#!/usr/bin/env bash
# Lightweight checks — no secrets printed.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

echo "=== mini-heartbeat smoke ==="
echo "  host:     $(hostname) ($(uname -s))"
echo "  runtime:  $GDDP_RUNTIME_ROOT"
echo "  config:   $GDDP_CONFIG_PATH"

fail=0

if [[ ! -d "$GDDP_RUNTIME_ROOT/scripts" ]]; then
  echo "  [FAIL] runtime scripts missing"; fail=1
else
  echo "  [ok] runtime scripts"
fi

if [[ ! -f "$GDDP_CONFIG_PATH/graphs/${GDDP_PROJECT_ID}/project.yaml" ]]; then
  echo "  [FAIL] project.yaml missing for $GDDP_PROJECT_ID"; fail=1
else
  echo "  [ok] project.yaml"
fi

# DeepSeek via env or resolver cmd — length only
_deepseek_key_len() {
  if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    echo "${#DEEPSEEK_API_KEY}"
    return 0
  fi
  local cmd="${GDDP_DEEPSEEK_KEY_CMD:-pass show api/deepseek}"
  [[ -n "$cmd" ]] || return 1
  local out
  if ! out="$(bash -c "$cmd" 2>/dev/null | head -1)"; then
    return 1
  fi
  [[ -n "$out" ]] || return 1
  echo "${#out}"
}

if ds_len="$(_deepseek_key_len)"; then
  echo "  [ok] DeepSeek key resolved (len=${ds_len})"
else
  echo "  [FAIL] DeepSeek key empty or resolver failed"; fail=1
fi

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "  [ok] gh auth"
else
  echo "  [warn] gh not authenticated (needed for Jules dispatch)"
fi

if command -v pi >/dev/null 2>&1; then
  echo "  [ok] pi on PATH"
else
  echo "  [warn] pi not on PATH (needed for evaluator harness)"
fi

# Webhook secret resolver (length only — never print secret)
_webhook_secret_len() {
  if [[ -n "${GITHUB_WEBHOOK_SECRET:-}" ]]; then
    echo "${#GITHUB_WEBHOOK_SECRET}"
    return 0
  fi
  local cmd="${GDDP_WEBHOOK_SECRET_CMD:-pass show gddp/webhook-secret}"
  if [[ -z "$cmd" ]]; then
    return 1
  fi
  local out
  if ! out="$(bash -c "$cmd" 2>/dev/null | head -1)"; then
    return 1
  fi
  [[ -n "$out" ]] || return 1
  echo "${#out}"
}

if ws_len="$(_webhook_secret_len)"; then
  echo "  [ok] webhook secret resolved (len=${ws_len})"
else
  echo "  [FAIL] webhook secret empty or resolver failed"; fail=1
fi

if curl -sf --max-time 2 http://127.0.0.1:5050/health >/dev/null 2>&1; then
  hcode="$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 http://127.0.0.1:5050/health)"
  if [[ "$hcode" == "200" ]]; then
    echo "  [ok] intake /health 200"
  else
    echo "  [FAIL] intake /health returned $hcode (expected 200 when armed)"; fail=1
  fi
  sig_code="$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 -X POST http://127.0.0.1:5050/webhook \
    -H "Content-Type: application/json" \
    -H "X-GitHub-Event: ping" \
    -H "X-Hub-Signature-256: sha256=invalid" \
    -d '{}')"
  if [[ "$sig_code" == "401" ]]; then
    echo "  [ok] intake rejects invalid HMAC (401)"
  else
    echo "  [FAIL] invalid HMAC returned $sig_code (expected 401)"; fail=1
  fi
else
  echo "  [warn] intake not listening on :5050 — skip /health and HMAC probe (arm first)"
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  if launchctl print "gui/$(id -u)/${INTAKE_LABEL}" >/dev/null 2>&1; then
    echo "  [ok] launchd $INTAKE_LABEL registered"
  else
    echo "  [warn] $INTAKE_LABEL not registered (run install-dormant / arm)"
  fi
fi

# Plist env drift: the installed launchd plist freezes its EnvironmentVariables
# at arm time. Editing gddp.env never reaches the heartbeat until re-arm —
# on 2026-08-02 the plist still pinned executor model grok-cli/grok-4.5 after
# gddp.env moved to zai/glm-5.2, and every launchd-dispatched executor died on
# revoked xAI OAuth while shell-run pi worked. Compare the env the current env
# file would render against the env launchd actually has loaded.
_plist_drift_keys() {
  local template="$1" installed="$2" rendered
  rendered="$(mktemp -t gddp-plist-render)"
  render_plist "$template" "$rendered"
  "$GDDP_PYTHON" - "$rendered" "$installed" <<'PY'
import json, subprocess, sys

def env_of(path):
    out = subprocess.run(
        ["plutil", "-extract", "EnvironmentVariables", "json", "-o", "-", path],
        capture_output=True, text=True,
    )
    return json.loads(out.stdout) if out.returncode == 0 else {}

current, installed = env_of(sys.argv[1]), env_of(sys.argv[2])
diffs = [k for k in sorted(set(current) | set(installed))
         if current.get(k) != installed.get(k)]
if diffs:
    print("\n".join(diffs))
    sys.exit(1)
PY
  local rc=$?
  rm -f "$rendered"
  return $rc
}

for label in "$HEARTBEAT_LABEL" "$INTAKE_LABEL"; do
  template="$KIT_ROOT/launchd/${label}.plist"
  installed="$LAUNCH_AGENTS_DIR/${label}.plist"
  if [[ ! -f "$installed" ]]; then
    echo "  [warn] $label plist not installed (run install-dormant / arm)"
    continue
  fi
  if drift_keys="$(_plist_drift_keys "$template" "$installed")"; then
    echo "  [ok] $label plist env matches gddp.env"
  else
    echo "  [FAIL] $label plist env is stale — re-run bin/arm.sh. Drifted keys:"
    while IFS= read -r key; do
      echo "         - $key"
    done <<< "$drift_keys"
    fail=1
  fi
done

# One dry heartbeat if runtime present (does not require arm)
if [[ -d "$GDDP_RUNTIME_ROOT/scripts" ]]; then
  echo "  running one heartbeat tick (observe logs)..."
  (
    cd "$GDDP_RUNTIME_ROOT"
    export GDDP_REPO_ROOT="${GDDP_REPOS_ROOT}"
    export PYTHONPATH="$GDDP_RUNTIME_ROOT${PYTHONPATH:+:$PYTHONPATH}"
    python3 -m scripts.runtime.heartbeat.runner \
      --project "$GDDP_PROJECT_ID" \
      --repo "$GDDP_PROJECT_REPO" \
      --config-path "$GDDP_CONFIG_PATH" \
      && echo "  [ok] heartbeat runner exited 0" \
      || { echo "  [FAIL] heartbeat runner non-zero"; fail=1; }
  )
fi

if [[ "$fail" -ne 0 ]]; then
  echo "=== smoke: FAIL ==="
  exit 1
fi
echo "=== smoke: OK ==="
