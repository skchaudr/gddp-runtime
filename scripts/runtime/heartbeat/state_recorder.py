"""
state_recorder.py — All SQLite state mutations for the heartbeat.

Single responsibility: write to the DB. No business logic here.
"""

import json
import sqlite3
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_id() -> str:
    return now().replace(":", "").replace("-", "").replace(".", "")[:17]


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
