#!/usr/bin/env bash
# Park the *current* Linux control plane (big-ssd) before arming mini.
# Safe-ish: stops intake, comments the heartbeat crontab line. Idempotent.
set -euo pipefail

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "disarm-source is for the Linux plane (big-ssd). On mini use disarm.sh." >&2
  exit 1
fi

echo "=== mini-heartbeat: disarm source plane ($(hostname)) ==="

if systemctl is-active --quiet gddp-intake 2>/dev/null; then
  sudo systemctl stop gddp-intake
  echo "  gddp-intake: stopped"
else
  echo "  gddp-intake: not active"
fi

# Disable so reboot does not resurrect until re-enabled
if systemctl is-enabled --quiet gddp-intake 2>/dev/null; then
  sudo systemctl disable gddp-intake
  echo "  gddp-intake: disabled"
fi

CRON_TMP="$(mktemp)"
crontab -l 2>/dev/null >"$CRON_TMP" || true
if grep -q 'scripts.runtime.heartbeat.runner' "$CRON_TMP" 2>/dev/null; then
  # Comment active heartbeat lines; leave already-commented alone
  sed -i.bak -E \
    's|^([[:space:]]*[^#].*scripts\.runtime\.heartbeat\.runner.*)$|# mini-heartbeat parked: \1|' \
    "$CRON_TMP"
  crontab "$CRON_TMP"
  echo "  crontab: heartbeat line(s) commented"
else
  echo "  crontab: no active heartbeat runner line found"
fi
rm -f "$CRON_TMP" "${CRON_TMP}.bak" 2>/dev/null || true

echo "Source plane parked. Arm mini with:"
echo "  MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh"
echo "Restore big-ssd later: sudo systemctl enable --now gddp-intake"
echo "  and uncomment the heartbeat line in crontab -e"
