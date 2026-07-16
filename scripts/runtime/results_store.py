"""
results_store.py — Persistence helpers for review receipts.

Runtime return handling writes structured receipts into the existing `results`
table and leaves graph truth untouched.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# GDDP_RUNTIME_ROOT points to the runtime state root; OPCLAW_ROOT remains a legacy fallback.
_default_root = Path(__file__).parent.parent.parent
RUNTIME_ROOT = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH = RUNTIME_ROOT / "db" / "queue.db"


def _connect() -> sqlite3.Connection:
    """Create a WAL-mode connection with busy timeout for concurrent writes.

    Concurrency: WAL lets readers overlap the single writer; busy_timeout
    makes a colliding writer wait instead of raising 'database is locked'.
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_or_none(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


def init_db() -> None:
    """Ensure the canonical review-receipt table exists."""
    con = _connect()
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                result_id                   TEXT PRIMARY KEY,
                schema_version              TEXT NOT NULL DEFAULT '1.0',
                job_id                      TEXT NOT NULL,
                executor                    TEXT NOT NULL,
                received_at                 TEXT NOT NULL,
                execution_duration_seconds  INTEGER,
                outcome                     TEXT NOT NULL,
                status                      TEXT NOT NULL,
                changed_files               TEXT,
                patch_path                  TEXT,
                summary_path                TEXT,
                logs_path                   TEXT,
                acceptance_check            TEXT,
                risks                       TEXT,
                followup_candidates         TEXT,
                github_action               TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            )
            """
        )
        con.commit()
    finally:
        con.close()


def write_result(
    result_id: str,
    job_id: str,
    executor: str,
    outcome: str,
    status: str,
    received_at: str = None,
    execution_duration_seconds: int = None,
    changed_files=None,
    patch_path: str = None,
    summary_path: str = None,
    logs_path: str = None,
    acceptance_check=None,
    risks=None,
    followup_candidates=None,
    github_action=None,
):
    """Insert or update a structured review receipt in the canonical results table."""
    init_db()
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute("SELECT 1 FROM results WHERE result_id = ?", (result_id,))
        exists = cur.fetchone()

        payload = {
            "result_id": result_id,
            "job_id": job_id,
            "executor": executor,
            "received_at": received_at or _now(),
            "execution_duration_seconds": execution_duration_seconds,
            "outcome": outcome,
            "status": status,
            "changed_files": _json_or_none(changed_files),
            "patch_path": patch_path,
            "summary_path": summary_path,
            "logs_path": logs_path,
            "acceptance_check": _json_or_none(acceptance_check),
            "risks": _json_or_none(risks),
            "followup_candidates": _json_or_none(followup_candidates),
            "github_action": _json_or_none(github_action),
        }

        if not exists:
            con.execute(
                """
                INSERT INTO results (
                    result_id, job_id, executor, received_at,
                    execution_duration_seconds, outcome, status,
                    changed_files, patch_path, summary_path, logs_path,
                    acceptance_check, risks, followup_candidates, github_action
                ) VALUES (
                    :result_id, :job_id, :executor, :received_at,
                    :execution_duration_seconds, :outcome, :status,
                    :changed_files, :patch_path, :summary_path, :logs_path,
                    :acceptance_check, :risks, :followup_candidates, :github_action
                )
                """,
                payload,
            )
        else:
            con.execute(
                """
                UPDATE results
                   SET job_id = :job_id,
                       executor = :executor,
                       received_at = :received_at,
                       execution_duration_seconds = :execution_duration_seconds,
                       outcome = :outcome,
                       status = :status,
                       changed_files = :changed_files,
                       patch_path = :patch_path,
                       summary_path = :summary_path,
                       logs_path = :logs_path,
                       acceptance_check = :acceptance_check,
                       risks = :risks,
                       followup_candidates = :followup_candidates,
                       github_action = :github_action
                 WHERE result_id = :result_id
                """,
                payload,
            )
        con.commit()
    finally:
        con.close()


def init_decision_results() -> None:
    """Ensure the decision-loop results table exists.

    Distinct from the `results` receipt table: decision results record what the
    runtime decision loop *did* (dispatch / escalate / no_op), which may have no
    associated job (e.g. a no_op or a stale-state clean). No FK to jobs.
    """
    con = _connect()
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_results (
                result_id           TEXT PRIMARY KEY,
                schema_version      TEXT NOT NULL DEFAULT '1.0',
                action              TEXT NOT NULL,
                node_id             TEXT,
                project_id          TEXT,
                reason              TEXT,
                created_at          TEXT NOT NULL
            )
            """
        )
        con.commit()
    finally:
        con.close()


def write_decision_result(
    result_id: str,
    action: str,
    node_id: str = None,
    project_id: str = None,
    reason: str = None,
) -> None:
    """Insert a decision-loop result row. Does NOT touch graph truth."""
    init_decision_results()
    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO decision_results
                (result_id, action, node_id, project_id, reason, created_at)
            VALUES
                (:result_id, :action, :node_id, :project_id, :reason, :created_at)
            """,
            {
                "result_id": result_id,
                "action": action,
                "node_id": node_id,
                "project_id": project_id,
                "reason": reason,
                "created_at": _now(),
            },
        )
        con.commit()
    finally:
        con.close()
