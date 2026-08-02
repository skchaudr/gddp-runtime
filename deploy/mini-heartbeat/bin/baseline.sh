#!/usr/bin/env bash
# baseline.sh — verified production state, tiered by what a failure means.
#
# Two failure tiers, distinct exit codes so callers can gate appropriately:
#   [WARN] weakened  — system operable today but fragile or drifting
#                      (dirty/desynced git, secrets still resolving via ssh)
#   [CRIT] broken    — a lane is inoperable or unsafe (intake down, HMAC
#                      not enforced, secrets unresolvable, db locked, ...)
# exit 0 = OK, exit 1 = DEGRADED (warns only), exit 2 = BROKEN (any crit).
# Checks the RENDERED plists (production truth), not the caller's shell env.
#
# Born from the 2026-07-12/13 incidents: an scp hot-patch left git desynced,
# and "cutover complete" was declared while secrets still resolved over ssh
# to pi-big. Sections 1 and 2 catch exactly those.
set -uo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

PASS=0; WARN=0; CRIT=0
ok()   { echo "  [ok]   $1"; PASS=$((PASS+1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN+1)); }
crit() { echo "  [CRIT] $1"; CRIT=$((CRIT+1)); }
info() { echo "  [info] $1"; }

PLIST="$HOME/Library/LaunchAgents/${INTAKE_LABEL}.plist"
DB="$GDDP_RUNTIME_ROOT/db/queue.db"
FUNNEL_HEALTH_URL="${FUNNEL_HEALTH_URL:-https://sab-mini.tail02ac6f.ts.net/health}"

echo "=== GDDP mini baseline — $(hostname) $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# --- 1. git: clean and synced (catches hot-patch drift) ----------------------
cd "$GDDP_RUNTIME_ROOT"
if [[ -z "$(git status --porcelain)" ]]; then
  ok "git working tree clean"
else
  warn "git working tree dirty: $(git status --porcelain | head -3 | tr '\n' ' ')"
fi
if git fetch --quiet origin main 2>/dev/null; then
  read -r ahead behind < <(git rev-list --left-right --count HEAD...origin/main)
  if [[ "$ahead" == 0 && "$behind" == 0 ]]; then
    ok "git synced with origin/main ($(git rev-parse --short HEAD))"
  else
    warn "git out of sync: $ahead ahead / $behind behind origin/main"
  fi
else
  warn "git fetch origin failed (offline?)"
fi

# --- 2. secrets: local-only, resolvable (catches phantom cutover) ------------
if [[ ! -f "$PLIST" ]]; then
  crit "intake plist missing: $PLIST"
  secret_cmd=""; deepseek_cmd=""
else
  secret_cmd="$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:GDDP_WEBHOOK_SECRET_CMD" "$PLIST" 2>/dev/null || true)"
  deepseek_cmd="$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:GDDP_DEEPSEEK_KEY_CMD" "$PLIST" 2>/dev/null || true)"
  for pair in "webhook:$secret_cmd" "deepseek:$deepseek_cmd"; do
    name="${pair%%:*}"; cmd="${pair#*:}"
    if [[ -z "$cmd" ]]; then
      crit "$name secret cmd missing from rendered plist"
    elif [[ "$cmd" == *ssh* ]]; then
      warn "$name secret cmd still uses ssh (remote dependency): $cmd"
    else
      ok "$name secret cmd is local"
    fi
  done
fi
webhook_secret=""
if [[ -n "$secret_cmd" ]]; then
  webhook_secret="$(bash -c "$secret_cmd" 2>/dev/null | head -1 || true)"
fi
if [[ -n "$webhook_secret" ]]; then
  ok "webhook secret resolves (len=${#webhook_secret})"
else
  crit "webhook secret does not resolve via plist cmd"
fi
if [[ -n "$deepseek_cmd" ]] && out="$(bash -c "$deepseek_cmd" 2>/dev/null | head -1)" && [[ -n "$out" ]]; then
  ok "deepseek key resolves (len=${#out})"
else
  crit "deepseek key does not resolve via plist cmd"
fi

# --- 3. services: launchd + intake + funnel ----------------------------------
for label in "$INTAKE_LABEL" "$HEARTBEAT_LABEL"; do
  if launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then
    ok "launchd $label registered"
  else
    crit "launchd $label not registered"
  fi
done
hcode="$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:5050/health || true)"
[[ "$hcode" == 200 ]] && ok "intake /health 200 (local)" || crit "intake /health local: $hcode"
fcode="$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$FUNNEL_HEALTH_URL" || true)"
[[ "$fcode" == 200 ]] && ok "funnel /health 200 ($FUNNEL_HEALTH_URL)" || crit "funnel /health: $fcode"

