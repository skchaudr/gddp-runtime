# Getting started

This page covers a local development checkout of `gddp-runtime`: prerequisites, install, database init, tests, and a safe first heartbeat smoke. Production arming uses the mini-heartbeat kit, not a raw runner invocation.

## Prerequisites

- Python 3.11+
- `git`
- A local checkout of **gddp-config** (sibling directory or `GDDP_CONFIG_PATH`)
- Optional executors for live dispatch: `droid`, GitHub token for Jules, model proxies your executor argv targets

## Clone and install

```bash
git clone <gddp-runtime-url> ~/repos/gddp-runtime
git clone <gddp-config-url> ~/repos/gddp-config
cd ~/repos/gddp-runtime

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Flask, PyYAML, Pydantic, anthropic are the declared deps.
# For gddp CLI work from config: also install rich in the config venv.
```

`setup.sh` is a light host check (python + flask + script presence). Prefer an explicit venv for repeatable work.

## Initialize SQLite

```bash
python3 scripts/init_db.py
```

This creates/migrates `db/queue.db` with `events`, `jobs`, `queue_records`, `results`, `decision_results`, `executor_sessions`, and related tables. Runtime state directories are gitignored; do not commit them.

## Run tests

Project convention:

```bash
.venv/bin/python -m pytest -q scripts
```

Focused mission suite (from the README):

```bash
.venv/bin/python -m pytest -q \
  scripts/adapters/test_mission_adapter.py \
  scripts/adapters/test_mission_projection.py \
  scripts/adapters/test_mission_evidence.py \
  scripts/adapters/test_mission_git_verify.py \
  scripts/adapters/test_mission_push_guard.py \
  scripts/runtime/heartbeat/test_mission_config.py \
  scripts/runtime/heartbeat/test_mission_reconciler.py \
  scripts/runtime/heartbeat/test_mission_pipeline_e2e.py \
  scripts/test_gddp_node_receipt.py
```

There is no configured project linter.

## Environment variables (dev)

| Variable | Purpose |
| --- | --- |
| `GDDP_CONFIG_PATH` | Path to `gddp-config` (optional if sibling to runtime) |
| `GDDP_RUNTIME_ROOT` | State root for DB/events/jobs (defaults to repo root locally) |
| `GITHUB_TOKEN` / `GH_TOKEN` | Jules issue dispatch |
| `GITHUB_WEBHOOK_SECRET` | Intake HMAC (or secret command form in deploy env) |
| `GDDP_LOCAL_SUBPROCESS_ARGV` | JSON/argv for local/Droid worker launch |
| `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` | Durable spool root for local adapters |
| `GDDP_EXECUTOR_OVERRIDE` | Reroute executor name without editing graph config |
| `GDDP_MISSION_SESSION_DIR` | Mission session durability (default `db/mission-sessions`) |
| `GDDP_FACTORY_MISSION_DIR` | Factory mission state (default `~/.factory/missions`) |
| `GDDP_INTAKE_INSECURE=1` | Dev-only intake without secret; never expose publicly |

## Local heartbeat check

Use the kit even for a one-off check:

```bash
bash deploy/mini-heartbeat/bin/smoke.sh
```

Do not invoke the runner module directly. The kit loads `gddp.env`, spool settings, and executor argv before running its bounded smoke tick.

## Mini-heartbeat kit (preferred operator path)

```bash
# Dry checks
bash deploy/mini-heartbeat/bin/smoke.sh

# Arm only when intentional
MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh

# Disarm
bash deploy/mini-heartbeat/bin/disarm.sh
```

Fresh Linux hosts should follow [`deploy/mini-heartbeat/FRESH-HOST-STANDUP.md`](../../deploy/mini-heartbeat/FRESH-HOST-STANDUP.md). Critical detail: systemd user units for the heartbeat **must** use `KillMode=process` so oneshot ticks do not reap dispatched worker process groups.

## Operator job views

Runtime job state is read and audited through `scripts/jobs_status.py` (the backend behind operator `gddp jobs` surfaces). It may update runtime job/queue rows. It must never update graph/node status in `gddp-config`.

## Manual review actions

When a job is `awaiting_review`:

1. **accept** — edit graph truth in `gddp-config` (human-only `complete`)
2. **retry** — re-dispatch from persisted state
3. **block** — leave truth unchanged; record blocker outside runtime
4. **defer** — leave in review-needed
5. **reopen / supersede** — revisit or replace later

## Replay

```bash
python3 -m scripts.runtime.replay --result-id <result-id>
python3 -m scripts.runtime.replay --job-id <job-id>   # requires explicit confirmation
```

Treat job redispatch as manual tooling; it bypasses some modern reservation bookkeeping.

## Common gotchas

- Sibling `gddp-config` is assumed; set `GDDP_CONFIG_PATH` when layouts differ.
- Project ID is not always the checkout directory name — resolution uses `project.yaml`'s `repo:` field via `scripts/runtime/repo_resolver.py`.
- Copying `queue.db` while writers run is unsafe; use SQLite online backup after quiescing writers.
- Do not run archived Big Pi artifacts under `deploy/_archive/`.

## Next reads

- [Architecture](architecture.md)
- [Development workflow](../how-to-contribute/development-workflow.md)
- [Deployment](../deployment/index.md)
- [Debugging](../how-to-contribute/debugging.md)
