"""
state_recorder.py — All SQLite state mutations for the heartbeat.

Single responsibility: write to the DB. No business logic here.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

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
               priority, status, attempt, max_attempts, artifacts_dir,
               required_artifacts, previous_findings
           ) VALUES (
               :job_id, :created_at, :event_id, :project_id, :repo, :node_id,
               :job_type, :executor, :queue_state, :title, :goal, :why,
               :constraints, :acceptance_criteria,
               :priority, :status, :attempt, :max_attempts, :artifacts_dir,
               :required_artifacts, :previous_findings
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


def mark_job_cancelled(con: sqlite3.Connection, job_id: str) -> None:
    """Persist a terminal local cancellation without mutating graph truth."""
    con.execute(
        """UPDATE jobs
           SET status = 'cancelled', queue_state = 'cancelled'
           WHERE job_id = ?""",
        (job_id,),
    )
    con.execute(
        "UPDATE queue_records SET queue = 'cancelled' WHERE job_id = ?",
        (job_id,),
    )


def execution_attempt_id(job_id: str, attempt_index: int) -> str:
    return f"{job_id}:attempt:{attempt_index}"


def insert_executor_session(
    con: sqlite3.Connection,
    job_id: str,
    executor: str,
    session_id: str,
    expected_base_commit_sha: str | None = None,
    *,
    attempt_index: int | None = None,
    state: str = "dispatched",
) -> str:
    """Insert one immutable attempt record and return its database id."""
    if attempt_index is None:
        row = con.execute(
            "SELECT attempt FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"job not found: {job_id}")
        attempt_index = int(row["attempt"] if hasattr(row, "keys") else row[0])
    attempt_id = execution_attempt_id(job_id, attempt_index)
    session_db_id = f"ses_{ts_id()}"
    ts = now()
    con.execute(
        """INSERT INTO executor_sessions
           (session_db_id, job_id, executor, session_id,
            execution_attempt_id, attempt_index, state,
            expected_base_commit_sha, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_db_id,
            job_id,
            executor,
            session_id,
            attempt_id,
            attempt_index,
            state,
            expected_base_commit_sha,
            ts,
            ts,
        ),
    )
    return session_db_id


def allocate_retry_attempt(
    con: sqlite3.Connection,
    job,
    *,
    executor: str,
    expected_base_commit_sha: str | None = None,
    previous_findings: dict | str | None = None,
) -> tuple[dict, str] | None:
    """Atomically increment a known job attempt and insert its dispatch record."""
    persisted_job = dict(job)
    current_attempt = int(persisted_job.get("attempt") or 0)
    max_attempts = int(persisted_job.get("max_attempts") or 0)
    if current_attempt >= max_attempts:
        return None

    next_attempt = current_attempt + 1
    encoded_findings = previous_findings
    if isinstance(encoded_findings, dict):
        encoded_findings = json.dumps(
            encoded_findings, sort_keys=True, separators=(",", ":")
        )
    updated = con.execute(
        """UPDATE jobs
              SET attempt = ?,
                  previous_findings = COALESCE(?, previous_findings)
            WHERE job_id = ? AND attempt = ?""",
        (
            next_attempt,
            encoded_findings,
            persisted_job["job_id"],
            current_attempt,
        ),
    )
    if updated.rowcount != 1:
        return None

    persisted_job["attempt"] = next_attempt
    if encoded_findings is not None:
        persisted_job["previous_findings"] = encoded_findings
    attempt_id = execution_attempt_id(persisted_job["job_id"], next_attempt)
    session_db_id = insert_executor_session(
        con,
        persisted_job["job_id"],
        executor,
        attempt_id,
        expected_base_commit_sha,
        attempt_index=next_attempt,
        state="dispatching",
    )
    return persisted_job, session_db_id


def finalize_executor_session_dispatch(
    con: sqlite3.Connection,
    session_db_id: str,
    *,
    state: str,
    executor: str | None = None,
    session_id: str | None = None,
    expected_base_commit_sha: str | None = None,
    error: str | None = None,
) -> bool:
    """Finalize a reserved attempt only while it is still dispatching."""
    updated = con.execute(
        """UPDATE executor_sessions
              SET state = ?,
                  executor = COALESCE(?, executor),
                  session_id = COALESCE(?, session_id),
                  expected_base_commit_sha =
                      COALESCE(?, expected_base_commit_sha),
                  error = COALESCE(?, error),
                  updated_at = ?
            WHERE session_db_id = ?
              AND state = 'dispatching'""",
        (
            state,
            executor,
            session_id,
            expected_base_commit_sha,
            error,
            now(),
            session_db_id,
        ),
    )
    return updated.rowcount == 1


def recover_stale_dispatching_sessions(
    con: sqlite3.Connection,
    *,
    current_time: datetime | None = None,
    stale_after: timedelta = timedelta(minutes=30),
    repo: str | None = None,
) -> list[str]:
    """Terminalize expired dispatch reservations whose remote outcome is unknown."""
    current_time = current_time or datetime.now(timezone.utc)
    cutoff = (current_time - stale_after).isoformat()
    params: tuple = (cutoff,)
    repo_clause = ""
    if repo is not None:
        repo_clause = " AND j.repo = ?"
        params = (cutoff, repo)
    rows = con.execute(
        f"""SELECT es.session_db_id, es.job_id
              FROM executor_sessions es
              JOIN jobs j ON j.job_id = es.job_id
             WHERE es.state = 'dispatching'
               AND es.updated_at <= ?
               AND es.attempt_index = j.attempt
               AND j.status <> 'cancelled'
               {repo_clause}
             ORDER BY es.updated_at""",
        params,
    ).fetchall()
    reason = (
        "dispatch outcome unknown after heartbeat restart; reservation lease "
        "expired; not retried automatically; operator recovery required"
    )
    recovered: list[str] = []
    for row in rows:
        session_db_id = row["session_db_id"]
        updated = con.execute(
            """UPDATE executor_sessions
                  SET state = 'dispatch_failed', error = ?, updated_at = ?
                WHERE session_db_id = ?
                  AND state = 'dispatching'
                  AND updated_at <= ?""",
            (reason, current_time.isoformat(), session_db_id, cutoff),
        )
        if updated.rowcount != 1:
            continue
        mark_job_failed(con, row["job_id"])
        recovered.append(session_db_id)
    return recovered


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


def get_active_executor_sessions(
    con: sqlite3.Connection,
    repo: str | None = None,
) -> list:
    """Get sessions in dispatched/running/needs_operator state.

    If ``repo`` is provided (GitHub owner/name, e.g. "skchaudr/gddp-runtime"),
    only return sessions whose job matches that repo. This is the cross-repo
    reconciliation guard: a heartbeat operating on one repo_path must never
    apply patches belonging to a session for a different repo.

    Backward-compatible: callers that omit ``repo`` get all active sessions,
    preserving the original behaviour.
    """
    if repo:
        return con.execute(
            """SELECT es.* FROM executor_sessions es
               JOIN jobs j ON es.job_id = j.job_id
               WHERE es.state IN ('dispatched', 'running', 'needs_operator')
                 AND j.repo = ?
               ORDER BY es.created_at""",
            (repo,),
        ).fetchall()
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
