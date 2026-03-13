# gddp-runtime

Runtime scripts for the Graph-Driven Agentic Development (GDAD) system.

This repo contains the code that runs on the Big Pi control plane.
It does NOT contain runtime data (DB, job artifacts, events) — those live in `~/opclaw/` on the Pi.

---

## Structure

| Path | Purpose |
|---|---|
| `scripts/intake_server.py` | Flask webhook intake — normalizes GitHub events into SQLite |
| `scripts/heartbeat.py` | Polls for pending events, creates jobs, dispatches to Jules |
| `scripts/init_db.py` | Initializes SQLite queue.db with all 5 tables |
| `scripts/dry_run.py` | Fake end-to-end flow for testing without real GitHub events |
| `scripts/rollback.py` | Reverts a job and restores node state |
| `scripts/adapters/jules_action_adapter.py` | Dispatches jobs via GitHub issue + jules label |
| `scripts/adapters/jules_cli_adapter.py` | Jules CLI adapter (stub — Phase 4+) |
| `deploy/opclaw-intake.service` | systemd service unit for persistent intake server |
| `deploy/setup.sh` | One-shot Pi deployment script |

---

## Deployment

```bash
git clone git@github.com:skchaudr/gddp-runtime.git
cd gddp-runtime
bash deploy/setup.sh
```

---

## Updating the Pi

```bash
# on the Pi
cd ~/repos/gddp-runtime
git pull
cp -r scripts/* ~/opclaw/scripts/
sudo systemctl restart opclaw-intake
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
