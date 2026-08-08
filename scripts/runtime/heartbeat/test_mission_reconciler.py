from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

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
            error TEXT,
            updated_at TEXT
        );
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
            "'engagement-1', 'running', ?, NULL, NULL, NULL, '')",
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
