#!/usr/bin/env bash
# setup.sh — Deploy gddp-runtime to Big Pi
# Run once on a fresh Pi.
# For updates after install, use: bash deploy/deploy.sh --restart-intake
# Usage: bash deploy/setup.sh

set -euo pipefail

RUNTIME_ROOT="${GDDP_RUNTIME_ROOT:-${OPCLAW_ROOT:-$HOME/opclaw}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

echo "=== GDDP Runtime Setup ==="

# 1. Create runtime directories (data never goes in the repo)
mkdir -p "$RUNTIME_ROOT"/{db,events/{raw,normalized},jobs,scripts/adapters}
echo "  directories: ok"

# 2. Deploy the current repo snapshot into the runtime scripts dir
bash "$SCRIPT_DIR/deploy/deploy.sh"
echo "  scripts + marker: ok"

# 3. Install systemd service
sudo cp "$SCRIPT_DIR/deploy/gddp-intake.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gddp-intake
echo "  systemd service: ok"

# 4. Initialize DB if not already present
if [ ! -f "$RUNTIME_ROOT/db/queue.db" ]; then
    python3 "$RUNTIME_ROOT/scripts/init_db.py"
    echo "  database: initialized"
else
    echo "  database: already exists, skipping"
fi

echo ""
echo "=== Setup complete ==="
echo "Start intake server: sudo systemctl start gddp-intake"
echo "Check status:        sudo systemctl status gddp-intake"
echo "Check deploy:        cat $RUNTIME_ROOT/.gddp-runtime-deploy.json"
echo "Expose tunnel:       cloudflared tunnel --url http://localhost:5050"
