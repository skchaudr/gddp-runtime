# SQLite data models

`/Users/sab-mini/repos/gddp-runtime/scripts/init_db.py` initializes `db/queue.db`, enables WAL and foreign keys, and applies additive migrations for historical databases. JSON-shaped values are stored as text where noted.

## `events`

Normalized ingress records. Important fields include `event_id`, timestamps, source/type, actor and GitHub coordinates, repository/project, candidate nodes, scope/priority/risk, raw and normalized artifact paths, classification/routing JSON, status, and `claimed_at`. Raw payload bodies live on disk under `events/raw/`, not in this table.

## `jobs`

Bounded attempts derived from nodes. Stores project/repository/node, executor and job type, title/goal/context, constraints and criteria, dependencies, risk/priority/effort, queue and job statuses, retry counters, artifact paths, required artifacts, and previous findings. `event_id` references `events`.

`plumbing_attempt` is added by migration for infrastructure retries separately from the authored work.

## `queue_records`

Queue lifecycle and leasing: `queue_item_id`, `job_id`, queue, availability, lease owner/expiry, retry count, and last error. The lease prevents two workers claiming one job. `job_id` references `jobs`.

## `results`

Executor return and evaluator-review records: outcome/status, changed files, patch/summary/log paths, acceptance-check JSON, risks, follow-up candidates, and GitHub action metadata. The table is executor-neutral and references `jobs`.

## `artifact_verifications`

Required-artifact evidence keyed by verification ID, job and node. Records artifact type, validation method, verified flag/time/actor, and notes. Despite historical comments about advancement, verification is evidence; only a human accepts graph completion.

## `decision_results`

Audited runtime/operator decisions, including action, optional node/project, reason, and time. It intentionally has no job foreign key because no-op and stale-state decisions may not have a job.

## `executor_sessions`

One row per executor attempt. It stores executor/session identity, state, `execution_attempt_id`, attempt index, expected base and result commit SHAs, patch path, stable completion ID and digest, quarantine reason, evidence manifest, errors, and timestamps.

Important constraints:

- Index on `execution_attempt_id`.
- Partial unique index on non-null `completion_id`.
- Historical rows are deterministically backfilled with attempt index and `<job-id>:attempt:<index>` identity.
- Completion conflicts and mission-integrity failures are retained in `completion_quarantine_reason` for human review.

## Relationships

`events` may produce many `jobs`. Each job has queue records, results, artifact verifications, and executor sessions. `decision_results` is a separate audit stream. None of these tables is graph truth; graph YAML remains in `gddp-config`.
