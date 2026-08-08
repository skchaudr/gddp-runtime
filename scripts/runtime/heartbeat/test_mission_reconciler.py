from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.adapters.executor_protocol import PatchResult, SessionStatus
from scripts.runtime.heartbeat import reconciler


def _connection() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            project_id TEXT,
            node_id TEXT,
            repo TEXT,
            attempt INTEGER,
            status TEXT,
            queue_state TEXT
        );
        CREATE TABLE queue_records (
            job_id TEXT PRIMARY KEY,
            queue TEXT
        );
        CREATE TABLE executor_sessions (
            session_db_id TEXT PRIMARY KEY,
            job_id TEXT,
            executor TEXT,
            session_id TEXT,
            state TEXT,
            expected_base_commit_sha TEXT,
            result_commit_sha TEXT,
            patch_path TEXT,
            completion_id TEXT,
            completion_digest_sha256 TEXT,
            completion_quarantine_reason TEXT,
            evidence_manifest_path TEXT,
            error TEXT,
            updated_at TEXT
        );
        CREATE UNIQUE INDEX idx_completion_id
            ON executor_sessions(completion_id)
            WHERE completion_id IS NOT NULL;
        """
    )
    for index, node_id in enumerate(("node-alpha", "node-beta"), start=1):
        job_id = f"job-{node_id}"
        con.execute(
            "INSERT INTO jobs VALUES (?, 'project', ?, 'owner/repo', 0, "
            "'running', 'running')",
            (job_id, node_id),
        )
        con.execute(
            "INSERT INTO queue_records VALUES (?, 'running')", (job_id,)
        )
        con.execute(
            "INSERT INTO executor_sessions VALUES (?, ?, 'factory_mission', "
            "'engagement-1', 'running', ?, NULL, NULL, NULL, NULL, NULL, NULL, "
            "NULL, '')",
            (f"session-{index}", job_id, "a" * 40),
        )
    con.commit()
    return con


def test_reconciler_collects_engagement_once_and_fans_out_by_feature_id(
    monkeypatch, tmp_path
):
    con = _connection()
    sessions = con.execute(
        "SELECT * FROM executor_sessions ORDER BY session_db_id"
    ).fetchall()
    adapter = MagicMock()
    adapter.status.return_value = SessionStatus(state="completed")
    adapter.collect_engagement.return_value = [
        PatchResult(
            success=True,
            feature_id="node-beta",
            result_commit_sha="c" * 40,
            result_ref="gddp/engagement-1",
            evidence_manifest_path="/evidence/node-beta.json",
        ),
        PatchResult(
            success=True,
            feature_id="node-alpha",
            result_commit_sha="b" * 40,
            result_ref="gddp/engagement-1",
            evidence_manifest_path="/evidence/node-alpha.json",
        ),
    ]
    batch = MagicMock()
    monkeypatch.setattr(reconciler, "_resolve_ref", lambda *args: "c" * 40)
    monkeypatch.setattr(reconciler, "_is_ancestor", lambda *args: True)
    monkeypatch.setattr(reconciler, "_ensure_result_ref", lambda *args: None)

    reconciler._reconcile_engagement_group(
        con, adapter, sessions, tmp_path, batch
    )

    adapter.collect_engagement.assert_called_once()
    rows = {
        row["job_id"]: row
        for row in con.execute(
            "SELECT * FROM executor_sessions ORDER BY session_db_id"
        )
    }
    assert rows["job-node-alpha"]["result_commit_sha"] == "b" * 40
    assert rows["job-node-alpha"]["patch_path"] == "/evidence/node-alpha.json"
    assert rows["job-node-beta"]["result_commit_sha"] == "c" * 40
    assert rows["job-node-beta"]["patch_path"] == "/evidence/node-beta.json"
    assert batch.add.call_count == 2


def test_reconciler_routes_engagement_review_result_without_commit(
    monkeypatch, tmp_path
):
    con = _connection()
    sessions = con.execute(
        "SELECT * FROM executor_sessions ORDER BY session_db_id"
    ).fetchall()
    adapter = MagicMock()
    adapter.status.return_value = SessionStatus(state="completed")
    adapter.collect_engagement.return_value = [
        PatchResult(
            success=False,
            feature_id=node_id,
            result_ref="gddp/engagement-1",
            evidence_manifest_path=f"/evidence/{node_id}.json",
            review_required=True,
            error="Feature id drift requires human review",
        )
        for node_id in ("node-alpha", "node-beta")
    ]
    batch = MagicMock()

    reconciler._reconcile_engagement_group(
        con, adapter, sessions, tmp_path, batch
    )

    assert batch.add.call_count == 0
    assert {
        tuple(row)
        for row in con.execute(
            "SELECT status, queue_state FROM jobs"
        )
    } == {("awaiting_review", "awaiting_review")}
    assert {
        row[0]
        for row in con.execute("SELECT state FROM executor_sessions")
    } == {"evaluated"}


@pytest.mark.parametrize("terminal_state", ["crashed", "failed"])
def test_reconciler_collects_partial_evidence_after_engagement_failure(
    monkeypatch, tmp_path, terminal_state
):
    con = _connection()
    sessions = con.execute(
        "SELECT * FROM executor_sessions ORDER BY session_db_id"
    ).fetchall()
    adapter = MagicMock()
    adapter.status.return_value = SessionStatus(
        state=terminal_state,
        error="mission process died before mission_completed",
    )
    adapter.collect_engagement.return_value = [
        PatchResult(
            success=True,
            feature_id="node-alpha",
            result_commit_sha="b" * 40,
            result_ref="gddp/engagement-1",
            evidence_manifest_path="/evidence/node-alpha.json",
        ),
        PatchResult(
            success=False,
            feature_id="node-beta",
            result_ref="gddp/engagement-1",
            evidence_manifest_path="/evidence/node-beta.json",
            review_required=True,
            error="mission_crashed: incomplete feature",
        ),
    ]
    failed = MagicMock()
    batch = MagicMock()
    monkeypatch.setattr(reconciler, "_handle_failed", failed)
    monkeypatch.setattr(reconciler, "_resolve_ref", lambda *args: "b" * 40)
    monkeypatch.setattr(reconciler, "_is_ancestor", lambda *args: True)
    monkeypatch.setattr(reconciler, "_ensure_result_ref", lambda *args: None)

    reconciler._reconcile_engagement_group(
        con, adapter, sessions, tmp_path, batch
    )

    adapter.collect_engagement.assert_called_once()
    failed.assert_not_called()
    rows = {
        row["job_id"]: row
        for row in con.execute(
            "SELECT * FROM executor_sessions ORDER BY session_db_id"
        )
    }
    assert rows["job-node-alpha"]["state"] == "collected"
    assert rows["job-node-alpha"]["result_commit_sha"] == "b" * 40
    assert rows["job-node-beta"]["state"] == "evaluated"
    assert (
        rows["job-node-beta"]["patch_path"]
        == "/evidence/node-beta.json"
    )
    batch.add.assert_called_once()


def test_reconciler_persists_ancestry_mismatch_quarantine_reason(tmp_path):
    con = _connection()
    session = con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-1'"
    ).fetchone()
    adapter = MagicMock()
    adapter.status.return_value = SessionStatus(state="completed")
    quarantine_reason = (
        f"result {'b' * 40} does not descend from receipt base {'c' * 40}"
    )
    adapter.collect_engagement.return_value = [
        PatchResult(
            success=False,
            feature_id="node-alpha",
            result_commit_sha="b" * 40,
            result_ref="gddp/engagement-1",
            evidence_manifest_path="/evidence/node-alpha.json",
            completion_quarantine_reason=quarantine_reason,
            review_required=True,
            error=quarantine_reason,
        )
    ]
    batch = MagicMock()

    reconciler._reconcile_engagement_group(
        con, adapter, [session], tmp_path, batch
    )

    row = con.execute(
        """
        SELECT state, completion_quarantine_reason
          FROM executor_sessions
         WHERE session_db_id = 'session-1'
        """
    ).fetchone()
    assert row["state"] == "evaluated"
    assert row["completion_quarantine_reason"] == quarantine_reason
    batch.add.assert_not_called()


def test_reconciler_persists_completion_identity_before_evaluation(
    monkeypatch, tmp_path
):
    con = _connection()
    sessions = con.execute(
        "SELECT * FROM executor_sessions ORDER BY session_db_id"
    ).fetchall()
    adapter = MagicMock()
    adapter.status.return_value = SessionStatus(state="completed")
    adapter.collect_engagement.return_value = [
        PatchResult(
            success=True,
            feature_id=node_id,
            result_commit_sha=result_sha,
            result_ref="gddp/engagement-1",
            evidence_manifest_path=f"/evidence/{node_id}.json",
            completion_id=f"mission:{node_id}:worker",
            completion_digest_sha256=str(index) * 64,
        )
        for index, (node_id, result_sha) in enumerate(
            (("node-alpha", "b" * 40), ("node-beta", "c" * 40)),
            start=1,
        )
    ]
    batch = MagicMock()
    monkeypatch.setattr(reconciler, "_resolve_ref", lambda *args: "c" * 40)
    monkeypatch.setattr(reconciler, "_is_ancestor", lambda *args: True)
    monkeypatch.setattr(reconciler, "_ensure_result_ref", lambda *args: None)

    reconciler._reconcile_engagement_group(
        con, adapter, sessions, tmp_path, batch
    )

    rows = con.execute(
        """
        SELECT completion_id, completion_digest_sha256,
               evidence_manifest_path, completion_quarantine_reason
          FROM executor_sessions
         ORDER BY session_db_id
        """
    ).fetchall()
    assert [row["completion_id"] for row in rows] == [
        "mission:node-alpha:worker",
        "mission:node-beta:worker",
    ]
    assert [row["completion_digest_sha256"] for row in rows] == [
        "1" * 64,
        "2" * 64,
    ]
    assert [row["evidence_manifest_path"] for row in rows] == [
        "/evidence/node-alpha.json",
        "/evidence/node-beta.json",
    ]
    assert all(row["completion_quarantine_reason"] is None for row in rows)
    assert batch.add.call_count == 2


def test_reconciler_exact_duplicate_drives_job_forward_with_first_result(
    monkeypatch, tmp_path
):
    """Exact replay must not leave the job running forever.

    The first stored result is authoritative; the reconciler proceeds the
    second session through evaluation with that result instead of parking
    it as an unpolled completion_duplicate orphan.
    """
    con = _connection()
    con.execute(
        """
        UPDATE executor_sessions
           SET completion_id = 'completion-shared',
               completion_digest_sha256 = ?,
               result_commit_sha = ?,
               evidence_manifest_path = '/evidence/existing.json'
         WHERE session_db_id = 'session-1'
        """,
        ("1" * 64, "a" * 40),
    )
    con.commit()
    session = con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-2'"
    ).fetchone()
    adapter = MagicMock()
    adapter.status.return_value = SessionStatus(state="completed")
    adapter.collect_engagement.return_value = [
        PatchResult(
            success=True,
            feature_id="node-beta",
            result_commit_sha="b" * 40,
            result_ref="gddp/engagement-1",
            evidence_manifest_path="/evidence/replay.json",
            completion_id="completion-shared",
            completion_digest_sha256="1" * 64,
        )
    ]
    batch = MagicMock()
    monkeypatch.setattr(reconciler, "_resolve_ref", lambda *args: "a" * 40)
    monkeypatch.setattr(reconciler, "_is_ancestor", lambda *args: True)
    monkeypatch.setattr(reconciler, "_ensure_result_ref", lambda *args: None)
    monkeypatch.setattr(reconciler, "_parent_commit", lambda *args: "0" * 40)

    reconciler._reconcile_engagement_group(
        con, adapter, [session], tmp_path, batch
    )

    row = con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-2'"
    ).fetchone()
    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = 'job-node-beta'"
    ).fetchone()
    assert row["result_commit_sha"] == "a" * 40
    assert row["evidence_manifest_path"] == "/evidence/existing.json"
    assert row["state"] == "collected"
    assert row["completion_quarantine_reason"] is None
    assert job["status"] == "running"  # evaluation batch owns the next hop
    batch.add.assert_called_once()
    added = batch.add.call_args
    assert added.args[2] == "a" * 40  # first stored result, not the replay claim


def test_reconciler_quarantined_duplicate_is_not_enqueued_for_evaluation(
    monkeypatch, tmp_path
):
    """Replay carrying a quarantine reason must not launder into evaluation.

    Exact-duplicate forwarding fixes the stranded-running bug, but must
    preserve review disposition from the first stored result / incoming claim.
    """
    con = _connection()
    quarantine = (
        "feature result is reachable from protected branch main "
        "— protected-branch push detected"
    )
    con.execute(
        """
        UPDATE executor_sessions
           SET completion_id = 'completion-shared',
               completion_digest_sha256 = ?,
               result_commit_sha = ?,
               evidence_manifest_path = '/evidence/existing.json',
               completion_quarantine_reason = ?
         WHERE session_db_id = 'session-1'
        """,
        ("1" * 64, "a" * 40, quarantine),
    )
    con.commit()
    session = con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-2'"
    ).fetchone()
    adapter = MagicMock()
    adapter.status.return_value = SessionStatus(state="completed")
    adapter.collect_engagement.return_value = [
        PatchResult(
            success=False,
            feature_id="node-beta",
            result_commit_sha="b" * 40,
            result_ref="gddp/engagement-1",
            evidence_manifest_path="/evidence/replay.json",
            completion_id="completion-shared",
            completion_digest_sha256="1" * 64,
            review_required=True,
            completion_quarantine_reason=(
                "feature result is reachable from protected branch main "
                "— protected-branch push detected"
            ),
            error=(
                "feature result is reachable from protected branch main "
                "— protected-branch push detected"
            ),
        )
    ]
    batch = MagicMock()
    monkeypatch.setattr(reconciler, "_resolve_ref", lambda *args: "a" * 40)
    monkeypatch.setattr(reconciler, "_is_ancestor", lambda *args: True)
    monkeypatch.setattr(reconciler, "_ensure_result_ref", lambda *args: None)

    reconciler._reconcile_engagement_group(
        con, adapter, [session], tmp_path, batch
    )

    row = con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-2'"
    ).fetchone()
    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = 'job-node-beta'"
    ).fetchone()
    assert row["result_commit_sha"] == "a" * 40  # first stored cargo
    assert "protected-branch" in (row["error"] or "")
    assert job["status"] == "awaiting_review"
    assert job["queue_state"] == "awaiting_review"
    batch.add.assert_not_called()


def test_reconciler_same_session_replay_resumes_first_evaluation(
    monkeypatch, tmp_path
):
    con = _connection()
    con.execute(
        """
        UPDATE executor_sessions
           SET completion_id = 'completion-shared',
               completion_digest_sha256 = ?,
               result_commit_sha = ?,
               evidence_manifest_path = '/evidence/existing.json'
         WHERE session_db_id = 'session-1'
        """,
        ("1" * 64, "a" * 40),
    )
    con.commit()
    session = con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-1'"
    ).fetchone()
    adapter = MagicMock()
    adapter.status.return_value = SessionStatus(state="completed")
    adapter.collect_engagement.return_value = [
        PatchResult(
            success=True,
            feature_id="node-alpha",
            result_commit_sha="a" * 40,
            result_ref="gddp/engagement-1",
            evidence_manifest_path="/evidence/existing.json",
            completion_id="completion-shared",
            completion_digest_sha256="1" * 64,
        )
    ]
    batch = MagicMock()
    monkeypatch.setattr(reconciler, "_resolve_ref", lambda *args: "a" * 40)
    monkeypatch.setattr(reconciler, "_is_ancestor", lambda *args: True)
    monkeypatch.setattr(reconciler, "_ensure_result_ref", lambda *args: None)

    reconciler._reconcile_engagement_group(
        con, adapter, [session], tmp_path, batch
    )

    row = con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-1'"
    ).fetchone()
    assert row["state"] == "collected"
    assert row["result_commit_sha"] == "a" * 40
    batch.add.assert_called_once()


def test_mission_evaluation_success_and_error_route_only_to_review(
    monkeypatch,
):
    graph_status = {"value": "ready"}

    def _provisional_only(**kwargs):
        if kwargs["verification"].get("verdict") == "pass":
            graph_status["value"] = "provisional"
        return graph_status["value"] == "provisional"

    monkeypatch.setattr(reconciler, "write_result", lambda **_kwargs: None)
    monkeypatch.setattr(
        reconciler,
        "maybe_mark_provisional",
        _provisional_only,
    )

    for verification, expected_graph_status in (
        (
            {
                "verification_status": "ok",
                "verdict": "pass",
                "integrity": {
                    "intent_preserved": True,
                    "graph_integrity_preserved": True,
                    "required_human_review": False,
                },
            },
            "provisional",
        ),
        ({"verification_status": "error", "error": "evaluator crashed"}, "ready"),
    ):
        con = _connection()
        pending = reconciler.PendingEvaluation(
            session_db_id="session-1",
            session_id="engagement-1",
            executor="factory_mission",
            project_id="project",
            node_id="node-alpha",
            job_id="job-node-alpha",
            attempt=0,
            result_commit_sha="b" * 40,
        )
        graph_status["value"] = "ready"

        reconciler._finalize_evaluation(con, pending, verification)

        job = con.execute(
            "SELECT status, queue_state FROM jobs WHERE job_id = ?",
            (pending.job_id,),
        ).fetchone()
        queue = con.execute(
            "SELECT queue FROM queue_records WHERE job_id = ?",
            (pending.job_id,),
        ).fetchone()["queue"]
        session = con.execute(
            "SELECT state, result_commit_sha FROM executor_sessions "
            "WHERE session_db_id = ?",
            (pending.session_db_id,),
        ).fetchone()
        assert tuple(job) == ("awaiting_review", "awaiting_review")
        assert queue == "awaiting_review"
        assert session["state"] == "evaluated"
        assert graph_status["value"] == expected_graph_status
        assert graph_status["value"] != "complete"
