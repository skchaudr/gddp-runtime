# Deployment

GDDP uses separate `gddp-config` and `gddp-runtime` checkouts on each active host. Paths are host-specific; use `GDDP_CONFIG_PATH` and `GDDP_RUNTIME_ROOT` rather than copying the Mini's absolute paths. Runtime does not turn execution success into graph completion.

## Host topology

| Host | Current role | Runtime state | Service shape |
| --- | --- | --- | --- |
| `sab-mini` | Production control plane | Canonical production `db/queue.db`; intake and heartbeat active | macOS launchd: `com.gddp.intake`, `com.gddp.heartbeat` |
| `pi-big` | Former production and offline secret-store backup | Disarmed; not a queue host | Old intake inactive and heartbeat cron commented |
| `sab-air` | Operator workstation and optional Rig 1 Jules polling lane | No production intake | Dormant heartbeat-only launchd kit under its local runtime checkout |
| `sab-dev` | Agent-session VM | Dry-run queue only; no production webhooks | Development checkout, normally `~/gddp-runtime` and `~/gddp-config` |
| `khoj-38` and later rigs | Linux execution hosts used to prove fresh-host portability | Per-host runtime state and local executor spool | systemd user timer from `deploy/mini-heartbeat/systemd/` in the local checkout |

`pi-small` is legacy OpenClaw and is outside GDDP. Other Tailscale machines are outside the runtime topology unless added to `/Users/sab-mini/repos/gddp-runtime/TOPOLOGY.md`.

## One control plane, additive worker lanes

The mini kit has a one-plane exclusivity contract: do not arm intake and heartbeat on `sab-mini` until the former source plane is disarmed. This prevents divergent queues and duplicate dispatch. Rig 1 is different: it is a heartbeat-only, additive polling lane and installs no intake.

The historical `/Users/sab-mini/repos/gddp-runtime/deploy/deploy.sh` copies a committed `scripts/` snapshot into a runtime root and writes `.gddp-runtime-deploy.json`. Its defaults still describe the older Big Pi layout (`$HOME/opclaw`), so current host setup should follow the mini-heartbeat kit and the verified fresh-host guide rather than treating that script as a universal installer.

## Continue reading

- [Mini-heartbeat operations](mini-heartbeat.md)
- [Production host details](production-hosts.md)
- [Historical 2026-07-13 deployment detail](historical-jul13-deployment.md)
- [Monitoring](../how-to-monitor/index.md)
- Source topology: `/Users/sab-mini/repos/gddp-runtime/TOPOLOGY.md`
