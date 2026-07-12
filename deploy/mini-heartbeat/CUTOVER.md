# pi-big → sab-mini cutover checklist

Human-operated. Run phases in order; do not skip smoke or HMAC checks.
Topology canon: `TOPOLOGY.md` (update Transition after each phase).

## Phase 0 — Preconditions (both hosts)

On **sab-mini**:

```bash
cd ~/repos/gddp-runtime && git pull --ff-only origin main
cd ~/repos/gddp-config && git pull --ff-only origin main
python3 -m pytest -q scripts/   # from gddp-runtime
gh auth status
```

On **pi-big** (while still production):

```bash
cd ~/repos/gddp-runtime && git pull --rebase origin main
cd ~/repos/gddp-config && git pull --ff-only origin main
sudo systemctl status gddp-intake --no-pager
crontab -l | grep heartbeat
```

Record both `git log -1 --oneline` in a handoff before proceeding.

## Phase 1 — Dormant install + smoke (mini, no arm yet)

```bash
cd ~/repos/gddp-runtime
bash deploy/mini-heartbeat/bin/install-dormant.sh
```

Edit `deploy/mini-heartbeat/env/gddp.env` if paths differ from defaults.

**Secrets (pick one strategy):**

| Strategy | `GDDP_WEBHOOK_SECRET_CMD` | When |
|---|---|---|
| **A — Transition (tonight)** | `ssh -o BatchMode=yes pi-big "pass show gddp/webhook-secret"` | Until pass store migrated to mini |
| **B — Target** | `pass show gddp/webhook-secret` | After importing pi-big `pass` + GPG automation key |

Re-render plists after env edit:

```bash
bash deploy/mini-heartbeat/bin/install-dormant.sh   # idempotent
```

Smoke (must pass before arm):

```bash
bash deploy/mini-heartbeat/bin/smoke.sh
```

Smoke checks: runtime/config paths, DeepSeek resolver, **webhook secret
resolver (length only)**, optional HMAC 401 if intake is listening.

## Phase 2 — Stable public intake URL (mini)

**Do not use bare `cloudflared tunnel` PIDs for production.**

Pick one durable exposure (❓ Sab to confirm on mini):

1. **Tailscale Funnel** on sab-mini → `https://sab-mini.<tailnet>.ts.net/webhook`
2. **Named Cloudflare tunnel** as a launchd service (not a one-shot shell)

Verification before any webhook repoint:

```bash
# Invalid HMAC must 401 (intake must be running — Phase 3 arm, or manual start)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:5050/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: ping" \
  -H "X-Hub-Signature-256: sha256=deadbeef" \
  -d '{}'
# expect 401

curl -s http://127.0.0.1:5050/health
# expect {"status":"ok"} when secret resolved
```

## Phase 3 — Optional queue continuity

If mini should inherit pi-big queue rows:

```bash
# on pi-big
tar czf /tmp/gddp-runtime-state-$(date +%Y%m%d).tar.gz \
  -C ~/repos/gddp-runtime db jobs events

# copy to mini, then on mini (intake/heartbeat STOPPED):
cd ~/repos/gddp-runtime
tar xzf /tmp/gddp-runtime-state-*.tar.gz
```

Skip if mini starts fresh (recommended for first cutover unless jobs are
in-flight).

## Phase 4 — Disarm pi-big

On **pi-big** only:

```bash
cd ~/repos/gddp-runtime
bash deploy/mini-heartbeat/bin/disarm-source.sh
```

Confirm: `gddp-intake` stopped+disabled; heartbeat crontab line commented.

## Phase 5 — Arm sab-mini

```bash
cd ~/repos/gddp-runtime
MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh
bash deploy/mini-heartbeat/bin/smoke.sh
```

Tail logs: `~/Library/Logs/gddp-intake.log`, `gddp-heartbeat.log`.

## Phase 6 — Repoint GitHub webhooks (12 repos)

Canonical secret: pi-big `pass show gddp/webhook-secret` (same value mini
intake uses).

For each repo in the 12-repo list (see
`.handoffs/artifacts/029-pi-big-live-intake/system-state.md`):

```bash
# Example — adjust hook id per repo
gh api repos/skchaudr/<repo>/hooks -q '.[] | {id, url, active}'
gh api repos/skchaudr/<repo>/hooks/<id> -X PATCH \
  -f url='https://sab-mini.<tailnet>.ts.net/webhook' \
  -f content_type='json' \
  -f secret="$(ssh pi-big 'pass show gddp/webhook-secret')"
```

Use **Ping** or a test issue on one repo before batch-updating all 12.

## Phase 7 — Supervised live proof

One real event on a low-risk repo → confirm:

1. GitHub delivery **200**
2. Row in mini `events` table
3. Heartbeat picks up on next tick (or manual runner once)
4. No duplicate dispatch on pi-big (should be disarmed)

Update `TOPOLOGY.md` Transition section to match Target; retire pi-big from
GDDP in the table.

## Rollback

```bash
# mini
bash deploy/mini-heartbeat/bin/disarm.sh

# pi-big
sudo systemctl enable --now gddp-intake
# uncomment heartbeat line in crontab -e

# GitHub: PATCH hooks back to pi-big funnel URL
```

## Never again

- Multi-day jobs on trycloudflare / bare `python3 scripts/intake_server.py` PIDs
- Canary-only webhooks left active after the proof
- Arm mini before disarm pi-big (dual-plane risk)
- Smoke skip before arm
- VM-only review of Mini worktree state without SSH to Mini