# Debugging

This page covers how to inspect runtime state, replay failed steps, and diagnose common issues.

## Checking SQLite state

All runtime state lives in `db/queue.db` under the runtime root. The database has six tables: `events`, `jobs`, `queue_records`, `results`, `artifact_verifications`, `decision_results`.

### Quick inspection

```bash
# Check the database exists
ls -la db/queue.db

# List tables
sqlite3 db/queue.db ".tables"

# Recent events
sqlite3 db/queue.db "SELECT event_id, event_type, project_id, status, created_at FROM events ORDER BY created_at DESC LIMIT 10;"

# Recent jobs
sqlite3 db/queue.db "SELECT job_id, node_id, project_id, executor, status FROM jobs ORDER BY rowid DESC LIMIT 10;"

# Recent results (receipts)
sqlite3 db/queue.db "SELECT result_id, job_id, verdict, created_at FROM results ORDER BY rowid DESC LIMIT 10;"

# Jobs awaiting review
sqlite3 db/queue.db "SELECT job_id, node_id, project_id FROM jobs WHERE status = 'awaiting_review';"
```

All SQLite connections in the runtime use `row_factory = sqlite3.Row` and `PRAGMA foreign_keys=ON`. When inspecting manually, use `sqlite3` directly or a Python one-liner:

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('db/queue.db')
con.row_factory = sqlite3.Row
for row in con.execute('SELECT * FROM results ORDER BY rowid DESC LIMIT 5'):
    print(dict(row))
"
```

## Replay utilities

The replay module (`scripts/runtime/replay.py`) re-runs failed or partial runtime steps from persisted DB state. No DB surgery needed.

### Replay a result

Re-runs the return router logic (`handle_merged_pr`) for the event associated with a result. This recreates the review receipt and state routing.

```bash
python3 -m scripts.runtime.replay --result-id res_20260312T21053737
```

The result ID maps to an event ID by swapping the `res_` prefix for `evt_`. The replay reads the event from the DB and re-runs the return router against it.

### Replay a job

Re-dispatches a specific job to its assigned executor (e.g., Jules). This requires explicit operator confirmation, typed at a prompt, to prevent accidental re-dispatches.

```bash
python3 -m scripts.runtime.replay --job-id job_20260312T21053737
```

The replay prints the job details (node, project, executor, goal, status) and asks for `yes` confirmation before dispatching. On success it marks the event mapped and the job running. On failure it marks the job failed.

### What replay does not cover

Replay does not re-receive webhooks. Events are read from the DB, not re-intaked. Classification and scoping use the persisted job and event context, not a fresh pass.

## Dry-run flow

The dry run (`scripts/dry_run.py`) walks a mock event through the full pipeline with SQLite only. If something is broken in the pipeline plumbing, the dry run is the fastest way to find where:

```bash
python3 scripts/dry_run.py
```

It prints each step with a separator line, so you can see exactly where the flow stops or produces unexpected output. The verification bridge is mocked, so no real LLM call happens.

## Intake server health check

The intake server exposes a `/health` endpoint that returns `{"status": "ok"}` with a 200 status code:

```bash
# Local dev (Flask dev server on port 5050)
curl http://127.0.0.1:5050/health

# Production (Big Pi, systemd service)
curl http://127.0.0.1:5050/health
```

On Big Pi, check the systemd service status:

```bash
sudo systemctl status gddp-intake --no-pager
```

The intake server prints a warning on startup if no webhook secret is resolved. It also exits immediately if `db/queue.db` does not exist, telling you to run `python3 scripts/init_db.py` first.

## Deploy marker

`deploy/deploy.sh` writes a deploy marker at `$RUNTIME_ROOT/.gddp-runtime-deploy.json` recording exactly which git commit is running on the live surface. The marker contains:

```json
{
  "source_repo": "/path/to/gddp-runtime",
  "source_branch": "main",
  "source_commit": "<full-sha>",
  "source_commit_short": "<short-sha>",
  "runtime_root": "/path/to/runtime-root",
  "deploy_invoked_from": "/path/to/worktree",
  "deploy_invoked_branch": "<branch-or-detached>",
  "deployed_at_utc": "<timestamp>",
  "deployed_scripts_dir": "/path/to/runtime-root/scripts"
}
```

If the live system is behaving unexpectedly, check the marker to confirm which commit is actually running. The `source_branch` and `source_commit` can differ from `deploy_invoked_branch` when deployment is done from a detached worktree. See the [Big Pi runbook](../../deploy/BIGPI_RUNBOOK.md) troubleshooting section for the full explanation.

## Big Pi runbook troubleshooting

The runbook at `deploy/BIGPI_RUNBOOK.md` is the operator runbook for the live control plane. Its troubleshooting section covers:

- The repo checkout is what runs. The `~/opclaw` snapshots and markers are legacy and not authoritative.
- The deploy marker records both the canonical repo checkout and the worktree the deploy was invoked from.
- `source_branch` and `source_commit` can legitimately differ from `deploy_invoked_branch` when deployment is done from a detached worktree.
- If Big Pi repo branches diverge unexpectedly, report the divergence before changing branches or redeploying.

The runbook also documents mutation boundaries: do not run `git reset --hard` unless explicitly authorized, do not commit or push as part of a read-only audit, and prefer inspection and reporting over mutation.

## Common issues

### GDDP_CONFIG_PATH not set

If `gddp-config` is not a sibling directory of `gddp-runtime`, the runtime cannot find project graphs. Set the path explicitly:

```bash
export GDDP_CONFIG_PATH=/path/to/gddp-config
```

The runtime resolves the config path in this priority order: explicit `--config-path` argument, then `GDDP_CONFIG_PATH` environment variable, then the sibling directory convention (`runtime_root.parent / "gddp-config"`). See [Getting started](../overview/getting-started.md) for the full environment variable table.

### queue.db not found

The intake server exits on startup if `db/queue.db` does not exist. The error message tells you to run `python3 scripts/init_db.py` first. If the database exists but is empty or corrupted, reinitialize it:

```bash
python3 scripts/init_db.py
```

This creates all six tables with the correct schema. If `GDDP_RUNTIME_ROOT` is set, the database lives at `$GDDP_RUNTIME_ROOT/db/queue.db`. Otherwise it defaults to the repo root.

### Webhook secret not configured

The intake server prints a warning on startup if no webhook secret is resolved. Without a secret, signature verification is disabled, and the server should not be exposed publicly. Set the secret via environment variable:

```bash
export GITHUB_WEBHOOK_SECRET=<your-secret>
```

Or configure an external command (default: `pass` password manager) via the `GDDP_WEBHOOK_SECRET_CMD` environment variable. The resolution pattern is the same as the DeepSeek API key resolution in the verification bridge.

### gh CLI not authenticated

The Jules adapter uses the GitHub CLI (`gh`) to create issues on target repositories. If dispatch fails with an authentication error, verify the CLI is authenticated:

```bash
gh auth status
```

If not authenticated, run `gh auth login` and follow the prompts. The adapter also respects `GITHUB_TOKEN` or `GH_TOKEN` environment variables. See [Getting started](../overview/getting-started.md) for the environment variable table.

## Related pages

- [Testing](testing.md) - what the 212 tests cover
- [Tooling](tooling.md) - build and dev tools
- [Deployment](../deployment.md) - systemd, cron, and the Big Pi runbook
- [Patterns and conventions](patterns-and-conventions.md) - error handling patterns
