#!/usr/bin/env bash
# Enable + start mini-heartbeat services. Refuses without explicit arm flag.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_mac

if [[ "${MINI_HEARTBEAT_ARM:-}" != "1" ]]; then
  cat <<EOF >&2
Refusing to arm. Only one control plane should run intake + heartbeat.

  MINI_HEARTBEAT_ARM=1 bash $KIT_ROOT/bin/arm.sh

Before arming: run disarm-source.sh on big-ssd (or accept dual-plane risk).
EOF
  exit 2
fi

if [[ ! -f "$INTAKE_PLIST" || ! -f "$HEARTBEAT_PLIST" ]]; then
  echo "Plists missing — run install-dormant.sh first." >&2
  exit 1
fi

# Re-render in case env changed
render_plist "$KIT_ROOT/launchd/${INTAKE_LABEL}.plist" "$INTAKE_PLIST"
render_plist "$KIT_ROOT/launchd/${HEARTBEAT_LABEL}.plist" "$HEARTBEAT_PLIST"

# Flip RunAtLoad true for intake KeepAlive-ish restart via enable+start
# Templates stay false in git; we enable via launchctl, not by rewriting RunAtLoad.

launchctl bootout "gui/$(id -u)/${INTAKE_LABEL}" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true

# Temporarily enable RunAtLoad for this install only
_tmp_intake="$(mktemp)"
_tmp_hb="$(mktemp)"
sed 's|<key>RunAtLoad</key>[[:space:]]*<false/>|<key>RunAtLoad</key>\n  <true/>|; s|<key>KeepAlive</key>[[:space:]]*<false/>|<key>KeepAlive</key>\n  <true/>|' \
  "$INTAKE_PLIST" >"$_tmp_intake"
sed 's|<key>RunAtLoad</key>[[:space:]]*<false/>|<key>RunAtLoad</key>\n  <true/>|' \
  "$HEARTBEAT_PLIST" >"$_tmp_hb"
mv "$_tmp_intake" "$INTAKE_PLIST"
mv "$_tmp_hb" "$HEARTBEAT_PLIST"

launchctl bootstrap "gui/$(id -u)" "$INTAKE_PLIST" 2>/dev/null || launchctl load -w "$INTAKE_PLIST"
launchctl bootstrap "gui/$(id -u)" "$HEARTBEAT_PLIST" 2>/dev/null || launchctl load -w "$HEARTBEAT_PLIST"
launchctl enable "gui/$(id -u)/${INTAKE_LABEL}" 2>/dev/null || true
launchctl enable "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/${INTAKE_LABEL}" 2>/dev/null || launchctl start "$INTAKE_LABEL"
# heartbeat is interval-based; kick once so arm is observable
launchctl kickstart -k "gui/$(id -u)/${HEARTBEAT_LABEL}" 2>/dev/null || launchctl start "$HEARTBEAT_LABEL"

echo "mini-heartbeat: ARMED"
echo "  logs: ~/Library/Logs/gddp-intake.log"
echo "        ~/Library/Logs/gddp-heartbeat.log"
echo "  smoke: bash $KIT_ROOT/bin/smoke.sh"
echo "  disarm: bash $KIT_ROOT/bin/disarm.sh"
