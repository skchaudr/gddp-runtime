# TOPOLOGY.md — Machine & Queue Map (Human-Owned Canon)

Last updated: 2026-07-12. Supersedes `docs/host-roles.md` (2026-03-21, retired OpenClaw era).
Owner: Sab. Agents read this; agents do not edit it. Items marked ❓ need Sab's confirmation.

## Machines

| Tailscale name | Hardware | Role in GDDP |
|---|---|---|
| `pi-big` | Pi (8GB) | **Production control plane.** `gddp-intake.service` (systemd), heartbeat cron (5-min), production queue DB, all 12 repo webhooks, GPG automation key. Repos at `~/repos/gddp-runtime` + `~/repos/gddp-config`. |
| `sab-mini` | Mac Mini (16GB) | **Live-dispatch / canary surface.** Own local queue DB + local intake (localhost), password-manager secret resolver, `gh` authenticated. Public webhook endpoint is tunnel-based and **ephemeral** — went stale (502) before 2026-07-12. ❓ paths |
| `sab-air` | M5 MacBook Air (24GB) | Operator workstation. |
| `sab-dev` / `sab-dev-2` | Linux VMs | Claude Code session hosts. Clean clone of gddp-runtime; **no `gh` auth, no SSH keys to mini/pi-big.** Local `db/queue.db` contains only dry-run data. ❓ which VM is which |
| `pi-small` | Pi (4GB) | Legacy OpenClaw worker; not part of GDDP. |

## Queue & event rules (learned 2026-07-12, the hard way)

1. **A job lives where its queue row lives.** The canary job existed only in sab-mini's local DB; pi-big correctly ignored the signed merged-PR event because it had no matching job. Events must reach the queue that owns the job.
2. **Local state claims in a plan are machine-relative.** Every plan must name its target machine. A VM reviewer cannot falsify "dirty worktree" claims about the Mini.
3. **pi-big and the Mini drift.** Check commit lag (`git log --oneline -1` both sides) before assuming behavioral parity. On 2026-07-12 pi-big was 5 commits behind and lacked return-path wiring.
4. **Tunnels are ephemeral.** Any temporary tunnel exposing local intake: verify HMAC signature rejection first, tear down the tunnel and revert the webhook URL **as part of done**, not as cleanup. A forgotten tunnel URL is how "stale public endpoint 502" is born.
5. **Never synthesize intake events during a live proof.** Use GitHub signed redelivery or stop.
