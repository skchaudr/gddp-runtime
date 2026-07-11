#!/usr/bin/env bash
# Shared paths for mini-heartbeat scripts. Source only; do not execute.

set -euo pipefail

_KIT_BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(cd "$_KIT_BIN/.." && pwd)"
REPO_ROOT="$(cd "$KIT_ROOT/../.." && pwd)"

# Prefer env file if present (local, not committed)
_ENV_FILE="${MINI_HEARTBEAT_ENV:-$KIT_ROOT/env/gddp.env}"
if [[ -f "$_ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$_ENV_FILE"
fi

GDDP_RUNTIME_ROOT="${GDDP_RUNTIME_ROOT:-$HOME/repos/gddp-runtime}"
GDDP_CONFIG_PATH="${GDDP_CONFIG_PATH:-$HOME/repos/gddp-config}"
GDDP_REPOS_ROOT="${GDDP_REPOS_ROOT:-$HOME/repos}"
GDDP_PROJECT_ID="${GDDP_PROJECT_ID:-gddp-runtime}"
GDDP_PROJECT_REPO="${GDDP_PROJECT_REPO:-skchaudr/gddp-runtime}"

LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
INTAKE_LABEL="com.gddp.intake"
HEARTBEAT_LABEL="com.gddp.heartbeat"
INTAKE_PLIST="$LAUNCH_AGENTS_DIR/${INTAKE_LABEL}.plist"
HEARTBEAT_PLIST="$LAUNCH_AGENTS_DIR/${HEARTBEAT_LABEL}.plist"

render_plist() {
  local src="$1"
  local dest="$2"
  sed \
    -e "s|__HOME__|${HOME}|g" \
    -e "s|__GDDP_RUNTIME_ROOT__|${GDDP_RUNTIME_ROOT}|g" \
    -e "s|__GDDP_CONFIG_PATH__|${GDDP_CONFIG_PATH}|g" \
    -e "s|__GDDP_REPOS_ROOT__|${GDDP_REPOS_ROOT}|g" \
    -e "s|__GDDP_PROJECT_ID__|${GDDP_PROJECT_ID}|g" \
    -e "s|__GDDP_PROJECT_REPO__|${GDDP_PROJECT_REPO}|g" \
    "$src" >"$dest"
}

require_mac() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "mini-heartbeat launchd helpers expect macOS (Darwin). Got: $(uname -s)" >&2
    echo "On Linux control plane use deploy/BIGPI_RUNBOOK.md instead." >&2
    exit 1
  fi
}
