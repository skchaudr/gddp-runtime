#!/usr/bin/env bash
# init.sh — idempotent environment guard for PROBE-2A.
# Asserts preconditions. Creates nothing. Commits nothing.
set -euo pipefail

cd /Users/sab-mini/probe2-gddp/repoA-wt-probe2a

# 1. GDDP_RECEIPTS_PATH must be set and point to the expected ledger path.
if [ -z "${GDDP_RECEIPTS_PATH:-}" ]; then
  echo "FATAL: GDDP_RECEIPTS_PATH is not set" >&2
  exit 1
fi
if [ "$GDDP_RECEIPTS_PATH" != "/Users/sab-mini/probe2-gddp/receiptsA.jsonl" ]; then
  echo "FATAL: GDDP_RECEIPTS_PATH is '$GDDP_RECEIPTS_PATH', expected '/Users/sab-mini/probe2-gddp/receiptsA.jsonl'" >&2
  exit 1
fi

# 2. gddp-node-receipt must be on PATH and executable.
if ! command -v gddp-node-receipt >/dev/null 2>&1; then
  echo "FATAL: gddp-node-receipt not found on PATH" >&2
  exit 1
fi

# 3. python3 and pytest must be runnable.
if ! command -v python3 >/dev/null 2>&1; then
  echo "FATAL: python3 not found on PATH" >&2
  exit 1
fi
python3 -m pytest --version >/dev/null 2>&1 || {
  echo "FATAL: pytest not available via python3 -m pytest" >&2
  exit 1
}

# 4. Worktree must be on branch probe2a.
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "probe2a" ]; then
  echo "FATAL: expected branch 'probe2a', got '$BRANCH'" >&2
  exit 1
fi

echo "init.sh OK: GDDP_RECEIPTS_PATH=$GDDP_RECEIPTS_PATH, branch=$BRANCH"
