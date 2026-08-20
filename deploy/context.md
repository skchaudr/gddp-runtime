# deploy/context.md — Deployment Subsystem Map

This directory contains deployment scripts, environment templates, launchd/systemd service definitions, and operational runbooks for GDDP runtime hosts.

---

## 1. Canonical Startup & Operational Runbook

👉 **See [`STARTUP.md`](STARTUP.md)** for full start, stop, watch, steer, and fresh-host instructions.

### Quick Command Reference

| Action | Host | Command |
|---|---|---|
| **Smoke / Preflight** | `sab-mini` | `bash deploy/mini-heartbeat/bin/smoke.sh` |
| **Arm / Start** | `sab-mini` | `MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh` |
| **Disarm / Stop** | `sab-mini` | `bash deploy/mini-heartbeat/bin/disarm.sh` |
| **Heartbeat Logs** | `sab-mini` | `tail -f ~/Library/Logs/gddp-heartbeat.log` |
| **Intake Logs** | `sab-mini` | `tail -f ~/Library/Logs/gddp-intake.log` |
| **Queue Summary** | Any | `python3 scripts/jobs_status.py --summary` |
| **Fleet Watch** | Any | `gddp watch` |
| **Steer Session** | Any | `gddp steer <node_id> "<message>"` |

---

## 2. Machine Roles & Directory Mapping

| Directory / File | Target Host | Status | Description |
|---|---|---|---|
| [`STARTUP.md`](STARTUP.md) | All hosts | **Canonical Guide** | Production start/stop, watch/steer, fresh-host standup runbook |
| [`mini-heartbeat/`](mini-heartbeat/) | `sab-mini` (Mac Mini) | **Active Production** | Production launchd kit (`arm.sh`, `smoke.sh`, `gddp.env` loader) |
| [`mini-heartbeat/FRESH-HOST-STANDUP.md`](mini-heartbeat/FRESH-HOST-STANDUP.md) | Linux / VM | **Active Guide** | Verified Linux fresh-host standup path (systemd) |
| [`rig1-heartbeat/`](rig1-heartbeat/) | `rig1` | **Frozen** | Legacy heartbeat kit (frozen surface; do not invest) |
| [`deploy.sh`](deploy.sh) | — | **Frozen** | Legacy deployment script |
| [`_archive/`](_archive/) | `pi-big` | **Archived** | Decommissioned host runbooks (`BIGPI_RUNBOOK.md`) |

---

## 3. Production Deployment Invariants (`sab-mini`)

1. **Production Host:** `sab-mini` is the single active production queue and heartbeat host. `pi-big` is disarmed.
2. **Launchd Services:**
   - Intake: `com.gddp.intake` (`127.0.0.1:5050` / Tailscale Funnel)
   - Heartbeat: `com.gddp.heartbeat` (`deploy/mini-heartbeat/bin/arm.sh`)
3. **Environment Sourcing:** The heartbeat daemon sources `deploy/mini-heartbeat/env/gddp.env` via `deploy/mini-heartbeat/bin/common.sh`. Direct runner calls skip this environment and fail.
4. **Git-Only Host Sync:** Changes to production hosts land via `git pull --ff-only`. Never use `scp` or direct remote file mutations.

