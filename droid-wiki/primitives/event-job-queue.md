# Event, Job, Queue Record

These three primitives form the intake and work-tracking pipeline. An event triggers job creation; a queue record tracks the job's lifecycle with leasing to prevent double-dispatch.

## Event

An **event** is a normalized intake object from an external source (GitHub webhook, manual trigger, transcript).

### Schema (queue.db `events` table)

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | `TEXT PRIMARY KEY` | Unique event identifier |
| `schema_version` | `TEXT` | Schema version (default `1.0`) |
| `received_at` | `TEXT` | ISO timestamp of receipt |
| `source` | `TEXT` | Origin: `github`, `transcript`, `manual` |
| `event_type` | `TEXT` | Specific event (e.g., `pull_request.opened`) |
| `actor` | `TEXT` | Who triggered the event |
| `branch` | `TEXT` | Source branch (for PRs) |
| `base_branch` | `TEXT` | Target branch (for PRs) |
| `pr_number` | `INTEGER` | PR number (if applicable) |
| `issue_number` | `INTEGER` | Issue number (if applicable) |
| `commit_sha` | `TEXT` | Commit SHA (if applicable) |
| `url` | `TEXT` | External URL |
| `repo` | `TEXT` | Repository (owner/name) |
| `project_id` | `TEXT` | Associated project |
| `project_node_candidates` | `TEXT` | JSON array of candidate nodes |
| `scope_status` | `TEXT` | `pending`, `in_scope`, `out_of_scope` |
| `priority` | `TEXT` | `pending`, `low`, `medium`, `high`, `critical` |
| `risk_level` | `TEXT` | `pending`, `low`, `medium`, `high` |
| `raw_payload_path` | `TEXT` | Path to raw webhook payload |
| `normalized_payload_path` | `TEXT` | Path to normalized payload |
| `classification` | `TEXT` | JSON object (category, intent, flags) |
| `routing` | `TEXT` | JSON object (selected_executor, selected_queue) |
| `status` | `TEXT` | `received`, `classified`, `mapped`, `ignored` |
| `claimed_at` | `TEXT` | When this event was claimed for processing |

**Source:** `scripts/init_db.py` (events table, lines ~30-60)

### Event Lifecycle

```
received → classified → mapped → (jobs created)
              ↓
          ignored (if out of scope)
```

### Producers

- **Intake server** (`scripts/intake_server.py`) — receives webhooks, creates events
- **Manual trigger** — operator creates events via CLI

### Consumers

- **Scope checker** — classifies events as in/out of scope
- **Job creator** — maps events to jobs

---

## Job

A **job** is a bounded work packet derived from one or more events. Jobs are executor-neutral — they describe *what* to do, not *how*.

### Schema (queue.db `jobs` table)

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | `TEXT PRIMARY KEY` | Unique job identifier |
| `schema_version` | `TEXT` | Schema version (default `1.0`) |
| `created_at` | `TEXT` | ISO timestamp of creation |
| `event_id` | `TEXT` | Source event (FK to events) |
| `project_id` | `TEXT` | Associated project |
| `repo` | `TEXT` | Repository (owner/name) |
| `node_id` | `TEXT NOT NULL` | Target node |
| `job_type` | `TEXT NOT NULL` | `implementation`, `review`, `reasoning`, `context_update` |
| `executor` | `TEXT NOT NULL` | Selected executor (e.g., `jules`, `droid`) |
| `queue_state` | `TEXT` | Matches queue_record states |
| `title` | `TEXT NOT NULL` | Human-readable title |
| `goal` | `TEXT NOT NULL` | What this job must accomplish |
| `why` | `TEXT` | Rationale |
| `source_context` | `TEXT` | JSON object (context for executor) |
| `constraints` | `TEXT` | JSON array (hard boundaries) |
| `acceptance_criteria` | `TEXT` | JSON array (what must be true) |
| `dependencies` | `TEXT` | JSON array (node IDs) |
| `priority` | `TEXT` | `low`, `medium`, `high` (default `medium`) |
| `risk_level` | `TEXT` | `low`, `medium`, `high` (default `low`) |
| `estimated_effort` | `TEXT` | `low`, `medium`, `high` (default `medium`) |
| `status` | `TEXT` | `ready`, `running`, `awaiting_result`, `awaiting_review`, `complete`, `failed` |
| `attempt` | `INTEGER` | Current attempt number (default 0) |
| `max_attempts` | `INTEGER` | Max retries (default 3) |
| `artifacts_dir` | `TEXT` | Path to artifacts directory |
| `required_artifacts` | `TEXT` | JSON array (must exist before acceptance) |
| `previous_findings` | `TEXT` | JSON object (evaluator findings from prior attempts) |
| `result_summary_path` | `TEXT` | Path to result summary |

