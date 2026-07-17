"""
state_recorder.py — All SQLite state mutations for the heartbeat.

Single responsibility: write to the DB. No business logic here.
"""

import json
import sqlite3
from datetime import datetime, timezone

from .job_factory import ts_id


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_event_ignored(con: sqlite3.Connection, event_id: str) -> None:
    con.execute(
        "UPDATE events SET status = 'ignored' WHERE event_id = ?",
        (event_id,),
    )


def mark_event_classified(
    con: sqlite3.Connection,
    event_id: str,
    classification: dict,
) -> None:
    con.execute(
        """UPDATE events
           SET status = 'classified',
               classification = ?,
               scope_status = 'in_scope'
           WHERE event_id = ?""",
        (json.dumps(classification), event_id),
    )


def mark_event_scope_blocked(
    con: sqlite3.Connection,
    event_id: str,
    reason: str,
) -> None:
    con.execute(
        """UPDATE events
           SET status = 'scope_blocked',
               scope_status = 'blocked',
               classification = ?
           WHERE event_id = ?""",
        (json.dumps({"blocked_reason": reason}), event_id),
    )


def insert_job(con: sqlite3.Connection, job: dict) -> None:
    con.execute(
        """INSERT INTO jobs (
               job_id, created_at, event_id, project_id, repo, node_id,
               job_type, executor, queue_state, title, goal, why,
               constraints, acceptance_criteria,
               priority, status, attempt, max_attempts, artifacts_dir
           ) VALUES (
               :job_id, :created_at, :event_id, :project_id, :repo, :node_id,
               :job_type, :executor, :queue_state, :title, :goal, :why,
               :constraints, :acceptance_criteria,
               :priority, :status, :attempt, :max_attempts, :artifacts_dir
           )""",
        job,
    )


def insert_queue_record(con: sqlite3.Connection, job_id: str) -> None:
    con.execute(
        """INSERT INTO queue_records (queue_item_id, job_id, queue, available_at)
           VALUES (?, ?, 'ready', ?)""",
        (f"qi_{ts_id()}", job_id, now()),
    )


def mark_job_running(con: sqlite3.Connection, job_id: str) -> None:
    con.execute(
        """UPDATE jobs
           SET status = 'running', queue_state = 'running'
           WHERE job_id = ?""",
        (job_id,),
    )
    con.execute(
        "UPDATE queue_records SET queue = 'running' WHERE job_id = ?",
        (job_id,),
    )


def mark_event_mapped(con: sqlite3.Connection, event_id: str) -> None:
    con.execute(
        "UPDATE events SET status = 'mapped' WHERE event_id = ?",
        (event_id,),
    )


def mark_job_failed(con: sqlite3.Connection, job_id: str) -> None:
    con.execute(
        """UPDATE jobs
           SET status = 'failed', queue_state = 'failed'
           WHERE job_id = ?""",
        (job_id,),
    )
    con.execute(
        "UPDATE queue_records SET queue = 'failed' WHERE job_id = ?",
        (job_id,),
    )


def insert_executor_session(
    con: sqlite3.Connection,
    job_id: str,
    executor: str,
    session_id: str,
    expected_base_commit_sha: str | None = None,
) -> str:
    """Insert a new executor session record. Returns the session_db_id."""
    session_db_id = f"ses_{ts_id()}"
    ts = now()
    con.execute(
        """INSERT INTO executor_sessions
           (session_db_id, job_id, executor, session_id, state,
            expected_base_commit_sha, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'dispatched', ?, ?, ?)""",
        (session_db_id, job_id, executor, session_id,
         expected_base_commit_sha, ts, ts),
    )
    return session_db_id


def update_executor_session_state(
    con: sqlite3.Connection,
    session_db_id: str,
    state: str,
    error: str | None = None,
    result_commit_sha: str | None = None,
    patch_path: str | None = None,
) -> None:
    """Update an executor session's state and optional fields.

    Optional fields (error, result_commit_sha, patch_path) are only overwritten
    when explicitly passed; omitting one (or passing None) preserves the
    existing value. This lets a state-only transition (e.g. collected ->
    evaluated) keep the result commit SHA recorded by an earlier step instead
    of clobbering it back to NULL.
    """
    con.execute(
        """UPDATE executor_sessions
              SET state = ?,
                  error = COALESCE(?, error),
                  result_commit_sha = COALESCE(?, result_commit_sha),
                  patch_path = COALESCE(?, patch_path),
                  updated_at = ?
            WHERE session_db_id = ?""",
        (state, error, result_commit_sha, patch_path, now(), session_db_id),
    )


def get_active_executor_sessions(con: sqlite3.Connection) -> list:
    """Get all sessions in dispatched/running/needs_operator state."""
    return con.execute(
        """SELECT * FROM executor_sessions
            WHERE state IN ('dispatched', 'running', 'needs_operator')
            ORDER BY created_at"""
    ).fetchall()


def get_executor_session_by_id(
    con: sqlite3.Connection,
    session_db_id: str,
):
    """Get a single executor session by its DB id."""
    return con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = ?",
        (session_db_id,),
    ).fetchone()