# --- 4. webhook pipeline: real HMAC round-trip, no GitHub needed -------------
bcode="$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 -X POST http://127.0.0.1:5050/webhook \
  -H "Content-Type: application/json" -H "X-GitHub-Event: ping" \
  -H "X-Hub-Signature-256: sha256=invalid" -d '{}' || true)"
[[ "$bcode" == 401 ]] && ok "invalid HMAC rejected (401)" || crit "invalid HMAC returned $bcode (expected 401)"
if [[ -n "$webhook_secret" ]]; then
  payload='{"zen":"baseline signed ping"}'
  sig="$(printf '%s' "$payload" | openssl dgst -sha256 -hmac "$webhook_secret" | awk '{print $NF}')"
  scode="$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 -X POST http://127.0.0.1:5050/webhook \
    -H "Content-Type: application/json" -H "X-GitHub-Event: ping" \
    -H "X-Hub-Signature-256: sha256=$sig" -d "$payload" || true)"
  [[ "$scode" == 200 ]] && ok "correctly signed ping accepted (200)" || crit "signed ping returned $scode (expected 200)"
else
  crit "signed-ping check skipped: no webhook secret"
fi

# --- 5. queue.db: intact and writable ----------------------------------------
# WAL commits may not advance queue.db's mtime until checkpoint; use SQL
# application timestamps (as below), never the main file mtime, for freshness.
if [[ -f "$DB" ]]; then
  integ="$(sqlite3 "$DB" "PRAGMA integrity_check;" 2>/dev/null || echo error)"
  [[ "$integ" == "ok" ]] && ok "queue.db integrity ok" || crit "queue.db integrity: $integ"
  if sqlite3 "$DB" "BEGIN IMMEDIATE; ROLLBACK;" 2>/dev/null; then
    ok "queue.db writable (lock acquired)"
  else
    crit "queue.db not writable (locked or readonly)"
  fi
  info "jobs by state: $(sqlite3 "$DB" "SELECT queue_state || '=' || COUNT(*) FROM jobs GROUP BY queue_state;" | tr '\n' ' ')"
  info "last event received: $(sqlite3 "$DB" "SELECT COALESCE(MAX(received_at),'never') FROM events;")"
else
  crit "queue.db missing: $DB"
fi

# --- 6. dispatch path: one heartbeat tick -------------------------------------
(
  cd "$GDDP_RUNTIME_ROOT"
  export GDDP_REPO_ROOT="${GDDP_REPOS_ROOT}"
  export PYTHONPATH="$GDDP_RUNTIME_ROOT${PYTHONPATH:+:$PYTHONPATH}"
  python3 -m scripts.runtime.heartbeat.runner \
    --project "$GDDP_PROJECT_ID" --repo "$GDDP_PROJECT_REPO" \
    --config-path "$GDDP_CONFIG_PATH" >/dev/null 2>&1
) && ok "heartbeat tick exited 0 (dispatch path alive)" \
  || crit "heartbeat tick failed"

# --- 7. executor: jules dispatch dependency -----------------------------------
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  ok "gh authenticated (jules dispatch)"
else
  crit "gh not authenticated — jules dispatch will fail"
fi

# --- 8. evaluator: pi harness present and runnable -----------------------------
HARNESS="$GDDP_RUNTIME_ROOT/scripts/runtime/verification/semantic/pi_harness"
if command -v pi >/dev/null 2>&1; then
  if pi --version >/dev/null 2>&1; then
    ok "pi binary runs ($(pi --version 2>/dev/null | head -1))"
  else
    crit "pi on PATH but --version failed"
  fi
else
  crit "pi not on PATH — evaluator cannot run"
fi
for ext in gddp_verifier.ts gddp_verifier_guard.ts; do
  [[ -f "$HARNESS/$ext" ]] && ok "evaluator extension $ext present" || crit "evaluator extension $ext missing"
done

# --- summary -------------------------------------------------------------------
echo "=== baseline: $PASS ok, $WARN warn, $CRIT crit ==="
if [[ "$CRIT" -ne 0 ]]; then
  echo "=== baseline: BROKEN — a lane is inoperable or unsafe ==="
  exit 2
fi
if [[ "$WARN" -ne 0 ]]; then
  echo "=== baseline: DEGRADED — operable but fragile/drifting ==="
  exit 1
fi
echo "=== baseline: OK ==="
