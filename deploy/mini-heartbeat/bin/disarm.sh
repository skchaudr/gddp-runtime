#!/usr/bin/env bash
# Stop + disable mini-heartbeat LaunchAgents (park mini; does not touch big-ssd).
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_mac

launchctl bootout "gui/$(id -u)/${INTAKE_LABEL}" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
launchctl disable "gui/$(id -u)/${INTAKE_LABEL}" 2>/dev/null || true
launchctl disable "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true

# Re-render dormant templates (RunAtLoad=false) if kit present
if [[ -f "$KIT_ROOT/launchd/${INTAKE_LABEL}.plist" ]]; then
  render_plist "$KIT_ROOT/launchd/${INTAKE_LABEL}.plist" "$INTAKE_PLIST"
  render_plist "$KIT_ROOT/launchd/${HEARTBEAT_LABEL}.plist" "$HEARTBEAT_PLIST"
  launchctl bootstrap "gui/$(id -u)" "$INTAKE_PLIST" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$HEARTBEAT_PLIST" 2>/dev/null || true
  launchctl disable "gui/$(id -u)/${INTAKE_LABEL}" 2>/dev/null || true
  launchctl disable "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
fi

echo "mini-heartbeat: disarmed (services stopped/disabled)"
echo "  Re-arm: MINI_HEARTBEAT_ARM=1 bash $KIT_ROOT/bin/arm.sh"
