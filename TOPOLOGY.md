# TOPOLOGY.md — Machine & Queue Map (Human-Owned Canon)

Last updated: 2026-07-12 (night-shift cutover prep).
Owner: **Sab**. Agents read this; agents do not edit it unless Sab explicitly
asks for a draft. Items marked ❓ need Sab confirmation before cutover.

**How to use this file during pi-big → sab-mini migration:** read **Target**
for where we are going, **Transition** for what is true tonight, and
`deploy/mini-heartbeat/CUTOVER.md` for the ordered steps that move Transition
→ Target. Update Transition after each cutover phase; when Transition matches
Target, delete the Transition section.

---

## Target topology (post-migration)

Single control plane on **sab-mini**. No split-brain intake, no session-scoped
tunnels for production webhooks.

| Tailscale name | Hardware | Role in GDDP |
|---|---|---|
| `sab-mini` | Mac Mini (16GB) | **Sole production control plane.** launchd `com.gddp.intake` + `com.gddp.heartbeat`, production `db/queue.db`, all 12 repo webhooks, `pass` store (or approved remote resolver), `gh` authenticated, stable signed public intake URL (Tailscale Funnel or named tunnel as a **service**, not a shell PID). Repos: `~/repos/gddp-runtime` + `~/repos/gddp-config`. |
| `pi-big` | Pi (8GB) | **Retired from GDDP** (standby/archive). No intake, no heartbeat, no production webhooks. May keep repos for read-only reference until Sab deletes. |
| `sab-air` | M5 MacBook Air (24GB) | Operator workstation. SSH to mini/pi; not a queue host. |
| `sab-dev` / `sab-dev-2` | Linux VMs | Agent session hosts. Clean clones; **no live queue**, no `gh` auth, no production webhooks. `db/queue.db` = dry-run only. |
| `pi-small` | Pi (4GB) | Legacy OpenClaw; not part of GDDP. |

### Target paths (sab-mini defaults — confirm ❓)

| What | Path |
|---|---|
| Runtime checkout | `~/repos/gddp-runtime` ❓ |
| Config checkout | `~/repos/gddp-config` ❓ |
| Queue DB | `~/repos/gddp-runtime/db/queue.db` |
| Intake bind | `127.0.0.1:5050` → public funnel/tunnel |
| Webhook route | `POST /webhook` |
| Public intake URL | `https://sab-mini.<tailnet>.ts.net/webhook` ❓ (stable funnel) |
| Secrets | Local `pass`: `gddp/webhook-secret`, `api/deepseek`; automation GPG key migrated from pi-big |
| GitHub webhooks | All 12 repos → sab-mini public URL; one shared secret |

### Target queue & event rules

1. **One queue, one intake.** Every production job row and every production
   webhook delivery lands on sab-mini `db/queue.db`.
2. **Plans name the target machine** in line 1: `Target machine: sab-mini`.
3. **No session-scoped production infra.** Temporary tunnels are for one-shot
   proofs only; teardown + webhook revert is part of done.
4. **Intake fails closed** without a resolved webhook secret (no public
   exposure with verification disabled).
5. **Never synthesize intake events** during a live proof. Signed GitHub
   delivery or operator replay from a saved delivery payload — labeled in the
   handoff.
6. **Verdict ≠ acceptance.** Only Sab runs `accept_node`.

---

## Transition (as of 2026-07-12, post-canary recovery)

Canary retry proof **completed** on sab-mini (`res_20260712T0837057851` PASS).
Ephemeral canary webhook `651704334` **deactivated**. pi-big still owns the
12 production webhooks until cutover.

| Tailscale name | Current role | Queue / webhooks |
|---|---|---|
| `pi-big` | **Production control plane (legacy).** systemd `gddp-intake`, heartbeat cron 5m, Tailscale funnel, `pass` + automation GPG `F0928E218506BB29`. | Production `db/queue.db`; **12 repo webhooks** → `https://pi-big.tail02ac6f.ts.net/webhook` |
| `sab-mini` | **Canary / dev dispatch surface.** launchd kit installed **dormant**; intake ran localhost during canary with `GDDP_WEBHOOK_SECRET_CMD` → ssh pi-big `pass show gddp/webhook-secret`. | Local queue held canary job; **no production webhooks** after canary hook deactivated |
| `sab-dev` | VM agent host (this doc edited here). | Dry-run `db/queue.db` only |
| `sab-dev-2` | VM agent host ❓ | Dry-run only ❓ |
| `sab-air` | Operator | — |

### Transition paths

| Host | Runtime | Config | Notes |
|---|---|---|---|
| pi-big | `~/repos/gddp-runtime` (`run-main` + local graphify commit) | `~/repos/gddp-config` | User `sab-ssd` on box |
| sab-mini | `~/repos/gddp-runtime` | `~/repos/gddp-config` | Handoff 032 worktree; graphify-out dirt OK |
| sab-dev | `~/gddp-runtime` | `~/gddp-config` | No SSH to mini/pi from here (BatchMode fails) |

### Transition risks (do not repeat)

- Jobs dispatched from shell PIDs / trycloudflare while dormant pack unarmed.
- VM reviewing Mini worktree claims without naming the machine.
- Webhook secret on GitHub ≠ secret on intake → 401 (correct) or worse if
  verification was disabled (fixed: intake now fails closed).
- pi-big and sab-mini **code drift** — check `git log -1` both sides before
  assuming parity.

---

## Cutover

Ordered procedure: **`deploy/mini-heartbeat/CUTOVER.md`**.

Summary: smoke (secrets + HMAC) → stable mini public URL → disarm pi-big →
arm mini → repoint 12 webhooks → one supervised live event → update this file
(Transition → Target).

---

## Agent preflight (every live-dispatch session)

Before trusting a plan or dispatching:

1. Read this file (Transition + Target).
2. Confirm **target machine** is named in the plan.
3. On the target host: `git log -1 --oneline`, `git status -sb`, queue DB
   path, intake health (`curl -s localhost:5050/health`).
4. Confirm webhook secret resolves (length only) and invalid HMAC → `401`.
5. Confirm job row exists on **same host** as the webhook that will receive the
   return-path event.

---

## Related canon

- `deploy/mini-heartbeat/README.md` — dormant kit
- `deploy/mini-heartbeat/CUTOVER.md` — migration checklist
- `deploy/BIGPI_RUNBOOK.md` — pi-big ops (until retired)
- `docs/postmortem-canary-scope-2026-07-12.md` — why this file exists
- `droid-wiki/deployment.md` — **generated reference**; defers here for topology