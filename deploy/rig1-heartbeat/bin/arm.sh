#!/usr/bin/env bash
# Enable + start Rig 1 heartbeat. Refuses without explicit arm flag.
# Heartbeat only — does not install or start intake.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_mac

if [[ "${RIG1_HEARTBEAT_ARM:-}" != "1" ]]; then
  cat <<EOF >&2
Refusing to arm. Rig 1 heartbeat starts only with an explicit flag.

  RIG1_HEARTBEAT_ARM=1 bash $KIT_ROOT/bin/arm.sh

This is additive (async Jules lane). It does not cut over mini or intake.
EOF
  exit 2
fi

if [[ ! -f "$HEARTBEAT_PLIST" ]]; then
  echo "Plist missing — run install-dormant.sh first." >&2
  exit 1
fi

# Re-render in case env changed
render_plist "$KIT_ROOT/launchd/${HEARTBEAT_LABEL}.plist" "$HEARTBEAT_PLIST"

launchctl bootout "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true

# Temporarily enable RunAtLoad for this install only (template stays false in git)
_tmp_hb="$(mktemp)"
sed 's|<key>RunAtLoad</key>[[:space:]]*<false/>|<key>RunAtLoad</key>\n  <true/>|' \
  "$HEARTBEAT_PLIST" >"$_tmp_hb"
mv "$_tmp_hb" "$HEARTBEAT_PLIST"

launchctl bootstrap "gui/$(id -u)" "$HEARTBEAT_PLIST" 2>/dev/null || launchctl load -w "$HEARTBEAT_PLIST"
launchctl enable "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
# interval-based; kick once so arm is observable
launchctl kickstart -k "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || launchctl start "$HEARTBEAT_LABEL"

echo "rig1-heartbeat: ARMED"
echo "  label: $HEARTBEAT_LABEL"
echo "  logs:  ~/Library/Logs/gddp-rig1-heartbeat.log"
echo "         ~/Library/Logs/gddp-rig1-heartbeat.err.log"
echo "  disarm: bash $KIT_ROOT/bin/disarm.sh"
