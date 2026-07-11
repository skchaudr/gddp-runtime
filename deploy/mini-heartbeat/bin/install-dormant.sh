#!/usr/bin/env bash
# Place mini-heartbeat LaunchAgents disabled. Does not start services.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_mac

mkdir -p "$LAUNCH_AGENTS_DIR" "$HOME/Library/Logs" \
  "$GDDP_RUNTIME_ROOT"/{db,events/raw,events/normalized,jobs}

if [[ ! -d "$GDDP_RUNTIME_ROOT/scripts" ]]; then
  echo "Missing runtime scripts at $GDDP_RUNTIME_ROOT — clone gddp-runtime first." >&2
  exit 1
fi
if [[ ! -d "$GDDP_CONFIG_PATH/graphs" ]]; then
  echo "Missing config graphs at $GDDP_CONFIG_PATH — clone gddp-config first." >&2
  exit 1
fi

if [[ ! -f "$KIT_ROOT/env/gddp.env" && -f "$KIT_ROOT/env/gddp.env.example" ]]; then
  cp "$KIT_ROOT/env/gddp.env.example" "$KIT_ROOT/env/gddp.env"
  echo "Wrote $KIT_ROOT/env/gddp.env from example (edit paths if needed)."
fi

render_plist "$KIT_ROOT/launchd/${INTAKE_LABEL}.plist" "$INTAKE_PLIST"
render_plist "$KIT_ROOT/launchd/${HEARTBEAT_LABEL}.plist" "$HEARTBEAT_PLIST"

# Load definitions without running (RunAtLoad=false in templates).
# bootout first so re-install is idempotent.
launchctl bootout "gui/$(id -u)/${INTAKE_LABEL}" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$INTAKE_PLIST" 2>/dev/null || \
  launchctl load -w "$INTAKE_PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HEARTBEAT_PLIST" 2>/dev/null || \
  launchctl load -w "$HEARTBEAT_PLIST" 2>/dev/null || true

# Ensure disabled after load (some macOS versions start interval jobs on load).
launchctl disable "gui/$(id -u)/${INTAKE_LABEL}" 2>/dev/null || true
launchctl disable "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
launchctl stop "$INTAKE_LABEL" 2>/dev/null || true
launchctl stop "$HEARTBEAT_LABEL" 2>/dev/null || true

echo "mini-heartbeat: dormant install OK"
echo "  runtime:   $GDDP_RUNTIME_ROOT"
echo "  config:    $GDDP_CONFIG_PATH"
echo "  plists:    $INTAKE_PLIST"
echo "             $HEARTBEAT_PLIST"
echo "  arm later: MINI_HEARTBEAT_ARM=1 bash $KIT_ROOT/bin/arm.sh"