**Source:** `scripts/init_db.py` (jobs table, lines ~65-100)

### Job Lifecycle

```
ready → running → awaiting_result → awaiting_review → complete
   ↓         ↓           ↓               ↓
 failed  failed      failed         failed (if evaluator fails)
```

**Retry behavior:**

- `attempt` increments on each retry
- `previous_findings` carries evaluator feedback to the next attempt
- `max_attempts` bounds retries (default 3)

### Job Status vs. Node Status

**Critical distinction:**

- **Job status** = runtime execution state (queue.db)
- **Node status** = graph truth (gddp-config YAML)

A job can be `complete` while the node remains `provisional` (awaiting human review). The runtime never marks a node `complete`; only the human does.

### Producers

- **Job creator** — maps events to jobs
- **Retry allocator** — creates retry jobs with previous findings

### Consumers

- **Dispatcher** — creates NodePackets from jobs
- **Reconciler** — tracks job status through executor lifecycle

---

## Queue Record

A **queue record** tracks a job's lifecycle with leasing to prevent two workers from picking up the same job.

### Schema (queue.db `queue_records` table)

| Field | Type | Description |
|-------|------|-------------|
| `queue_item_id` | `TEXT PRIMARY KEY` | Unique queue item identifier |
| `schema_version` | `TEXT` | Schema version (default `1.0`) |
| `job_id` | `TEXT NOT NULL` | Associated job (FK to jobs) |
| `queue` | `TEXT NOT NULL` | Current queue state (see below) |
| `available_at` | `TEXT NOT NULL` | When this job becomes available |
| `lease_owner` | `TEXT` | Worker ID holding the lease (null if unleased) |
| `lease_expires_at` | `TEXT` | When the lease expires (ISO timestamp) |
| `retry_count` | `INTEGER` | Number of retries (default 0) |
| `last_error` | `TEXT` | Last error message |

**Source:** `scripts/init_db.py` (queue_records table, lines ~105-120)

### Queue States

| State | Meaning |
|-------|---------|
| `ready` | Available for dispatch |
| `leased` | Worker claimed this job |
| `dispatching` | Worker is sending to executor |
| `running` | Executor is working |
| `awaiting_result` | Executor completed, collecting artifacts |
| `awaiting_review` | Evaluator queued or in progress |
| `complete` | Job finished |
| `failed` | Job failed (error or max attempts) |
| `cancelled` | Job cancelled by operator |

### Leasing Protocol

1. Worker queries for `ready` jobs where `available_at <= now()`
2. Worker attempts to lease: `UPDATE ... SET lease_owner = ?, lease_expires_at = ? WHERE queue_item_id = ? AND lease_owner IS NULL`
3. If lease succeeds, worker dispatches the job
4. If lease fails (another worker got it), worker moves to next job
5. Lease expires after timeout; job returns to `ready`

**Purpose:** Prevents double-dispatch in concurrent environments.

### Producers

- **Job creator** — creates queue records for new jobs
- **Lease manager** — updates lease state

### Consumers

- **Dispatcher** — leases and dispatches jobs
- **Reconciler** — updates queue state through lifecycle

---

## Relationships

```
Event (1) → (0..*) Job
Job (1) → (1) Queue Record
Job (1) → (0..*) Executor Session
Job (1) → (0..*) Result
```

## Systems That Produce/Consume

### Event Producers

- `scripts/intake_server.py` — webhook intake
- Manual CLI triggers

### Event Consumers

- `scripts/runtime/intake/scope_checker.py` — classification
- `scripts/runtime/intake/job_creator.py` — job creation

### Job Producers

- `scripts/runtime/intake/job_creator.py` — event → job mapping
- `scripts/runtime/heartbeat/state_recorder.py` — retry allocation

### Job Consumers

- `scripts/runtime/heartbeat/dispatcher.py` — job → NodePacket
- `scripts/runtime/heartbeat/reconciler.py` — lifecycle tracking

### Queue Record Producers

- `scripts/runtime/intake/job_creator.py` — creates queue records
- `scripts/runtime/heartbeat/state_recorder.py` — updates queue state

### Queue Record Consumers

- `scripts/runtime/heartbeat/dispatcher.py` — leases and dispatches

## Key Invariants

1. One event can create zero, one, or multiple jobs
2. Queue records prevent double-dispatch via leasing
3. Job status is runtime state; node status is graph truth
4. Retries carry previous findings to the next attempt
5. Lease expiration returns jobs to `ready` for re-dispatch
