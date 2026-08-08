"""
init_db.py — Initialize queue.db with tables matching Phase 0 schemas.

Tables mirror the YAML schemas in gddp-config/schemas/v1/:
  events            → event.yaml
  jobs              → job.yaml
  queue_records     → queue_record.yaml
  results           → result.yaml
  artifact_verifications → artifact_verification.yaml
"""

import os
import sqlite3
from pathlib import Path

_default_root = Path(__file__).parent.parent
RUNTIME_ROOT  = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH       = RUNTIME_ROOT / "db" / "queue.db"


def _ensure_column(
    con: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    existing = {
        row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def init_db():
    # A fresh rig checkout has no db/ yet; sqlite3.connect will not create it.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;

    -- -----------------------------------------------------------------------
    -- events: normalized intake objects
    -- Raw webhook payloads are never stored here. Only normalized events.
    -- -----------------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS events (
        event_id                TEXT PRIMARY KEY,
        schema_version          TEXT NOT NULL DEFAULT '1.0',
        received_at             TEXT NOT NULL,
        source                  TEXT NOT NULL,           -- github | transcript | manual
        event_type              TEXT NOT NULL,           -- pull_request.opened | issue.opened | etc.
        actor                   TEXT,
        branch                  TEXT,
        base_branch             TEXT,
        pr_number               INTEGER,
        issue_number            INTEGER,
        commit_sha              TEXT,
        url                     TEXT,
        repo                    TEXT,                   -- owner/name from webhook payload
        project_id              TEXT,
        project_node_candidates TEXT,                   -- JSON array
        scope_status            TEXT DEFAULT 'pending', -- pending | in_scope | out_of_scope
        priority                TEXT DEFAULT 'pending', -- pending | low | medium | high | critical
        risk_level              TEXT DEFAULT 'pending', -- pending | low | medium | high
        raw_payload_path        TEXT,
        normalized_payload_path TEXT,
        classification          TEXT,                   -- JSON object (category, intent, flags)
        routing                 TEXT,                   -- JSON object (selected_executor, selected_queue)
        status                  TEXT DEFAULT 'received', -- received | classified | mapped | ignored
        claimed_at              TEXT
    );

    -- -----------------------------------------------------------------------
    -- jobs: bounded work packets
    -- One event can create zero, one, or multiple jobs.
    -- -----------------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS jobs (
        job_id              TEXT PRIMARY KEY,
        schema_version      TEXT NOT NULL DEFAULT '1.0',
        created_at          TEXT NOT NULL,
        event_id            TEXT,
        project_id          TEXT,
        repo                TEXT,
        node_id             TEXT NOT NULL,
        job_type            TEXT NOT NULL,              -- implementation | review | reasoning | context_update
        executor            TEXT NOT NULL,              -- jules | vertex | pi_worker | vm_worker | human
        queue_state         TEXT DEFAULT 'ready',       -- matches queue_record states
        title               TEXT NOT NULL,
        goal                TEXT NOT NULL,
        why                 TEXT,
        source_context      TEXT,                       -- JSON object
        constraints         TEXT,                       -- JSON array
        acceptance_criteria TEXT,                       -- JSON array
        dependencies        TEXT,                       -- JSON array
        priority            TEXT DEFAULT 'medium',
        risk_level          TEXT DEFAULT 'low',
        estimated_effort    TEXT DEFAULT 'medium',
        status              TEXT DEFAULT 'ready',       -- ready | running | awaiting_result | awaiting_review | complete | failed
        attempt             INTEGER DEFAULT 0,
        max_attempts        INTEGER DEFAULT 3,
        artifacts_dir       TEXT,
        required_artifacts  TEXT NOT NULL DEFAULT '[]',
        previous_findings   TEXT,
        result_summary_path TEXT,
        FOREIGN KEY(event_id) REFERENCES events(event_id)
    );

    -- -----------------------------------------------------------------------
    -- queue_records: lifecycle tracking with leasing
    -- Prevents two workers from picking up the same job.
    -- -----------------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS queue_records (
        queue_item_id   TEXT PRIMARY KEY,
        schema_version  TEXT NOT NULL DEFAULT '1.0',
        job_id          TEXT NOT NULL,
        queue           TEXT NOT NULL,                  -- see queue state values in queue_record.yaml
        available_at    TEXT NOT NULL,
        lease_owner     TEXT,                           -- null | worker_id
        lease_expires_at TEXT,                          -- null | ISO timestamp
        retry_count     INTEGER DEFAULT 0,
        last_error      TEXT,
        FOREIGN KEY(job_id) REFERENCES jobs(job_id)
    );

    -- -----------------------------------------------------------------------
    -- results: unified executor return contract
    -- Downstream stages do not care which executor produced the result.
    -- -----------------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS results (
        result_id                   TEXT PRIMARY KEY,
        schema_version              TEXT NOT NULL DEFAULT '1.0',
        job_id                      TEXT NOT NULL,
        executor                    TEXT NOT NULL,
        received_at                 TEXT NOT NULL,
        execution_duration_seconds  INTEGER,
        outcome                     TEXT NOT NULL,      -- success | failure | partial | error
        status                      TEXT NOT NULL,      -- completed | failed | needs_review
        changed_files               TEXT,               -- JSON array
        patch_path                  TEXT,
        summary_path                TEXT,
        logs_path                   TEXT,
        acceptance_check            TEXT,               -- JSON object: criterion -> pass|fail|untested
        risks                       TEXT,               -- JSON array
        followup_candidates         TEXT,               -- JSON array of node_ids
        github_action               TEXT,               -- JSON object
        FOREIGN KEY(job_id) REFERENCES jobs(job_id)
    );

    -- -----------------------------------------------------------------------
    -- artifact_verifications: gate before node advancement
    -- All required_artifacts in a node must verify before node → complete.
    -- -----------------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS artifact_verifications (
        verification_id     TEXT PRIMARY KEY,
        schema_version      TEXT NOT NULL DEFAULT '1.0',
        job_id              TEXT NOT NULL,
        node_id             TEXT NOT NULL,
        artifact_type       TEXT NOT NULL,              -- decision.md | result-summary.md | patch.diff | merged_pr | etc.
        validation_method   TEXT NOT NULL,              -- file_exists | content_check | github_api_check | human_audit
        verified            INTEGER NOT NULL DEFAULT 0, -- 0 | 1
        verified_at         TEXT,
        verified_by         TEXT,                       -- runtime_validator | human | codex_reviewer
        notes               TEXT,
        FOREIGN KEY(job_id) REFERENCES jobs(job_id)
    );

    -- -----------------------------------------------------------------------
    -- decision_results: records from the runtime decision loop.
    -- Distinct from `results` (which holds merged-PR receipts and FKs to jobs).
    -- A decision can be a no_op or a stale-state clean that has no associated
    -- job, so this table intentionally has NO foreign key to jobs.
    -- -----------------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS decision_results (
        result_id           TEXT PRIMARY KEY,
        schema_version      TEXT NOT NULL DEFAULT '1.0',
        action              TEXT NOT NULL,              -- dispatch_next | escalate | review_pr | accept_node | no_op
        node_id             TEXT,                       -- nullable: no_op/escalate may have no node
        project_id          TEXT,
        reason              TEXT,
        created_at          TEXT NOT NULL
    );

    -- -----------------------------------------------------------------------
    -- executor_sessions: tracks remote executor sessions (Jules CLI, etc.)
    -- One job can have multiple sessions (retries, parallel candidates).
    -- -----------------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS executor_sessions (
        session_db_id              TEXT PRIMARY KEY,
        job_id                     TEXT NOT NULL,
        executor                   TEXT NOT NULL,      -- jules_cli | jules_api | droid | etc.
        session_id                 TEXT NOT NULL,      -- executor-specific ID
        state                      TEXT DEFAULT 'dispatched', -- dispatched | running | needs_operator | completed | failed | collected | evaluated
        execution_attempt_id       TEXT NOT NULL,
        attempt_index              INTEGER NOT NULL,
        expected_base_commit_sha   TEXT,               -- commit visible at dispatch time
        result_commit_sha          TEXT,               -- commit after patch application (set by runtime)
        patch_path                 TEXT,               -- path to retrieved patch file
        completion_id              TEXT,               -- stable executor completion identity
        completion_digest_sha256   TEXT,               -- digest binding normalized completion evidence
        completion_quarantine_reason TEXT,             -- evidence conflict requiring human review
        evidence_manifest_path     TEXT,               -- per-node evidence manifest
        error                      TEXT,
        created_at                 TEXT NOT NULL,
        updated_at                 TEXT NOT NULL,
        FOREIGN KEY(job_id) REFERENCES jobs(job_id)
    );
    """)

    # CREATE TABLE IF NOT EXISTS does not add columns to existing databases.
    # These migrations are idempotent and preserve every historical row.
    _ensure_column(con, "events", "claimed_at", "TEXT")
    _ensure_column(con, "events", "repo", "TEXT")
    _ensure_column(
        con,
        "jobs",
        "required_artifacts",
        "TEXT NOT NULL DEFAULT '[]'",
    )
    _ensure_column(con, "jobs", "previous_findings", "TEXT")
    _ensure_column(con, "jobs", "plumbing_attempt", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "executor_sessions", "execution_attempt_id", "TEXT")
    _ensure_column(con, "executor_sessions", "attempt_index", "INTEGER")
    _ensure_column(con, "executor_sessions", "completion_id", "TEXT")
    _ensure_column(
        con,
        "executor_sessions",
        "completion_digest_sha256",
        "TEXT",
    )
    _ensure_column(
        con,
        "executor_sessions",
        "completion_quarantine_reason",
        "TEXT",
    )
    _ensure_column(
        con,
        "executor_sessions",
        "evidence_manifest_path",
        "TEXT",
    )

    # Old session rows predate first-class attempt identity. Their durable
    # creation order is the only available attempt ordering, so backfill it
    # deterministically without changing executor session IDs or state.
    con.execute(
        """
        UPDATE executor_sessions AS current
           SET attempt_index = (
               SELECT COUNT(*) - 1
                 FROM executor_sessions AS prior
                WHERE prior.job_id = current.job_id
                  AND (
                      prior.created_at < current.created_at
                      OR (
                          prior.created_at = current.created_at
                          AND prior.session_db_id <= current.session_db_id
                      )
                  )
           )
         WHERE attempt_index IS NULL
        """
    )
    con.execute(
        """
        UPDATE executor_sessions
           SET execution_attempt_id =
               job_id || ':attempt:' || CAST(attempt_index AS TEXT)
         WHERE execution_attempt_id IS NULL
        """
    )
    con.execute(
        """CREATE INDEX IF NOT EXISTS
           idx_executor_sessions_execution_attempt_id
           ON executor_sessions(execution_attempt_id)"""
    )
    con.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS
           idx_executor_sessions_completion_id_unique
           ON executor_sessions(completion_id)
           WHERE completion_id IS NOT NULL"""
    )

    con.commit()
    con.close()
    print(f"Initialized: {DB_PATH}")
    print("Tables: events, jobs, queue_records, results, artifact_verifications, decision_results, executor_sessions")


if __name__ == "__main__":
    init_db()
