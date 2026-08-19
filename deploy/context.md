# deploy/context.md — Deployment Subsystem Map

This directory contains deployment scripts, environment templates, and launchd service definitions for GDDP runtime hosts.

---

## 1. Machine Roles & Directory Mapping

| Directory / File | Target Host | Status | Description |
|---|---|---|---|
| [`mini-heartbeat/`](mini-heartbeat/) | `sab-mini` (Mac Mini) | **Active Production** | Production launchd kit (`arm.sh`, `smoke.sh`, `gddp.env` loader) |
| [`rig1-heartbeat/`](rig1-heartbeat/) | `rig1` | **Frozen** | Legacy heartbeat kit (frozen surface; do not invest) |
| [`deploy.sh`](deploy.sh) | — | **Frozen** | Legacy deployment script |
| [`_archive/`](_archive/) | `pi-big` | **Archived** | Decommissioned host runbooks (`BIGPI_RUNBOOK.md`) |

---

## 2. Production Deployment Invariants (`sab-mini`)

1. **Production Host:** `sab-mini` is the single active production queue and heartbeat host. `pi-big` is disarmed.
2. **Launchd Services:**
   - Intake: `com.gddp.intake` (`127.0.0.1:5050` / Tailscale Funnel)
   - Heartbeat: `com.gddp.heartbeat` (`deploy/mini-heartbeat/bin/arm.sh`)
3. **Environment Sourcing:** The heartbeat daemon sources `deploy/mini-heartbeat/env/gddp.env` via `deploy/mini-heartbeat/bin/common.sh`. Direct runner calls skip this environment and fail.
4. **Git-Only Host Sync:** Changes to production hosts land via `git pull --ff-only`. Never use `scp` or direct remote file mutations.
