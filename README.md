# gddp-runtime

Runtime scripts for the Graph-Driven Agentic Development (GDAD) system.

This repo contains the code that runs on the Big Pi control plane.
It does NOT contain runtime data (DB, job artifacts, events) — those live in `~/opclaw/` on the Pi.

---

## Structure

| Path | Purpose |
|---|---|
| `scripts/intake_server.py` | Flask webhook intake — normalizes GitHub events into SQLite |
| `scripts/heartbeat.py` | Legacy heartbeat entrypoint retained for earlier flow |
| `scripts/runtime/heartbeat/runner.py` | Canonical heartbeat runner for Big Pi manual execution |
| `scripts/init_db.py` | Initializes SQLite queue.db with all 5 tables |
| `scripts/dry_run.py` | Fake end-to-end flow for testing without real GitHub events |
| `scripts/rollback.py` | Reverts a job and restores node state |
| `scripts/adapters/jules_action_adapter.py` | Dispatches jobs via GitHub issue + jules label |
| `scripts/adapters/jules_cli_adapter.py` | Jules CLI adapter (stub — Phase 4+) |
| `deploy/BIGPI_RUNBOOK.md` | Operator runbook for Big Pi paths, commands, and first dispatch |
| `deploy/opclaw-intake.service` | systemd service unit for persistent intake server |
| `deploy/deploy.sh` | Canonical Big Pi deploy command; syncs scripts and writes deploy marker |
| `deploy/setup.sh` | One-shot Pi deployment script |

---

## Deployment

```bash
git clone git@github.com:skchaudr/gddp-runtime.git
cd gddp-runtime
bash deploy/setup.sh
```

`~/repos/gddp-runtime` is the source of truth.
`~/opclaw/scripts` is the deployed execution surface.

`deploy/setup.sh` is for first install.
For updates after that, use `deploy/deploy.sh`.

---

## Updating the Pi

```bash
# on the Pi
cd ~/repos/gddp-runtime
git pull
bash deploy/deploy.sh --restart-intake
```

### Replay Mechanics

GDAD supports replaying failed or partial runtime steps without manual database surgery.

- **Replay a Return Router failure:**
  If graph advancement fails after a PR merge, use the `result_id` from the logs.
  ```bash
  python3 -m runtime.replay --result-id res_20260312T21053737
  ```
  This re-runs the return router logic for the original event.

- **Replay a Job Dispatch failure:**
  If a job fails to dispatch or needs a re-run, use the `job_id`.
  ```bash
  python3 -m runtime.replay --job-id job_20260312T21053737
  ```
  This re-dispatches the job. **Note:** This requires operator confirmation (`yes/no`) to prevent accidental re-dispatches.

**Safeguards:**
- Replay reads from persisted job/event/result context in SQLite.
- Replay does NOT re-receive webhooks or re-classify events.
- Job re-dispatch ALWAYS requires manual operator confirmation.

This writes the deployed commit marker to:

```bash
~/opclaw/.gddp-runtime-deploy.json
```

Use it to verify what code is actually running:

```bash
cat ~/opclaw/.gddp-runtime-deploy.json
```

Heartbeat runner invocation on Big Pi:

```bash
cd ~/opclaw/scripts
python3 -m runtime.heartbeat.runner \
  --project <project-id> \
  --repo <owner/repo> \
  --config-path ~/repos/gddp-config
```

For the full operator procedure, see:

```bash
deploy/BIGPI_RUNBOOK.md
```

---

## Related repos

| Repo | Purpose |
|---|---|
| `skchaudr/gddp-config` | Schemas, graphs, templates — the doctrine |
| `skchaudr/gddp-runtime` | Scripts — the execution layer |
| `skchaudr/vault-doctor` | First real GDAD project |

---

## Key rule

Runtime data never goes in this repo.
`~/opclaw/db/`, `~/opclaw/jobs/`, `~/opclaw/events/` stay on the Pi only.
