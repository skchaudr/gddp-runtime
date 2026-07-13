# Deployment

> **Topology canon:** multi-host machine map, queue rules, and pi-big → sab-mini
> migration live in **`TOPOLOGY.md`** (human-owned, repo root) and
> **`deploy/mini-heartbeat/CUTOVER.md`**. Read those first before live dispatch.

## Production: sab-mini (since 2026-07-12/13)

Production moved from Big Pi to a Mac Mini in the Jul 2026 cutover
(`deploy/mini-heartbeat/CUTOVER.md`; session trail in
`.handoffs/036-mini-production-docs-baseline.md` and
`.handoffs/037-mini-clean-baseline-startup.md`). The shape:

- **Two launchd agents** replace systemd + cron: `com.gddp.intake` (webhook
  receiver on `127.0.0.1:5050`) and `com.gddp.heartbeat`. Plists are rendered
  from `deploy/mini-heartbeat/env/gddp.env` by
  `deploy/mini-heartbeat/bin/install-dormant.sh`, armed with `arm.sh`.
- **Tailscale Funnel** is the public surface (`https://sab-mini.tail02ac6f.ts.net/webhook`),
  replacing ngrok; 12 repo webhooks point at it.
- **Secrets are mini-local** (since 2026-07-13): `~/.password-store` + GPG
  automation key, resolved via direct `gpg --batch --quiet --decrypt` — not
  `pass show`, which hangs under launchd (comment in `gddp.env` explains).
  pi-big holds an offline backup only; production has no remote secret
  dependency (that dependency caused the 2026-07-12 incident —
  `docs/postmortem-canary-scope-2026-07-12.md`).
- **Verification is a script, not a claim:** `deploy/mini-heartbeat/bin/baseline.sh`
  (tiered OK / DEGRADED / BROKEN — git sync, secret locality, services, HMAC
  round-trip, queue.db, dispatch tick, executor, evaluator liveness) and
  `deploy/mini-heartbeat/bin/smoke.sh` (lighter, warn-based).
- **Git discipline:** production hosts are pull-only — no scp hot-patches, no
  remote file edits (`AGENTS.md`, rule born from the incident above).

## Archive: Big Pi deployment model (pre-cutover)

Everything below describes the retired Big Pi control plane: two repos, a
systemd service, and a cron heartbeat. Kept for reference; see also
`deploy/BIGPI_RUNBOOK.md`.

## Live topology

| Path | Role |
|---|---|
| `~/repos/gddp-runtime` | Runtime source **and** live execution surface. Both the intake service and the heartbeat cron run directly from this checkout. |
| `~/repos/gddp-config` | Graph truth. Human-owned project graphs as YAML. The runtime reads this but never writes it. |
| `~/opclaw/` | Retired legacy surface. `deploy/deploy.sh` still snapshots scripts here and writes a deploy marker, but nothing executes from it and its `db/` is empty. Pending removal. |

No environment on Big Pi sets `GDDP_RUNTIME_ROOT` or `OPCLAW_ROOT`. The runtime root defaults to the repo checkout at `~/repos/gddp-runtime`. The `OPCLAW_ROOT` fallback in code is dead and safe to remove.

## deploy.sh

`deploy/deploy.sh` is the canonical runtime deploy command. It copies a committed snapshot of `scripts/` into the runtime scripts directory and writes a deploy marker JSON recording exactly which git commit is running.

```bash
bash deploy/deploy.sh
bash deploy/deploy.sh --restart-intake
```

What it does, in order:

1. Resolves the runtime root (`GDDP_RUNTIME_ROOT`, then `OPCLAW_ROOT`, then `~/opclaw` by default).
2. Creates runtime state directories: `db/`, `events/{raw,normalized}`, `jobs/`.
3. Captures the current commit SHA, short SHA, branch, and canonical repo root from git.
4. Copies `scripts/` into a temporary directory, then atomically swaps it into place (the old `scripts/` directory is preserved as `scripts.previous/` for rollback).
5. Writes `.gddp-runtime-deploy.json` with the source repo, source branch, source commit, runtime root, deploy invocation details, and UTC timestamp.
6. If `--restart-intake` is passed, restarts `gddp-intake.service` via systemctl.

The deploy marker records both the canonical repo checkout and the worktree the deploy was invoked from. `source_branch` and `source_commit` can legitimately differ from `deploy_invoked_branch` when deployment is done from a detached worktree.

## setup.sh

`deploy/setup.sh` is the first-time install script. Run once on a fresh Pi:

```bash
bash deploy/setup.sh
```

Steps:

1. **Create directories** — `db/`, `events/{raw,normalized}`, `jobs/`, `scripts/adapters` under the runtime root. Runtime state never lives in the repo.
2. **Deploy scripts** — calls `deploy/deploy.sh` to copy the current snapshot and write the deploy marker.
3. **Install systemd service** — copies `deploy/gddp-intake.service` to `/etc/systemd/system/`, reloads systemd, enables `gddp-intake`.
4. **Initialize the database** — if `db/queue.db` does not exist, runs `scripts/init_db.py` to create the six SQLite tables (`events`, `jobs`, `queue_records`, `results`, `artifact_verifications`, `decision_results`).

