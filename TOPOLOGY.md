# TOPOLOGY.md — GDDP Runtime Topology

Where the GDDP runtime runs: control plane, queue, intake, webhooks, and
agent-session hosts. Lives in `gddp-runtime` because this is **runtime**
infrastructure — not personal notes, not `gddp-config` graph truth.

Last verified: 2026-07-12 (post cutover to sab-mini).

Cutover procedure (historical): `deploy/mini-heartbeat/CUTOVER.md`.

---

## Production (sab-mini)

Single control plane. No split-brain intake.

| What | Value |
|---|---|
| Host | `sab-mini` (Mac Mini, 16GB) |
| Intake | launchd `com.gddp.intake` → `127.0.0.1:5050` |
| Heartbeat | launchd `com.gddp.heartbeat` |
| Public URL | `https://sab-mini.tail02ac6f.ts.net/webhook` (Tailscale Funnel → `:5050`) |
| Queue DB | `~/repos/gddp-runtime/db/queue.db` |
| Runtime repo | `~/repos/gddp-runtime` |
| Config repo | `~/repos/gddp-config` |
| Webhooks | 12 repos (`skchaudr/*`) → mini URL; shared secret |
| Secrets (transition) | `GDDP_WEBHOOK_SECRET_CMD` / `GDDP_DEEPSEEK_KEY_CMD` → ssh `sab-ssd@pi-big` `pass show …` |
| `gh` | Authenticated on mini (`ssh` protocol) |

**pi-big** (`sab-ssd@pi-big`): GDDP **disarmed** — intake inactive, heartbeat
crontab commented. Still holds `pass` store + automation GPG `F0928E218506BB29`
until migrated to mini. Not a queue host.

Webhook repoint: `gh api` PATCH needs JSON `config` body — flat `-f url=` does
not update the hook URL.

---

## Other machines

| Tailscale name | Role in GDDP |
|---|---|
| `sab-air` | Operator workstation. SSH to mini/pi. Not a queue host. |
| `sab-dev` | Agent session VM. Dry-run `db/queue.db` only. No production webhooks, no `gh` auth for dispatch. Paths: `~/gddp-runtime`, `~/gddp-config`. |
| `pi-small` | Legacy OpenClaw. Not part of GDDP. |

Machines on Tailscale but **not in this map** (e.g. `sab-dev-2`) are out of
scope unless they join the runtime control plane.

---

## Runtime invariants

1. **One queue, one intake.** Production jobs and webhook deliveries land on
   sab-mini `db/queue.db`.
2. **Plans name the target machine** — line 1: `Target machine: sab-mini`
   (or explicit host during migration).
3. **No session-scoped production infra.** Ephemeral tunnels are for one-shot
   proofs; teardown + webhook revert is part of done.
4. **Intake fails closed** without a resolved webhook secret.
5. **Never synthesize intake events** during a live proof — signed GitHub
   delivery or labeled operator replay only.
6. **Verdict ≠ acceptance.** Graph status changes require human `accept_node`.

---

## Preflight (before live dispatch)

On the **target host**:

```bash
git log -1 --oneline && git status -sb
curl -s http://127.0.0.1:5050/health
# invalid HMAC → 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:5050/webhook \
  -H "Content-Type: application/json" -H "X-GitHub-Event: ping" \
  -H "X-Hub-Signature-256: sha256=deadbeef" -d '{}'
```

Confirm the job row exists on the **same host** that will receive the return-path
webhook.

---

## Related

- `deploy/mini-heartbeat/README.md` — launchd kit
- `deploy/mini-heartbeat/CUTOVER.md` — pi-big → mini checklist
- `deploy/BIGPI_RUNBOOK.md` — pi-big ops (archive)
- `docs/postmortem-canary-scope-2026-07-12.md` — why topology discipline exists
- `droid-wiki/deployment.md` — generated reference; defers here for hosts