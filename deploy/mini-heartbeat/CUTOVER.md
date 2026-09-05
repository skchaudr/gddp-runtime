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

## Phase 3 — Disarm pi-big

Quiesce production writers before capturing or moving runtime state. On
**pi-big** only:

```bash
cd ~/repos/gddp-runtime
bash deploy/mini-heartbeat/bin/disarm-source.sh
sudo systemctl is-active gddp-intake   # expect: inactive
crontab -l | grep 'scripts.runtime.heartbeat.runner'  # expect only commented lines, or no match
```

`disarm-source.sh` prevents future intake/cron starts; an already-running
heartbeat and its detached local executor can outlive it. Drain them without
terminating them, using the actual runner command and the local-subprocess PID
files written under its configured spool:

```bash
repo="$HOME/repos/gddp-runtime"
spool="${GDDP_ATTEMPT_SPOOL_DIR:-${GDDP_LOCAL_SUBPROCESS_SPOOL_DIR:-$repo/jobs/local-subprocess-spool}}"
active_writers() {
  pgrep -af '[s]cripts\.runtime\.heartbeat\.runner|[a]dapters\.local_subprocess_adapter --run-attempt' || true
  for pid_file in "$spool"/*/supervisor.pid "$spool"/*/pid; do
    test -f "$pid_file" || continue
    attempt_dir="${pid_file%/*}"
    test -f "$attempt_dir/exit.json" && continue
    pid="$(cat "$pid_file")"
    kill -0 "$pid" 2>/dev/null && printf 'active local executor pid=%s (%s)\n' "$pid" "$pid_file"
  done
}

deadline=$((SECONDS + 120))
while test -n "$(active_writers)" && test "$SECONDS" -lt "$deadline"; do
  active_writers
  sleep 2
done
if test -n "$(active_writers)"; then
  active_writers
  echo 'HARD STOP: runtime writers did not drain; do not snapshot or arm mini.' >&2
  false
fi
```

The empty final check is the snapshot gate. If the configured executor uses a
non-default spool, set `GDDP_ATTEMPT_SPOOL_DIR` to that live path first.
Hard stop if any manual/unrecognized GDDP writer remains or the process check
cannot account for the configured executor. Keep pi-big disarmed whether Phase
4 is used or skipped.

## Phase 4 — Optional queue continuity

If mini should inherit pi-big runtime state, capture it only after the Phase 3
no-writer gate passes. SQLite's online backup command includes committed WAL
content without copying the live database files individually:

```bash
# on pi-big, after Phase 3
repo="$HOME/repos/gddp-runtime"
stamp="$(date +%Y%m%d-%H%M%S)"
snapshot_dir="/tmp/gddp-runtime-state-$stamp"
archive="$snapshot_dir.tar.gz"
mkdir -p "$snapshot_dir/db"
sqlite3 "$repo/db/queue.db" ".backup '$snapshot_dir/db/queue.db'"
sqlite3 "$snapshot_dir/db/queue.db" 'PRAGMA journal_mode=DELETE;' >/dev/null
test "$(sqlite3 "$snapshot_dir/db/queue.db" 'PRAGMA integrity_check;')" = ok
tar czf "$archive" -C "$snapshot_dir" db/queue.db -C "$repo" jobs events
printf 'copy this archive to stopped mini: %s\n' "$archive"

# after copying the archive to mini, on mini (intake/heartbeat STOPPED):
cd "$HOME/repos/gddp-runtime"
tar xzf /tmp/gddp-runtime-state-YYYYMMDD-HHMMSS.tar.gz
sqlite3 db/queue.db 'PRAGMA integrity_check;'  # expect: ok
```

Retain the source archive as recovery evidence until the supervised live proof
passes. It supports direct rollback only while mini has accepted no new runtime
activity. Skip this phase if mini starts fresh (recommended for first cutover
unless jobs are in-flight).

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

Directly reactivating pi-big is safe only when mini has accepted **zero new
runtime activity** since the snapshot/cutover. In that case:

```bash
# mini
bash deploy/mini-heartbeat/bin/disarm.sh

# pi-big
sudo systemctl enable --now gddp-intake
# uncomment heartbeat line in crontab -e

# GitHub: PATCH hooks back to pi-big funnel URL
```

If mini accepted any event, dispatch, result, or other runtime write, disarm
both planes and preserve both runtime-state copies. Hard stop before reactivation
until their divergent state is reconciled; do not replace either database with
the pre-cutover snapshot.

## Never again

- Multi-day jobs on trycloudflare / bare `python3 scripts/intake_server.py` PIDs
- Canary-only webhooks left active after the proof
- Arm mini before disarm pi-big (dual-plane risk)
- Smoke skip before arm
- VM-only review of Mini worktree state without SSH to Mini