For updates after the initial setup, use `deploy/deploy.sh --restart-intake` instead of re-running `setup.sh`.

## gddp-intake.service

`deploy/gddp-intake.service` is the systemd unit for the webhook intake server:

```ini
[Unit]
Description=GDDP Intake Server
After=network.target

[Service]
User=sab-ssd
WorkingDirectory=/home/sab-ssd/repos/gddp-runtime
ExecStart=/usr/bin/python3 /home/sab-ssd/repos/gddp-runtime/scripts/intake_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The service runs `scripts/intake_server.py` (a Flask server) with `Restart=always` so a crash brings it back in 5 seconds. It starts after `network.target` so the webhook listener has a network stack available.

Check status:

```bash
sudo systemctl status gddp-intake --no-pager
```

## Heartbeat cron

The heartbeat is a user crontab entry, not a systemd service. It runs every 5 minutes:

```bash
crontab -l | grep heartbeat
```

The cron invokes `python3 -m scripts.runtime.heartbeat.runner` from the repo checkout. Because it reads the checkout directly, it picks up new code on the next tick after a `git pull` with no restart needed. The intake server, by contrast, loads code at process start, so it needs a `systemctl restart` after a pull.

## Deploy workflow

The standard update procedure, run on Big Pi:

```bash
cd ~/repos/gddp-config && git pull --ff-only
cd ~/repos/gddp-runtime && git pull --rebase
sudo systemctl restart gddp-intake
# heartbeat picks up new code on the next cron tick automatically
```

Both repos move together. Node schema and runtime readers are coupled, so pulling config without the runtime (or vice versa) can break dispatch. The `--rebase` on the runtime repo lets local graphify commits ride on top of upstream.

## Preflight checklist

From `deploy/BIGPI_RUNBOOK.md`, before the first real dispatch for a project:

1. **Verify the runtime checkout is current:**
   ```bash
   cd ~/repos/gddp-runtime && git status -sb
   ```

2. **Verify intake is healthy:**
   ```bash
   sudo systemctl status gddp-intake --no-pager
   ```

3. **Verify the target graph exists on Big Pi:**
   ```bash
   cd ~/repos/gddp-config
   git status --short --branch
   find ~/repos/gddp-config/graphs/<project-id> -maxdepth 2 -type f | sort
   ```

4. **Verify the target project has at least one ready node:**
   ```python
   from pathlib import Path
   import yaml
   project = Path.home() / "repos" / "gddp-config" / "graphs" / "<project-id>" / "project.yaml"
   data = yaml.safe_load(project.read_text())
   print([n["id"] for n in data.get("nodes", []) if n.get("status") == "ready"])
   ```

5. **Verify there is exactly one intended event or trigger path for the run.**

6. **Run the heartbeat once, inspect output, then stop.**

## Operational procedures

The full runbook is in `deploy/BIGPI_RUNBOOK.md`. Key procedures:

### Manual heartbeat run

```bash
cd ~/repos/gddp-runtime
python3 -m scripts.runtime.heartbeat.runner \
  --project <project-id> \
  --repo <owner/repo> \
  --config-path ~/repos/gddp-config
```

### Review workflow

When the runtime creates a receipt and moves a job to `awaiting_review`, automation stops there. The reviewer inspects:

- The `results` row in `~/repos/gddp-runtime/db/queue.db`
- The matching job row and queue state
- Artifacts under `~/repos/gddp-runtime/jobs/<job-id>/`
- The merged PR or executor output that produced the receipt

Then chooses exactly one manual action:

| Action | What it means |
|---|---|
| `accept` | Update graph truth manually in `~/repos/gddp-config` |
| `retry` | Re-dispatch the job from persisted runtime state |
| `block` | Leave graph truth unchanged, record the blocker |
| `defer` | Leave the job in review-needed state for later |
| `reopen` / `supersede` | Revisit or replace the work if downstream evidence invalidates it |

Merged PRs and runtime receipts are never treated as automatic graph advancement.

### Mutation boundaries

- Do not run `git reset --hard` unless explicitly authorized.
- Do not commit, push, or redeploy as part of a read-only audit.
- Prefer inspection and reporting over mutation.
- If branch or deploy state is ambiguous, report it plainly instead of fixing it ad hoc.
- Do not add richer graph states, auto-review logic, or automatic return routing in this phase.

## Related pages

- [Architecture](overview/architecture.md)
- [Getting started](overview/getting-started.md)
- [Heartbeat system](systems/heartbeat.md)
- [Intake server](systems/intake-server.md)
- [Patterns and conventions](how-to-contribute/patterns-and-conventions.md)
- [Tooling](how-to-contribute/tooling.md)
