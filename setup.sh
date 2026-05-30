#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

echo "=== setup: gddp-runtime ==="

# 1. Python
python3 --version 2>&1 || { echo "✗ python3 not found"; exit 1; }
echo "✓ python3 $(python3 --version 2>&1 | awk '{print $2}')"

# 2. Flask (only external dep — scripts are mostly stdlib)
pip install -q flask 2>/dev/null && echo "✓ flask installed" || echo "⚠ flask install failed"

# 3. Verify scripts exist
for f in scripts/intake_server.py scripts/dry_run.py scripts/init_db.py scripts/heartbeat.py; do
  [ -f "$f" ] && echo "✓ $f" || echo "⚠ $f missing"
done

# 4. Run dry-flow test (no network, SQLite only)
python3 scripts/dry_run.py 2>/dev/null && echo "✓ dry_run.py passes" || echo "⚠ dry_run.py failed"

# 5. Snapshot
echo "--- snapshot ---"
echo "  branch:  $(git branch --show-current 2>/dev/null || echo 'not a git repo')"
echo "  python:  $(python3 --version 2>&1)"
echo "  setup:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
