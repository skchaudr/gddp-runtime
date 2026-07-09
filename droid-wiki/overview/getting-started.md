# Getting started

## Prerequisites

- Python 3.11+
- `gddp-config` repository cloned locally (sibling to `gddp-runtime`, or set via `GDDP_CONFIG_PATH`)
- Flask, PyYAML, Pydantic, and Anthropic SDK (see `requirements.txt`)
- GitHub CLI (`gh`) installed and authenticated (for the Jules adapter)

## Install

```bash
git clone https://github.com/skchaudr/gddp-runtime.git
cd gddp-runtime
pip install -r requirements.txt
```

If `gddp-config` is not a sibling directory, set the path:

```bash
export GDDP_CONFIG_PATH=/path/to/gddp-config
```

## Initialize the database

```bash
python3 scripts/init_db.py
```

This creates `db/queue.db` with six tables: `events`, `jobs`, `queue_records`, `results`, `artifact_verifications`, `decision_results`.

## Run the dry run

```bash
python3 scripts/dry_run.py
```

This exercises the full runtime loop locally with fake events and SQLite only. Useful for practicing the flow without dispatching real work.

## Run the heartbeat

```bash
python3 -m scripts.runtime.heartbeat.runner \
  --project <project-id> \
  --repo <owner/repo> \
  --config-path /path/to/gddp-config
```

The `--config-path` flag is optional for local development if `gddp-config` is a sibling repo. It is required for deployed runs.

## Run the decision loop

```bash
python3 -m scripts.runtime.decision_loop.engine \
  --project <project-id> \
  --config-path /path/to/gddp-config
```

This is what cron calls on the live deployment. It wakes, reads context, decides, acts, and exits.

## Run tests

```bash
python3 -m pytest -q
```

Expected: 212 passing tests covering intake, heartbeat modules, state recording, executor adapters, return routing, verification, decision loop, and runtime-root configuration.

## Environment variables

| Variable | Purpose | Required |
|---|---|---|
| `GDDP_CONFIG_PATH` | Path to the sibling `gddp-config` repo | Optional for local dev, required in deployment |
| `GDDP_RUNTIME_ROOT` | Runtime state root for SQLite, events, jobs | Optional, defaults to repo root |
| `GITHUB_TOKEN` or `GH_TOKEN` | GitHub API access for Jules adapter | Required for Jules adapter |
| `GITHUB_WEBHOOK_SECRET` | Webhook signature validation | Optional but recommended |
| `DEEPSEEK_API_KEY` | DeepSeek API for live semantic verification | Required for live semantic mode |
| `GLM_API_KEY` | GLM API for live semantic verification (fallback) | Optional |
