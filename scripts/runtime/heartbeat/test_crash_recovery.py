"""test_crash_recovery.py — Tests for heartbeat crash recovery and concurrency.

Proves:
- stale-claim-recovery-tested: stale 'claimed' events (past 30 mins) are re-claimed.
- no-double-processing: concurrent heartbeat runs produce exactly one job for a received event.
"""

import concurrent.futures
import sqlite3
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.runtime.heartbeat import runner
from scripts.runtime.heartbeat.runner import _plan_dispatches, connect
from scripts.runtime.heartbeat.graph_reader import NodeData


def _init_db_file(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript(
        """
        PRAGMA foreign_keys=ON;

        CREATE TABLE events (
            event_id                TEXT PRIMARY KEY,
            schema_version          TEXT NOT NULL DEFAULT '1.0',
            received_at             TEXT NOT NULL,
            source                  TEXT NOT NULL,
            event_type              TEXT NOT NULL,
            actor                   TEXT,
            branch                  TEXT,
            base_branch             TEXT,
            pr_number               INTEGER,
            issue_number            INTEGER,
            commit_sha              TEXT,
            url                     TEXT,
            repo                    TEXT,
            project_id              TEXT,
            project_node_candidates TEXT,
            scope_status            TEXT DEFAULT 'pending',
            priority                TEXT DEFAULT 'pending',
            risk_level              TEXT DEFAULT 'pending',
            raw_payload_path        TEXT,
            normalized_payload_path TEXT,
            classification          TEXT,
            routing                 TEXT,
            status                  TEXT DEFAULT 'received',
            claimed_at              TEXT
        );

        CREATE TABLE jobs (
            job_id              TEXT PRIMARY KEY,
            schema_version      TEXT NOT NULL DEFAULT '1.0',
            created_at          TEXT NOT NULL,
            event_id            TEXT,
            project_id          TEXT,
            repo                TEXT,
            node_id             TEXT NOT NULL,
            job_type            TEXT NOT NULL,
            executor            TEXT NOT NULL,
            queue_state         TEXT DEFAULT 'ready',
            title               TEXT NOT NULL,
            goal                TEXT NOT NULL,
            why                 TEXT,
            source_context      TEXT,
            constraints         TEXT,
            acceptance_criteria TEXT,
            dependencies        TEXT,
            priority            TEXT DEFAULT 'medium',
            risk_level          TEXT DEFAULT 'low',
            estimated_effort    TEXT DEFAULT 'medium',
            status              TEXT DEFAULT 'ready',
            attempt             INTEGER DEFAULT 0,
            max_attempts        INTEGER DEFAULT 3,
            artifacts_dir       TEXT,
            result_summary_path TEXT,
            FOREIGN KEY(event_id) REFERENCES events(event_id)
        );

        CREATE TABLE queue_records (
            queue_item_id    TEXT PRIMARY KEY,
            schema_version   TEXT NOT NULL DEFAULT '1.0',
            job_id           TEXT NOT NULL,
            queue            TEXT NOT NULL,
            available_at     TEXT NOT NULL,
            lease_owner      TEXT,
            lease_expires_at TEXT,
            retry_count      INTEGER DEFAULT 0,
            last_error       TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(job_id)
        );
        """
    )
    con.commit()
    con.close()


@pytest.fixture
def test_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "queue.db"
    _init_db_file(db_file)

    # Mock runtime root and DB path in the runner
    monkeypatch.setattr(runner, "DB_PATH", db_file)
    monkeypatch.setattr(runner, "RUNTIME_ROOT", tmp_path)

    return db_file


def test_stale_claim_recovery_processed(test_db_path):
    """Proves: an event stuck in 'claimed' past the stale cutoff is re-claimed and processed by a later heartbeat run."""
    con = connect()

    now_utc = datetime.now(timezone.utc)
    stale_time = (now_utc - timedelta(minutes=45)).isoformat()
    fresh_time = (now_utc - timedelta(minutes=15)).isoformat()

    # 1. Insert a stale event and a fresh event
    con.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, project_id, repo, status, claimed_at, url) "
        "VALUES (?, ?, 'github', 'issue.opened', 'test-project', 'owner/repo', 'claimed', ?, 'node: test-node-stale')",
        ("evt_stale", now_utc.isoformat(), stale_time)
    )
    con.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, project_id, repo, status, claimed_at, url) "
        "VALUES (?, ?, 'github', 'issue.opened', 'test-project', 'owner/repo', 'claimed', ?, 'node: test-node-fresh')",
        ("evt_fresh", now_utc.isoformat(), fresh_time)
    )
    con.commit()

    # 2. Setup mock ready nodes
    node_stale = NodeData(
        node_id="test-node-stale",
        title="Stale Node Title",
        status="ready",
        type="task",
        why="Testing stale claim recovery",
        depends_on=[],
        acceptance_criteria=["Criteria 1"],
        constraints=["Constraint 1"],
        allowed_execution_modes=["jules"],
        required_artifacts=["decision.md"],
        priority="high",
        unlocks=[]
    )

    node_fresh = NodeData(
        node_id="test-node-fresh",
        title="Fresh Node Title",
        status="ready",
        type="task",
        why="Testing fresh claim should not be touched",
        depends_on=[],
        acceptance_criteria=["Criteria 2"],
        constraints=["Constraint 2"],
        allowed_execution_modes=["jules"],
        required_artifacts=["decision.md"],
        priority="high",
        unlocks=[]
    )

    ready_nodes = [node_stale, node_fresh]
    mock_reader = MagicMock()

    # 3. Call _plan_dispatches
    planned = _plan_dispatches(
        con=con,
        project_id="test-project",
        repo="owner/repo",
        ready_nodes=ready_nodes,
        reader=mock_reader
    )

    # 4. Assertions:
    # - Only the stale event should have been re-claimed and processed
    assert len(planned) == 1, f"Expected exactly 1 planned dispatch, got {len(planned)}"
    assert planned[0].event_id == "evt_stale"
    assert planned[0].job["node_id"] == "test-node-stale"

    # - Check the database to confirm statuses
    stale_row = con.execute("SELECT status, claimed_at FROM events WHERE event_id = 'evt_stale'").fetchone()
    fresh_row = con.execute("SELECT status, claimed_at FROM events WHERE event_id = 'evt_fresh'").fetchone()

    # Once processed in _plan_dispatches, status transitions from 'claimed' to 'classified'
    assert stale_row["status"] == "classified"

    # The fresh event remains in claimed status with its original fresh timestamp
    assert fresh_row["status"] == "claimed"
    assert fresh_row["claimed_at"] == fresh_time

    con.close()


