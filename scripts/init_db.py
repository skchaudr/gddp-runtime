"""
init_db.py — Initialize queue.db with tables matching Phase 0 schemas.

Tables mirror the YAML schemas in gddp-config/schemas/v1/:
  events            → event.yaml
  jobs              → job.yaml
  queue_records     → queue_record.yaml
  results           → result.yaml
  artifact_verifications → artifact_verification.yaml
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "queue.db"


def init_db():
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
        status              TEXT DEFAULT 'ready',       -- mirrors queue_state for job lifecycle
        attempt             INTEGER DEFAULT 0,
        max_attempts        INTEGER DEFAULT 3,
        artifacts_dir       TEXT,
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
    """)

    # One-time migration: add claimed_at to pre-existing events tables.
    # CREATE TABLE IF NOT EXISTS never adds columns to an existing table, so
    # databases created before the claimed_at column was in the canonical schema
    # need an explicit ALTER TABLE. try/except handles both "already exists" and
    # "table missing" so init_db is safe to run from any state.
    try:
        con.execute("ALTER TABLE events ADD COLUMN claimed_at TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        con.execute("ALTER TABLE events ADD COLUMN repo TEXT")
    except sqlite3.OperationalError:
        pass

    con.commit()
    con.close()
    print(f"Initialized: {DB_PATH}")
    print("Tables: events, jobs, queue_records, results, artifact_verifications, decision_results")


if __name__ == "__main__":
    init_db()
