#!/usr/bin/env bash
# Shared paths for Rig 1 (sab-air) heartbeat scripts. Source only; do not execute.

set -euo pipefail

_KIT_BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(cd "$_KIT_BIN/.." && pwd)"
REPO_ROOT="$(cd "$KIT_ROOT/../.." && pwd)"

# Prefer env file if present (local, not committed)
_ENV_FILE="${RIG1_HEARTBEAT_ENV:-$KIT_ROOT/env/gddp.env}"
if [[ -f "$_ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$_ENV_FILE"
fi

GDDP_RUNTIME_ROOT="${GDDP_RUNTIME_ROOT:-$HOME/repos/gddp-runtime}"
GDDP_CONFIG_PATH="${GDDP_CONFIG_PATH:-$HOME/repos/gddp-config}"
GDDP_REPOS_ROOT="${GDDP_REPOS_ROOT:-$HOME/repos}"
GDDP_PROJECT_ID="${GDDP_PROJECT_ID:-gddp-runtime}"
GDDP_PROJECT_REPO="${GDDP_PROJECT_REPO:-skchaudr/gddp-runtime}"
if [[ -z "${GDDP_PYTHON:-}" ]]; then
  if [[ -x "$GDDP_RUNTIME_ROOT/.venv/bin/python" ]]; then
    GDDP_PYTHON="$GDDP_RUNTIME_ROOT/.venv/bin/python"
  else
    GDDP_PYTHON="/usr/bin/python3"
  fi
fi

# Rig 1 default: Keychain (not pass). Expand $USER at render/source time —
# GDDP_JULES_KEY_CMD is executed via shlex.split, not a shell, so bare $USER
# in the plist would not expand under launchd.
GDDP_JULES_KEY_CMD="${GDDP_JULES_KEY_CMD:-security find-generic-password -w -s jules-api-key -a ${USER}}"
GDDP_DEEPSEEK_KEY_CMD="${GDDP_DEEPSEEK_KEY_CMD:-pass show api/deepseek}"

LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
# Distinct from mini's com.gddp.heartbeat — additive third lane, not a cutover.
HEARTBEAT_LABEL="com.gddp.rig1.heartbeat"
HEARTBEAT_PLIST="$LAUNCH_AGENTS_DIR/${HEARTBEAT_LABEL}.plist"

_xml_escape() {
  local s="$1" r="" i c
  for ((i = 0; i < ${#s}; i++)); do
    c="${s:i:1}"
    case "$c" in
      '&') r+='&amp;' ;;
      '<') r+='&lt;' ;;
      '>') r+='&gt;' ;;
      '"') r+='&quot;' ;;
      *) r+="$c" ;;
    esac
  done
  printf '%s' "$r"
}

_sed_replacement_escape() {
  # sed treats & in the replacement as the matched text
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//&/\\&}"
  printf '%s' "$s"
}

render_plist() {
  local src="$1"
  local dest="$2"
  local deepseek_cmd jules_cmd local_argv local_spool
  deepseek_cmd="$(_sed_replacement_escape "$(_xml_escape "${GDDP_DEEPSEEK_KEY_CMD:-pass show api/deepseek}")")"
  jules_cmd="$(_sed_replacement_escape "$(_xml_escape "${GDDP_JULES_KEY_CMD}")")"
  local_argv="$(_sed_replacement_escape "$(_xml_escape "${GDDP_LOCAL_SUBPROCESS_ARGV:-}")")"
  local_spool="$(_sed_replacement_escape "$(_xml_escape "${GDDP_LOCAL_SUBPROCESS_SPOOL_DIR:-$GDDP_RUNTIME_ROOT/jobs/local-subprocess-spool}")")"
  sed \
    -e "s|__HOME__|${HOME}|g" \
    -e "s|__GDDP_RUNTIME_ROOT__|${GDDP_RUNTIME_ROOT}|g" \
    -e "s|__GDDP_CONFIG_PATH__|${GDDP_CONFIG_PATH}|g" \
    -e "s|__GDDP_REPOS_ROOT__|${GDDP_REPOS_ROOT}|g" \
    -e "s|__GDDP_PROJECT_ID__|${GDDP_PROJECT_ID}|g" \
    -e "s|__GDDP_PROJECT_REPO__|${GDDP_PROJECT_REPO}|g" \
    -e "s|__GDDP_PYTHON__|${GDDP_PYTHON}|g" \
    -e "s|__GDDP_DEEPSEEK_KEY_CMD__|${deepseek_cmd}|g" \
    -e "s|__GDDP_JULES_KEY_CMD__|${jules_cmd}|g" \
    -e "s|__GDDP_LOCAL_SUBPROCESS_ARGV__|${local_argv}|g" \
    -e "s|__GDDP_LOCAL_SUBPROCESS_SPOOL_DIR__|${local_spool}|g" \
    "$src" >"$dest"
}

require_mac() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "rig1-heartbeat launchd helpers expect macOS (Darwin). Got: $(uname -s)" >&2
    exit 1
  fi
}
