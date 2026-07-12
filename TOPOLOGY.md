# TOPOLOGY.md — GDDP Runtime Topology

Where the GDDP runtime runs: control plane, queue, intake, webhooks, and
agent-session hosts. Lives in `gddp-runtime` — runtime infrastructure, not
`gddp-config` graph truth.

Last verified: 2026-07-12 (production on sab-mini).

---

## Production (sab-mini)

| What | Value |
|---|---|
| Host | `sab-mini` (Mac Mini, 16GB) — use Tailscale name in plans |
| Intake | launchd `com.gddp.intake` → `127.0.0.1:5050` |
| Heartbeat | launchd `com.gddp.heartbeat` |
| Public URL | `https://sab-mini.tail02ac6f.ts.net/webhook` (Tailscale Funnel → `:5050`) |
| Queue DB | `~/repos/gddp-runtime/db/queue.db` |
| Runtime repo | `~/repos/gddp-runtime` |
| Config repo | `~/repos/gddp-config` |
| Webhooks | 12 repos (`skchaudr/*`) → mini URL; shared secret |
| Secrets (transition) | `GDDP_WEBHOOK_SECRET_CMD` / `GDDP_DEEPSEEK_KEY_CMD` → ssh `sab-ssd@pi-big` `pass show …` |
| `gh` | Authenticated on mini (`ssh` protocol) |

**pi-big** (`sab-ssd@pi-big`): GDDP disarmed — intake inactive, heartbeat
crontab commented. Still holds `pass` store + automation GPG `F0928E218506BB29`
until migrated to mini. Not a queue host.

---

## Other machines

| Tailscale name | Role in GDDP |
|---|---|
| `sab-air` | Operator workstation. SSH to mini/pi. Not a queue host. |
| `sab-dev` | Agent session VM. Dry-run `db/queue.db` only. No production webhooks. Paths: `~/gddp-runtime`, `~/gddp-config`. |
| `pi-small` | Legacy OpenClaw. Not part of GDDP. |

Machines on Tailscale but not listed here are out of scope for GDDP runtime.

---

## Related

- `deploy/mini-heartbeat/README.md` — launchd kit
- `deploy/mini-heartbeat/CUTOVER.md` — pi-big → mini migration
- `deploy/BIGPI_RUNBOOK.md` — pi-big ops (archive)
- `docs/postmortem-canary-scope-2026-07-12.md` — Jul 12 incident
- `AGENTS.md` — runtime workflow and doctrine