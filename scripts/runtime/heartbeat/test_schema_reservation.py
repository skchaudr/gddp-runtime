"""Legacy queue.db -> init_db -> reservation, plus isolated dispatch mechanics.

Reproduces the 2026-09-06 live failure (jobs missing expected_base_commit_sha)
with the real insert_job / _plan_dispatches path, then proves the existing
init_db migration, fake-executor smoke, and stranded-claim recovery.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import init_db as init_db_module
from scripts.adapters.executor_protocol import DispatchResult, SessionRef
from scripts.runtime.heartbeat import runner
from scripts.runtime.heartbeat.graph_reader import NodeData
from scripts.runtime.heartbeat.scope_checker import check_scope
from scripts.runtime.heartbeat.state_recorder import insert_job, mark_event_mapped

PROJECT = "schema-repair"
REPO = "owner/schema-repair"
NODE_ID = "nav-input-repair"
EVENT_ID = "evt_frontier_stranded_nav-input-repair_test"
BASE_SHA = "a" * 40

# Live khoj-38 queue.db jobs shape on 2026-09-06: plumbing_attempt present,
# expected_base_commit_sha absent. CREATE TABLE IF NOT EXISTS will not add it.
_LEGACY_JOBS = """
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    created_at TEXT NOT NULL,
    event_id TEXT,
    project_id TEXT,
    repo TEXT,
    node_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    executor TEXT NOT NULL,
    queue_state TEXT DEFAULT 'ready',
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    why TEXT,
    source_context TEXT,
    constraints TEXT,
    acceptance_criteria TEXT,
    dependencies TEXT,
    priority TEXT DEFAULT 'medium',
    risk_level TEXT DEFAULT 'low',
    estimated_effort TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'ready',
    attempt INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    artifacts_dir TEXT,
    required_artifacts TEXT NOT NULL DEFAULT '[]',
    previous_findings TEXT,
    result_summary_path TEXT,
    plumbing_attempt INTEGER NOT NULL DEFAULT 0
);
"""

_LEGACY_REST = """
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    received_at TEXT NOT NULL,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    url TEXT,
    repo TEXT,
    project_id TEXT,
    project_node_candidates TEXT,
    scope_status TEXT DEFAULT 'pending',
    priority TEXT DEFAULT 'pending',
    risk_level TEXT DEFAULT 'pending',
    classification TEXT,
    routing TEXT,
    status TEXT DEFAULT 'received',
    claimed_at TEXT
);
CREATE TABLE queue_records (
    queue_item_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    job_id TEXT NOT NULL,
    queue TEXT NOT NULL,
    available_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TEXT,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT
);
CREATE TABLE executor_sessions (
    session_db_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    executor TEXT NOT NULL,
    session_id TEXT NOT NULL,
    state TEXT DEFAULT 'dispatched',
    execution_attempt_id TEXT NOT NULL,
    attempt_index INTEGER NOT NULL,
    expected_base_commit_sha TEXT,
    result_commit_sha TEXT,
    patch_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE results (
    result_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    job_id TEXT NOT NULL,
    executor TEXT NOT NULL,
    received_at TEXT NOT NULL,
    execution_duration_seconds INTEGER,
    outcome TEXT NOT NULL,
    status TEXT NOT NULL,
    changed_files TEXT,
    patch_path TEXT,
    summary_path TEXT,
    logs_path TEXT,
    acceptance_check TEXT,
    risks TEXT,
    followup_candidates TEXT,
    github_action TEXT
);
"""


def _legacy_db(path: Path, *, sentinel: bool = True) -> None:
    con = sqlite3.connect(path)
    con.executescript("PRAGMA foreign_keys=ON;" + _LEGACY_JOBS + _LEGACY_REST)
    if sentinel:
        con.execute(
            "INSERT INTO jobs (job_id, created_at, project_id, repo, node_id, "
            "job_type, executor, title, goal, status, plumbing_attempt) "
            "VALUES ('job_preexisting', '2026-01-01T00:00:00Z', 'other', "
            "'owner/other', 'other-node', 'implementation', 'pi_rpc', "
            "'keep me', 'keep me', 'complete', 2)"
        )
    con.commit()
    con.close()


def _job_columns(path: Path) -> set[str]:
    con = sqlite3.connect(path)
    names = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
    con.close()
    return names


def _reservation_job(job_id: str = "job_reserved") -> dict:
    return {
        "job_id": job_id,
        "created_at": "2026-09-06T11:44:10+00:00",
        "event_id": EVENT_ID,
        "project_id": PROJECT,
        "repo": REPO,
        "node_id": NODE_ID,
        "job_type": "implementation",
        "executor": "local_subprocess",
        "queue_state": "ready",
        "title": "Repair input",
        "goal": "Produce a reviewable result",
        "why": "walk is blocked",
        "constraints": "[]",
        "acceptance_criteria": "[]",
        "priority": "medium",
        "status": "ready",
        "attempt": 0,
        "max_attempts": 3,
        "artifacts_dir": "/tmp/job_reserved/",
        "required_artifacts": "[]",
        "previous_findings": None,
        "expected_base_commit_sha": BASE_SHA,
    }


def _node() -> NodeData:
    return NodeData(
        node_id=NODE_ID,
        title="Repair input",
        status="ready",
        type="capability",
        why="walk is blocked",
        depends_on=[],
        acceptance_criteria=["walk works"],
        constraints=[],
        allowed_execution_modes=["local_subprocess"],
        required_artifacts=[],
        priority="medium",
        unlocks=[],
    )


def _insert_event(con: sqlite3.Connection, *, status: str, claimed_at: str | None) -> None:
    con.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, actor, "
        "url, repo, project_id, project_node_candidates, routing, status, "
        "claimed_at) VALUES (?, '2026-09-06T06:04:50Z', 'frontier_auto', "
        "'issue.opened', 'frontier', 'frontier-dispatch://node: nav-input-repair', "
        "?, ?, ?, ?, ?, ?)",
        (
            EVENT_ID,
            REPO,
            PROJECT,
            f'["{NODE_ID}"]',
            '{"selected_executor": "local_subprocess"}',
            status,
            claimed_at,
        ),
    )
    con.commit()


def _patch_planner(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "RUNTIME_ROOT", tmp_path / "runtime")
    monkeypatch.setattr(
        runner,
        "classify",
        lambda event, nodes: {
            "matched_node_id": NODE_ID,
            "executor_recommendation": "local_subprocess",
        },
    )
    monkeypatch.setattr(
        runner, "executor_preflight_error", lambda *a, **k: None
    )


def test_insert_job_fails_on_legacy_jobs_schema_before_migration(tmp_path):
    db_path = tmp_path / "queue.db"
    _legacy_db(db_path)
    assert "expected_base_commit_sha" not in _job_columns(db_path)

    con = sqlite3.connect(db_path)
    with pytest.raises(
        sqlite3.OperationalError, match="no column named expected_base_commit_sha"
    ):
        insert_job(con, _reservation_job())
    con.close()


def test_plan_dispatches_fails_on_legacy_schema_and_leaves_claim(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "queue.db"
    _legacy_db(db_path)
    _patch_planner(monkeypatch, tmp_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    _insert_event(con, status="received", claimed_at=None)

    with pytest.raises(
        sqlite3.OperationalError, match="no column named expected_base_commit_sha"
    ):
        runner._plan_dispatches(
            con,
            PROJECT,
            REPO,
            [_node()],
            None,
            expected_base_commit_sha=BASE_SHA,
        )
    # Claim is committed before insert_job; classified+job sit in the
    # uncommitted BEGIN IMMEDIATE and disappear when the connection closes.
    con.close()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT status, claimed_at FROM events WHERE event_id = ?", (EVENT_ID,)
    ).fetchone()
    assert row["status"] == "claimed"
    assert row["claimed_at"]
    assert con.execute(
        "SELECT COUNT(*) FROM jobs WHERE job_id != 'job_preexisting'"
    ).fetchone()[0] == 0
    con.close()


def test_init_db_then_reservation_succeeds_and_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    _legacy_db(db_path)
    _patch_planner(monkeypatch, tmp_path)

    init_db_module.init_db(db_path, quiet=True)
    init_db_module.init_db(db_path, quiet=True)

    assert "expected_base_commit_sha" in _job_columns(db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    kept = con.execute(
        "SELECT status, plumbing_attempt, expected_base_commit_sha "
        "FROM jobs WHERE job_id = 'job_preexisting'"
    ).fetchone()
    assert tuple(kept) == ("complete", 2, None)

    _insert_event(con, status="received", claimed_at=None)
    planned = runner._plan_dispatches(
        con,
        PROJECT,
        REPO,
        [_node()],
        None,
        expected_base_commit_sha=BASE_SHA,
    )
    assert len(planned) == 1
    job = con.execute(
        "SELECT node_id, expected_base_commit_sha, status FROM jobs "
        "WHERE job_id = ?",
        (planned[0].job["job_id"],),
    ).fetchone()
    assert job["node_id"] == NODE_ID
    assert job["expected_base_commit_sha"] == BASE_SHA
    assert job["status"] == "ready"
    event = con.execute(
        "SELECT status FROM events WHERE event_id = ?", (EVENT_ID,)
    ).fetchone()
    assert event["status"] == "classified"
    con.close()


def test_connect_opens_migrated_legacy_db(tmp_path, monkeypatch):
    """ensure_schema() is the startup migration; connect() opens the file."""
    db_path = tmp_path / "queue.db"
    _legacy_db(db_path)
    monkeypatch.setattr(runner, "DB_PATH", db_path)
    runner.ensure_schema()
    con = runner.connect()
    insert_job(con, _reservation_job("job_via_connect"))
    con.commit()
    stored = con.execute(
        "SELECT expected_base_commit_sha FROM jobs WHERE job_id = 'job_via_connect'"
    ).fetchone()[0]
    assert stored == BASE_SHA
    con.close()


def test_connect_without_ensure_schema_keeps_legacy_jobs_column_missing(
    tmp_path, monkeypatch
):
    """Installed systemd ticks call connect() only; that is the live seam."""
    db_path = tmp_path / "queue.db"
    _legacy_db(db_path)
    monkeypatch.setattr(runner, "DB_PATH", db_path)
    con = runner.connect()
    with pytest.raises(
        sqlite3.OperationalError, match="no column named expected_base_commit_sha"
    ):
        insert_job(con, _reservation_job("job_unmigrated"))
    con.close()


def test_repo_systemd_unit_runs_init_db_before_runner():
    unit = (
        Path(__file__).resolve().parents[3]
        / "deploy/mini-heartbeat/systemd/gddp-heartbeat.service"
    )
    text = unit.read_text()
    assert "scripts/init_db.py" in text
    assert "scripts.runtime.heartbeat.runner" in text
    assert text.index("scripts/init_db.py") < text.index(
        "scripts.runtime.heartbeat.runner"
    )


def test_fake_executor_success_and_failure_receipts(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    _legacy_db(db_path, sentinel=False)
    init_db_module.init_db(db_path, quiet=True)
    _patch_planner(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "executor_supports_engagement", lambda *a, **k: False)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    _insert_event(con, status="received", claimed_at=None)
    planned = runner._plan_dispatches(
        con,
        PROJECT,
        REPO,
        [_node()],
        None,
        expected_base_commit_sha=BASE_SHA,
    )
    assert len(planned) == 1
    job_id = planned[0].job["job_id"]
    attempt_dir = tmp_path / "attempt" / job_id
    attempt_dir.mkdir(parents=True)
    (attempt_dir / "result.json").write_text('{"ok": true}\n')

    monkeypatch.setattr(
        runner,
        "dispatch",
        lambda job, repo, repo_path=None, **k: DispatchResult(
            success=True,
            session_ref=SessionRef("local_subprocess", "fake-session-1"),
            attempt_dir=attempt_dir,
        ),
    )
    outcomes = runner._execute_dispatches(planned, REPO, str(tmp_path / "repo"))
    runner._record_outcomes(con, planned, outcomes, str(tmp_path / "repo"))

    session = con.execute(
        "SELECT state, session_id, attempt_dir FROM executor_sessions "
        "WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    event = con.execute(
        "SELECT status FROM events WHERE event_id = ?", (EVENT_ID,)
    ).fetchone()
    assert session["state"] == "dispatched"
    assert session["session_id"] == "fake-session-1"
    assert job["status"] == "running"
    assert event["status"] == "mapped"

    fail_event = "evt_fail"
    con.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, repo, "
        "project_id, status) VALUES (?, '2026-09-06T07:00:00Z', 'manual', "
        "'issue.opened', ?, ?, 'received')",
        (fail_event, REPO, PROJECT),
    )
    con.commit()
    monkeypatch.setattr(
        runner,
        "classify",
        lambda event, nodes: {
            "matched_node_id": NODE_ID,
            "executor_recommendation": "local_subprocess",
        },
    )
    # Active running job must block a second reservation for the same node.
    planned_blocked = runner._plan_dispatches(
        con,
        PROJECT,
        REPO,
        [_node()],
        SimpleNamespace(),
        expected_base_commit_sha=BASE_SHA,
    )
    assert planned_blocked == []
    blocked = con.execute(
        "SELECT status FROM events WHERE event_id = ?", (fail_event,)
    ).fetchone()[0]
    assert blocked == "scope_blocked"

    # Failure reporting: a reserved job whose executor returns success=False.
    fail_job_id = "job_dispatch_failure"
    con.execute(
        "INSERT INTO jobs (job_id, created_at, event_id, project_id, repo, "
        "node_id, job_type, executor, queue_state, title, goal, status, "
        "attempt, max_attempts, required_artifacts, expected_base_commit_sha) "
        "VALUES (?, '2026-09-06T07:01:00Z', ?, ?, ?, 'other-node', "
        "'implementation', 'local_subprocess', 'ready', 'Fail', 'Fail', "
        "'ready', 0, 3, '[]', ?)",
        (fail_job_id, fail_event, PROJECT, REPO, BASE_SHA),
    )
    from scripts.runtime.heartbeat.state_recorder import insert_executor_session

    session_db_id = insert_executor_session(
        con,
        fail_job_id,
        "local_subprocess",
        f"{fail_job_id}:attempt:0",
        expected_base_commit_sha=BASE_SHA,
        attempt_index=0,
        state="dispatching",
    )
    fail_planned = runner.PlannedDispatch(
        event_id=fail_event,
        classification={"executor_recommendation": "local_subprocess"},
        job={"job_id": fail_job_id, "node_id": "other-node", "repo": REPO},
        session_db_id=session_db_id,
    )
    fail_outcome = runner.DispatchOutcome(
        planned=fail_planned,
        success=False,
        error="worker launch failed",
    )
    runner._record_outcomes(con, [fail_planned], {fail_job_id: fail_outcome})
    assert con.execute(
        "SELECT status FROM jobs WHERE job_id = ?", (fail_job_id,)
    ).fetchone()[0] == "failed"
    assert con.execute(
        "SELECT state FROM executor_sessions WHERE session_db_id = ?",
        (session_db_id,),
    ).fetchone()[0] == "dispatch_failed"
    con.close()


def test_stranded_claim_recovery_blocks_duplicate_dispatch(tmp_path, monkeypatch):
    """Crash-claimed event, no job: migrate, then stale reclaim hits the
    existing active-job guard (the adopt / awaiting_result path)."""
    db_path = tmp_path / "queue.db"
    _legacy_db(db_path, sentinel=False)
    _patch_planner(monkeypatch, tmp_path)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    fresh = datetime.now(timezone.utc).isoformat()
    _insert_event(con, status="claimed", claimed_at=fresh)

    with pytest.raises(sqlite3.OperationalError):
        insert_job(con, _reservation_job())
    con.close()

    init_db_module.init_db(db_path, quiet=True)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    # Fresh claim: 30-minute lease still holds; no second reservation.
    planned_held = runner._plan_dispatches(
        con,
        PROJECT,
        REPO,
        [_node()],
        None,
        expected_base_commit_sha=BASE_SHA,
    )
    assert planned_held == []
    assert con.execute(
        "SELECT status FROM events WHERE event_id = ?", (EVENT_ID,)
    ).fetchone()[0] == "claimed"

    # Canonical hold before reclaim: an adopt-shaped awaiting_result job.
    con.execute(
        "INSERT INTO jobs (job_id, created_at, project_id, repo, node_id, "
        "job_type, executor, queue_state, title, goal, status, attempt, "
        "max_attempts, required_artifacts, expected_base_commit_sha) VALUES "
        "('job_adopted', '2026-09-06T11:00:00Z', ?, ?, ?, 'implementation', "
        "'local_subprocess', 'awaiting_result', 'Adopted', 'Adopted', "
        "'awaiting_result', 0, 3, '[]', ?)",
        (PROJECT, REPO, NODE_ID, BASE_SHA),
    )
    con.commit()
    assert not check_scope(_node(), PROJECT, con, graph_reader=None)

    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    con.execute(
        "UPDATE events SET claimed_at = ? WHERE event_id = ?", (stale, EVENT_ID)
    )
    con.commit()
    planned_reclaim = runner._plan_dispatches(
        con,
        PROJECT,
        REPO,
        [_node()],
        SimpleNamespace(),
        expected_base_commit_sha=BASE_SHA,
    )
    assert planned_reclaim == []
    recovered = con.execute(
        "SELECT status FROM events WHERE event_id = ?", (EVENT_ID,)
    ).fetchone()[0]
    assert recovered == "scope_blocked"
    assert con.execute(
        "SELECT COUNT(*) FROM jobs WHERE job_id != 'job_adopted'"
    ).fetchone()[0] == 0
    con.close()


def test_mapped_stranded_event_stays_inert_after_migration(tmp_path, monkeypatch):
    """Operator recovery when adopt is the chosen hold: map the crash claim
    so stale reclaim cannot pick it up."""
    db_path = tmp_path / "queue.db"
    _legacy_db(db_path, sentinel=False)
    init_db_module.init_db(db_path, quiet=True)
    _patch_planner(monkeypatch, tmp_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    _insert_event(con, status="claimed", claimed_at=stale)
    mark_event_mapped(con, EVENT_ID)
    con.commit()
    planned = runner._plan_dispatches(
        con,
        PROJECT,
        REPO,
        [_node()],
        None,
        expected_base_commit_sha=BASE_SHA,
    )
    assert planned == []
    assert con.execute(
        "SELECT status FROM events WHERE event_id = ?", (EVENT_ID,)
    ).fetchone()[0] == "mapped"
    assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    con.close()
