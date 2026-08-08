# State persistence

> Restored from the 2026-07-13 wiki. The table inventory and lifecycle details may lag the current schema; cross-check them against [Intake and control plane](intake-and-control-plane.md) and `scripts/init_db.py`.

The runtime persists every step of its loop in SQLite. Seven tables hold normalized events, bounded job packets, lease-backed queue records, executor receipts, artifact verifications, decision-loop outcomes, and durable executor sessions. Nothing about graph truth lives here; this is execution machinery state only. Graph truth stays in `gddp-config` YAML, and humans are the only ones who move a node to complete.

The database file lives at `db/queue.db` under the runtime root, resolved from `GDDP_RUNTIME_ROOT` (with `OPCLAW_ROOT` kept as a legacy fallback). The repo root is the default. The `db/` directory is git-ignored because it is runtime state, not source.

## Initialization

`scripts/init_db.py` is the canonical schema owner. Running it once creates all six tables with `CREATE TABLE IF NOT EXISTS`, sets `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`, and prints the table list on success. Idempotent: safe to run from any state, fresh or upgrade.

### WAL and foreign keys

Two pragmas run before any DDL:

- `journal_mode=WAL` lets readers and the writer coexist without blocking, which matters because the heartbeat dispatch loop and the return router both touch `queue.db` concurrently.
- `foreign_keys=ON` enforces the relationships below. SQLite ships with foreign keys off by default, so this pragma is mandatory, not decorative.

## The seven tables

### events

Normalized intake objects. Raw webhook payloads are never stored here; only the normalized event that the intake server produced.

| Column | Type | Notes |
|---|---|---|
| `event_id` | TEXT PK | Runtime-assigned |
| `schema_version` | TEXT | Defaults to `1.0` |
| `received_at` | TEXT | ISO timestamp |
| `source` | TEXT | `github` / `transcript` / `manual` |
| `event_type` | TEXT | `pull_request.opened`, `issue.opened`, etc. |
| `actor`, `branch`, `base_branch` | TEXT | Webhook context |
| `pr_number`, `issue_number` | INTEGER | GitHub identifiers |
| `commit_sha`, `url`, `repo` | TEXT | `repo` is `owner/name` from the payload |
| `project_id` | TEXT | Set during classification |
| `project_node_candidates` | TEXT | JSON array |
| `scope_status` | TEXT | `pending` / `in_scope` / `out_of_scope` |
| `priority` | TEXT | `pending` / `low` / `medium` / `high` / `critical` |
| `risk_level` | TEXT | `pending` / `low` / `medium` / `high` |
| `raw_payload_path`, `normalized_payload_path` | TEXT | Disk paths for audit |
| `classification` | TEXT | JSON object: category, intent, flags |
| `routing` | TEXT | JSON object: selected_executor, selected_queue |
| `status` | TEXT | `received` / `classified` / `mapped` / `ignored` |
| `claimed_at` | TEXT | Lease timestamp for atomic event claims |

### jobs

Bounded work packets. One event can produce zero, one, or many jobs.

| Column | Type | Notes |
|---|---|---|
| `job_id` | TEXT PK | |
| `event_id` | TEXT | FK to `events(event_id)` |
| `project_id`, `repo`, `node_id` | TEXT | Graph context |
| `job_type` | TEXT | `implementation` / `review` / `reasoning` / `context_update` |
| `executor` | TEXT | `jules` / `vertex` / `pi_worker` / `vm_worker` / `human` |
| `queue_state` | TEXT | Mirrors `queue_record` states |
| `title`, `goal`, `why` | TEXT | The packet body |
| `source_context`, `constraints`, `acceptance_criteria`, `dependencies` | TEXT | JSON |
| `priority`, `risk_level`, `estimated_effort` | TEXT | Triage fields |
| `status` | TEXT | `ready` / `running` / `awaiting_result` / `awaiting_review` / `complete` / `failed` |
| `attempt`, `max_attempts` | INTEGER | Retry budget, default 3 |
| `artifacts_dir`, `result_summary_path` | TEXT | Output paths |

### queue_records

Lifecycle tracking with leasing, so two workers cannot pick up the same job.

| Column | Type | Notes |
|---|---|---|
| `queue_item_id` | TEXT PK | |
| `job_id` | TEXT | FK to `jobs(job_id)` |
| `queue` | TEXT | Queue name |
| `available_at` | TEXT | When the item becomes eligible |
| `lease_owner` | TEXT | `null` or worker id |
| `lease_expires_at` | TEXT | `null` or ISO timestamp |
| `retry_count` | INTEGER | |
| `last_error` | TEXT | |

### results

The unified executor return contract. Downstream stages do not care which executor produced the row.

| Column | Type | Notes |
|---|---|---|
| `result_id` | TEXT PK | |
| `job_id` | TEXT | FK to `jobs(job_id)` |
| `executor` | TEXT | |
| `received_at` | TEXT | |
| `execution_duration_seconds` | INTEGER | |
| `outcome` | TEXT | `success` / `failure` / `partial` / `error` |
| `status` | TEXT | `completed` / `failed` / `needs_review` |
| `changed_files` | TEXT | JSON array |
| `patch_path`, `summary_path`, `logs_path` | TEXT | Artifact paths |
| `acceptance_check` | TEXT | JSON: criterion to `pass` / `fail` / `untested` |
| `risks` | TEXT | JSON array |
| `followup_candidates` | TEXT | JSON array of node ids |
| `github_action` | TEXT | JSON object |

