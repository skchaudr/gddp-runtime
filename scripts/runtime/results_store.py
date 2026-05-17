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

# OPCLAW_ROOT: set env var on Pi to ~/opclaw, falls back to repo root for local dev
_default_root = Path(__file__).parent.parent.parent
DB_PATH = Path(os.environ.get("OPCLAW_ROOT", _default_root)) / "db" / "queue.db"


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
    con = sqlite3.connect(DB_PATH)
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
    con = sqlite3.connect(DB_PATH)
    try:
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

        # Optimization: Use SQLite native ON CONFLICT DO UPDATE to avoid
        # the read-then-write overhead of manual UPSERT.
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
            ON CONFLICT(result_id) DO UPDATE SET
                job_id = excluded.job_id,
                executor = excluded.executor,
                received_at = excluded.received_at,
                execution_duration_seconds = excluded.execution_duration_seconds,
                outcome = excluded.outcome,
                status = excluded.status,
                changed_files = excluded.changed_files,
                patch_path = excluded.patch_path,
                summary_path = excluded.summary_path,
                logs_path = excluded.logs_path,
                acceptance_check = excluded.acceptance_check,
                risks = excluded.risks,
                followup_candidates = excluded.followup_candidates,
                github_action = excluded.github_action
            """,
            payload,
        )
        con.commit()
    finally:
        con.close()