def test_no_double_processing(test_db_path):
    """Proves: two concurrent heartbeat runs over the same received event produce exactly one job (atomic claim holds)."""
    con_main = connect()

    # 1. Insert exactly one 'received' event
    con_main.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, project_id, repo, status, url) "
        "VALUES (?, ?, 'github', 'issue.opened', 'test-project', 'owner/repo', 'received', 'node: test-node-concurrent')",
        ("evt_concurrent", datetime.now(timezone.utc).isoformat())
    )
    con_main.commit()
    con_main.close()

    node_concurrent = NodeData(
        node_id="test-node-concurrent",
        title="Concurrent Node",
        status="ready",
        type="task",
        why="Testing concurrent claim race condition",
        depends_on=[],
        acceptance_criteria=["Criteria C"],
        constraints=["Constraint C"],
        allowed_execution_modes=["jules"],
        required_artifacts=["decision.md"],
        priority="high",
        unlocks=[]
    )
    ready_nodes = [node_concurrent]
    mock_reader = MagicMock()

    claim_barrier = threading.Barrier(2)
    claim_attempts = []
    claim_attempts_lock = threading.Lock()

    class ClaimBarrierConnection:
        """Pause both runners after SELECT and immediately before the claim UPDATE."""

        def __init__(self, connection):
            self.connection = connection

        def execute(self, statement, parameters=()):
            normalized_statement = " ".join(statement.split())
            if "UPDATE events SET status = 'claimed'" in normalized_statement:
                with claim_attempts_lock:
                    claim_attempts.append(threading.get_ident())
                claim_barrier.wait(timeout=5)
            return self.connection.execute(statement, parameters)

        def __getattr__(self, name):
            return getattr(self.connection, name)

    # 2. Run _plan_dispatches in two concurrent threads on independent connections to the same DB file
    def run_worker():
        # Open an independent database connection for this thread
        sqlite_connection = connect()
        con_thread = ClaimBarrierConnection(sqlite_connection)
        try:
            planned_dispatches = _plan_dispatches(
                con=con_thread,
                project_id="test-project",
                repo="owner/repo",
                ready_nodes=ready_nodes,
                reader=mock_reader
            )
            return planned_dispatches
        finally:
            sqlite_connection.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_worker), executor.submit(run_worker)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # 3. Assertions
    # One worker must have planned 1 dispatch, and the other must have planned 0.
    total_planned = sum(len(r) for r in results)
    assert len(claim_attempts) == 2, "Both runners must reach the atomic claim UPDATE"
    assert total_planned == 1, f"Expected exactly 1 planned dispatch in total, got {total_planned}"

    # Verify via DB that only 1 job exists
    con_check = connect()
    jobs = con_check.execute("SELECT * FROM jobs").fetchall()
    assert len(jobs) == 1, f"Expected exactly 1 job in database, found {len(jobs)}"
    assert jobs[0]["node_id"] == "test-node-concurrent"
    con_check.close()
