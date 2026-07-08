# Big Pi Runbook

This is the operator runbook for the live Big Pi control plane.

## Source Of Truth

- `~/repos/gddp-runtime` is the source of truth for runtime code **and the live
  execution surface** — both the intake service and the heartbeat cron run
  directly from it.
- `~/repos/gddp-config` is the source of truth for project graphs.
- Live runtime state (SQLite, events, jobs) lives under `~/repos/gddp-runtime`
  (`db/queue.db` etc.), the runtime root default when `GDDP_RUNTIME_ROOT` is unset.
- `~/opclaw/` is a **retired** legacy surface: `deploy.sh` still snapshots
  scripts there and writes a marker, but nothing executes from it and its
  `db/` is empty. Pending removal.

## Active Paths

- Runtime source + live surface: `~/repos/gddp-runtime`
- Graph source: `~/repos/gddp-config`
- Live DB: `~/repos/gddp-runtime/db/queue.db`
- Legacy snapshot (unused): `~/opclaw/scripts`, marker `~/opclaw/.gddp-runtime-deploy.json`

No environment on Big Pi sets `GDDP_RUNTIME_ROOT` or `OPCLAW_ROOT`; the runtime
root defaults to the repo checkout. The `OPCLAW_ROOT` fallback in code is dead
and safe to remove.

## Active Services

- Intake server: `gddp-intake.service`
  (`/home/sab-ssd/repos/gddp-runtime/scripts/intake_server.py`)
- Heartbeat: user crontab, every 5 minutes, `python3 -m
  scripts.runtime.heartbeat.runner` from the repo checkout

Check status:

```bash
sudo systemctl status gddp-intake --no-pager
crontab -l | grep heartbeat
```

## Canonical Commands

Deploy the current runtime checkout (both repos move together — node schema
and runtime readers are coupled):

```bash
cd ~/repos/gddp-config && git pull --ff-only
cd ~/repos/gddp-runtime && git pull --rebase   # local graphify commits ride on top
sudo systemctl restart gddp-intake             # intake loads code at start
# heartbeat picks up new code on the next cron tick automatically
```

Run the heartbeat manually:

```bash
cd ~/repos/gddp-runtime
python3 -m scripts.runtime.heartbeat.runner \
  --project <project-id> \
  --repo <owner/repo> \
  --config-path ~/repos/gddp-config
```

## First Real Dispatch Preflight

Before the first real dispatch for a project:

1. Verify the runtime checkout is current:

```bash
cd ~/repos/gddp-runtime && git status -sb
```

2. Verify intake is healthy:

```bash
sudo systemctl status gddp-intake --no-pager
```

3. Verify the target graph exists on Big Pi:

```bash
cd ~/repos/gddp-config
git status --short --branch
find ~/repos/gddp-config/graphs/<project-id> -maxdepth 2 -type f | sort
```

4. Verify the target project has at least one ready node:

```bash
python3 - <<'PY'
from pathlib import Path
import yaml
project = Path.home() / "repos" / "gddp-config" / "graphs" / "<project-id>" / "project.yaml"
data = yaml.safe_load(project.read_text())
print([n["id"] for n in data.get("nodes", []) if n.get("status") == "ready"])
PY
```

5. Verify there is exactly one intended event or trigger path for the run.

6. Run heartbeat once, inspect output, then stop.

## Review Workflow

When runtime creates a receipt and moves a job to `awaiting_review`, stop automation there.

Review inputs:

- the `results` row in `~/opclaw/db/queue.db`
- the matching job row and queue state
- the artifacts under `~/opclaw/jobs/<job-id>/`
- the merged PR or executor output that produced the receipt

Choose exactly one manual action:

1. `accept` — update graph truth manually in `~/repos/gddp-config`
2. `retry` — re-dispatch the job from persisted runtime state
3. `block` — leave graph truth unchanged and record the blocker
4. `defer` — leave the job in review-needed state for later
5. `reopen` or `supersede` — revisit or replace the work later if downstream evidence invalidates it

Do not treat merged PRs or runtime receipts as automatic graph advancement.

## Troubleshooting Notes

- If `~/repos/gddp-runtime` and `~/opclaw/scripts` disagree, the deploy marker is authoritative for what is actually running.
- The deploy marker records both the canonical repo checkout and the worktree the deploy was invoked from.
- `source_branch` and `source_commit` can legitimately differ from `deploy_invoked_branch` when deployment is done from a detached worktree.
- If Big Pi repo branches diverge unexpectedly, report the divergence before changing branches or redeploying.

## Mutation Boundaries

- Do not run `git reset --hard` unless explicitly authorized.
- Do not commit, push, or redeploy as part of a read-only audit.
- Prefer inspection and reporting over mutation.
- If branch or deploy state is ambiguous, report it plainly instead of fixing it ad hoc.
- Do not add richer graph states, auto-review logic, or automatic return routing in this phase.
