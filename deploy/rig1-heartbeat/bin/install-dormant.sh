#!/usr/bin/env bash
# Place Rig 1 heartbeat LaunchAgent disabled. Does not start services.
# Heartbeat only — no intake. Additive third lane; does not touch mini labels.
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
if [[ ! -x "$GDDP_PYTHON" ]]; then
  echo "Python not executable at $GDDP_PYTHON — create .venv or set GDDP_PYTHON." >&2
  exit 1
fi

if [[ ! -f "$KIT_ROOT/env/gddp.env" && -f "$KIT_ROOT/env/gddp.env.example" ]]; then
  cp "$KIT_ROOT/env/gddp.env.example" "$KIT_ROOT/env/gddp.env"
  echo "Wrote $KIT_ROOT/env/gddp.env from example (edit paths if needed)."
fi

render_plist "$KIT_ROOT/launchd/${HEARTBEAT_LABEL}.plist" "$HEARTBEAT_PLIST"

# Load definition without running (RunAtLoad=false in template).
# bootout first so re-install is idempotent.
launchctl bootout "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HEARTBEAT_PLIST" 2>/dev/null || \
  launchctl load -w "$HEARTBEAT_PLIST" 2>/dev/null || true

# Ensure disabled after load (some macOS versions start interval jobs on load).
launchctl disable "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
launchctl stop "$HEARTBEAT_LABEL" 2>/dev/null || true

echo "rig1-heartbeat: dormant install OK"
echo "  runtime:   $GDDP_RUNTIME_ROOT"
echo "  config:    $GDDP_CONFIG_PATH"
echo "  python:    $GDDP_PYTHON"
echo "  label:     $HEARTBEAT_LABEL"
echo "  plist:     $HEARTBEAT_PLIST"
echo "  logs:      ~/Library/Logs/gddp-rig1-heartbeat.log"
echo "             ~/Library/Logs/gddp-rig1-heartbeat.err.log"
echo "  arm later: RIG1_HEARTBEAT_ARM=1 bash $KIT_ROOT/bin/arm.sh"
