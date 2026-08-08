# Tooling

Operator and developer tooling for `gddp-runtime`. The emphasis is on durable state: SQLite, spool files, receipts. Most tools read or mutate that state; none of them write graph truth.

## `init_db.py`

```bash
python3 scripts/init_db.py
```

Creates or migrates `db/queue.db` with the current schema: `events`, `jobs`, `queue_records`, `results`, `decision_results`, `executor_sessions`, and related tables. Safe to run multiple times; it applies only the missing migrations.

Runtime state directories (`db/`, `jobs/`, `events/`) are gitignored. Do not commit them.

## `jobs_status.py`

```bash
python3 scripts/jobs_status.py show
```

The operator backend for runtime job reads and writes. It may update job and queue state. It must never update graph or node status in `gddp-config`.

Subcommands and modes vary; the primary use is `show` for a snapshot of recent jobs, their state, and the associated node IDs. The evaluator integration (`test_jobs_status_evaluator.py`) exercises the evaluator-facing surface.

## `replay.py`

```bash
python3 -m runtime.replay --result-id res_20260312T21053737
python3 -m runtime.replay --job-id job_20260312T21053737
```

Replays failed or partial runtime steps from persisted state.

- `--result-id` re-runs the return router logic (`handle_merged_pr`) for the event associated with the result. Recreates the review receipt and state routing.
- `--job-id` re-dispatches the specific job to its assigned executor (e.g., Jules). Requires explicit operator confirmation to prevent accidental re-dispatches.

What is not replayed: initial webhook intake (events are read from the DB, not re-received), classification, and scoping (uses the persisted job/event context).

Treat job redispatch as manual tooling; it bypasses some modern reservation bookkeeping.

## `rollback.py`

```bash
python3 scripts/rollback.py --job job_20260312T21053737
```

Reverts a job and restores node state. Steps:

1. Shows current state of the job.
2. Confirms with the operator before making changes.
3. Reverts the job to `failed`, queue record to `cancelled`.
4. Prints what would need to happen on the graph side (node stays as-is).
5. Logs the rollback to the job's `decision.md`.

Use this when a job needs to be unwound and retried from scratch. It does not touch `gddp-config`; graph truth remains with the human.

## `gddp_node_receipt.py`

```bash
python3 scripts/gddp_node_receipt.py ...
```

CLI for the GDDP node receipt protocol. The receipt is the structured evidence returned by the executor adapter after an attempt. It records the node ID, attempt ID, commit ref, patch hash, and outcome.

Tests in `scripts/test_gddp_node_receipt.py` exercise the protocol.

## Deploy scripts

### Mini-heartbeat kit

The canonical operator path for arming the heartbeat on `sab-mini` and Linux hosts:

```bash
# Dry checks (no arm)
bash deploy/mini-heartbeat/bin/smoke.sh

# Arm (sets up launchd or systemd, sources env)
MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh

# Disarm
bash deploy/mini-heartbeat/bin/disarm.sh
```

`common.sh` sources `deploy/mini-heartbeat/env/gddp.env` which sets `GDDP_LOCAL_SUBPROCESS_ARGV`, `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR`, and other runtime env. This is why the operator path requires the kit: raw runner calls skip the env and create failed jobs before any executor launches.

Other scripts in the kit:

- `baseline.sh` — health checks and state inspection.
- `idle_shutdown.py` — 3-hour idle shutdown logic (systemd unit files in the same dir).
- `install-dormant.sh` — install but do not arm.
- `watch-dispatch.sh` — watch dispatch logs in real time.
- `shell-aliases.sh` — operator convenience aliases.

Fresh Linux hosts should follow [`deploy/mini-heartbeat/FRESH-HOST-STANDUP.md`](../../deploy/mini-heartbeat/FRESH-HOST-STANDUP.md).

### Rig1 heartbeat

```bash
deploy/rig1-heartbeat/
```

Legacy rig topology. Check the README in that directory before using; the mini-heartbeat kit is the current standard.

## `setup.sh`

```bash
bash setup.sh
```

Light host check: verifies Python, Flask, and script presence. Prefer an explicit venv for repeatable work. `setup.sh` is a sanity check, not an installer.

## `gddp` CLI (from `gddp-config`)

The `gddp` CLI lives in the `gddp-config` repo, not `gddp-runtime`. It reads graph YAML, project config, and node definitions. Runtime does not invoke it directly; the two repos are split by design.

When debugging graph resolution:

- `GDDP_CONFIG_PATH` points to the `gddp-config` checkout.
- `scripts/runtime/repo_resolver.py` resolves the project ID from `project.yaml`'s `repo:` field, not the checkout directory name.
- The graph reader caches YAML; if you edit `gddp-config` and the runtime does not see it, clear the cache or restart the heartbeat.

## Smoke, arm, disarm

The mini-heartbeat kit provides three entry points:

- `smoke.sh` — dry checks. Verifies env, DB presence, and script layout without arming. Run this before arming to catch configuration errors.
- `arm.sh` — arms the heartbeat. Sets up launchd (macOS) or systemd (Linux) units, sources the env, and starts the tick. Requires `MINI_HEARTBEAT_ARM=1` to proceed.
- `disarm.sh` — disarms the heartbeat. Stops the units and removes them.

The arm script refuses to arm if the smoke check fails. This is intentional; do not bypass it.

## Replay and rollback

Both tools operate on persisted SQLite state. They do not re-receive webhooks or re-classify events. Use them when:

- A job failed and you want to re-dispatch without re-intaking the event.
- A result was partially processed and you want to re-run the return router.
- A job needs to be unwound and retried from scratch.

Both tools require explicit confirmation before mutating state. They log their actions to the job's `decision.md` for audit.

## Database tools

`db/queue.db` is a SQLite WAL database. Standard SQLite tools work:

```bash
sqlite3 db/queue.db ".tables"
sqlite3 db/queue.db "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 10;"
```

Do not copy `queue.db` while writers are running. Use SQLite online backup after quiescing writers:

```bash
sqlite3 db/queue.db ".backup '/path/to/backup.db'"
```

Or stop the heartbeat, copy, and restart.

## Related

- [Development workflow](development-workflow.md) — definition of done
- [Testing](testing.md) — what to run before claiming done
- [Debugging](debugging.md) — common failures and log locations
- [Patterns and conventions](patterns-and-conventions.md) — hard boundaries
- [Deployment](../deployment/index.md) — production topology
- [Overview — getting started](../overview/getting-started.md) — install, DB, first smoke
