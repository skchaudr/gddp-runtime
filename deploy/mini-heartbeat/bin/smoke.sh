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

# DeepSeek via pass (or env) — length only
if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "  [ok] DEEPSEEK_API_KEY set (len=${#DEEPSEEK_API_KEY})"
elif command -v pass >/dev/null 2>&1; then
  if key="$(pass show api/deepseek 2>/dev/null | head -1)" && [[ -n "$key" ]]; then
    echo "  [ok] pass api/deepseek (len=${#key})"
  else
    echo "  [FAIL] pass api/deepseek empty or locked"; fail=1
  fi
else
  echo "  [FAIL] no DEEPSEEK_API_KEY and no pass"; fail=1
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

if [[ "$(uname -s)" == "Darwin" ]]; then
  if launchctl print "gui/$(id -u)/${INTAKE_LABEL}" >/dev/null 2>&1; then
    echo "  [ok] launchd $INTAKE_LABEL registered"
  else
    echo "  [warn] $INTAKE_LABEL not registered (run install-dormant / arm)"
  fi
fi

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
