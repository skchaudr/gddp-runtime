#!/usr/bin/env bash
# Stop + disable Rig 1 heartbeat LaunchAgent. Does not touch mini labels.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_mac

launchctl bootout "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
launchctl disable "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true

# Re-render dormant template (RunAtLoad=false) if kit present
if [[ -f "$KIT_ROOT/launchd/${HEARTBEAT_LABEL}.plist" ]]; then
  render_plist "$KIT_ROOT/launchd/${HEARTBEAT_LABEL}.plist" "$HEARTBEAT_PLIST"
  launchctl bootstrap "gui/$(id -u)" "$HEARTBEAT_PLIST" 2>/dev/null || true
  launchctl disable "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
fi

echo "rig1-heartbeat: disarmed (service stopped/disabled)"
echo "  Re-arm: RIG1_HEARTBEAT_ARM=1 bash $KIT_ROOT/bin/arm.sh"