### artifact_verifications

Gate before node advancement. Every `required_artifacts` entry on a node must verify before that node can move to complete.

| Column | Type | Notes |
|---|---|---|
| `verification_id` | TEXT PK | |
| `job_id` | TEXT | FK to `jobs(job_id)` |
| `node_id` | TEXT | |
| `artifact_type` | TEXT | `decision.md`, `result-summary.md`, `patch.diff`, `merged_pr`, etc. |
| `validation_method` | TEXT | `file_exists` / `content_check` / `github_api_check` / `human_audit` |
| `verified` | INTEGER | 0 or 1 |
| `verified_at` | TEXT | |
| `verified_by` | TEXT | `runtime_validator` / `human` / `codex_reviewer` |
| `notes` | TEXT | |

### decision_results

Records from the runtime decision loop. Deliberately has no foreign key to `jobs`, because a decision can be a `no_op` or a stale-state clean that has no associated job.

| Column | Type | Notes |
|---|---|---|
| `result_id` | TEXT PK | |
| `action` | TEXT | `dispatch_next` / `escalate` / `review_pr` / `accept_node` / `no_op` |
| `node_id` | TEXT | Nullable; `no_op` and `escalate` may have no node |
| `project_id` | TEXT | |
| `reason` | TEXT | |
| `created_at` | TEXT | |

### executor_sessions

Durable adapter-session and attempt identity. One job may have multiple sessions across work retries, plumbing replacements, or engagement fan-out.

| Column | Type | Notes |
|---|---|---|
| `session_db_id` | TEXT PK | Runtime database identity |
| `job_id` | TEXT | FK to `jobs(job_id)` |
| `executor`, `session_id`, `state` | TEXT | Adapter identity and lifecycle |
| `execution_attempt_id`, `attempt_index` | TEXT / INTEGER | Stable attempt binding |
| `expected_base_commit_sha`, `result_commit_sha` | TEXT | Git subject boundaries |
| `patch_path`, `evidence_manifest_path` | TEXT | Collected evidence locations |
| `completion_id`, `completion_digest_sha256` | TEXT | Replay and conflict identity |
| `completion_quarantine_reason`, `error` | TEXT | Human-review routing evidence |
| `created_at`, `updated_at` | TEXT | Durable timestamps |

## Relationships

```
events 1──* jobs 1──* queue_records
              │
              ├──* results
              ├──* artifact_verifications
              ├──* executor_sessions
              │
decision_results  (standalone, no FK)
```

`events` is the entry point. `jobs` references `events`. `queue_records`, `results`, `artifact_verifications`, and `executor_sessions` all reference `jobs`. `decision_results` stands alone by design, so the decision loop can record `no_op` and `escalate` actions even when no job is in flight.

## Migration pattern

`CREATE TABLE IF NOT EXISTS` never adds columns to an existing table, so `init_db.py` does additive migrations with explicit `ALTER TABLE` statements wrapped in `try/except sqlite3.OperationalError`. The `except` covers both "column already exists" and "table missing", which keeps `init_db` safe to run from any state, fresh or upgrade. Two such migrations are currently in place:

- `ALTER TABLE events ADD COLUMN claimed_at TEXT`
- `ALTER TABLE events ADD COLUMN repo TEXT`

There is no migration framework, no version table, no down migrations. The pattern is: add the column to the canonical `CREATE TABLE` for fresh installs, and append a guarded `ALTER TABLE` for upgrades. Anything that needs a rewrite is handled by dropping and reinitializing `queue.db`, which is acceptable because the database is runtime state, not source of truth.

## results_store.py

`scripts/runtime/results_store.py` is the persistence helper for review receipts and decision outcomes. It does not touch graph truth; it writes structured rows into the two tables that record what came back and what the loop decided.

### write_result

Inserts or updates a row in `results`. It calls `init_db()` first to ensure the table exists (defensive against partial setups), then checks whether `result_id` is already present. If not, it inserts. If yes, it updates every column in place. This makes it safe to call from idempotent retry paths, including replay, without producing duplicate receipts.

JSON-shaped columns (`changed_files`, `acceptance_check`, `risks`, `followup_candidates`, `github_action`) are normalized through `_json_or_none`, which passes strings through and `json.dumps` everything else. `received_at` defaults to `datetime.now(timezone.utc).isoformat()` when not supplied.

### write_decision_result

Inserts a row into `decision_results`. Calls `init_decision_results()` first to ensure the table exists, then writes `result_id`, `action`, `node_id`, `project_id`, `reason`, and a UTC `created_at`. No foreign key to `jobs`, on purpose, so `no_op` and `escalate` decisions with no associated job still get recorded.

## Key source files

| File | Role |
|---|---|
| `scripts/init_db.py` | Canonical schema, seven tables, pragmas, additive migrations |
| `scripts/runtime/results_store.py` | `write_result`, `write_decision_result`, table bootstrapping |

## Related pages

- [overview/architecture.md](../overview/architecture.md) for how persistence fits the wider system flow
- [systems/return-router.md](return-router.md) for who calls `write_result`
- [systems/verification.md](verification.md) for how `artifact_verifications` get produced
- [systems/replay.md](replay.md) for reprocessing persisted state
