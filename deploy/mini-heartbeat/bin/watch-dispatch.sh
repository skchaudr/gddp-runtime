#!/usr/bin/env bash
# watch-dispatch.sh — 6-pane tmux rig for watching a node dispatch end to end.
#
# Lanes (tiled):
#   1. intake log        (webhook arrives, event row written)
#   2. heartbeat log     (tick narrative: found/claim/classify/dispatch)
#   3. events table      (latest rows for this repo)
#   4. jobs table        (status + queue_state side by side)
#   5. issues w/ labels  (the 'jules' label appearing = handoff moment)
#   6. PRs               (Jules' PRs showing up)
#
# Usage:
#   bash deploy/mini-heartbeat/bin/watch-dispatch.sh
#   bash deploy/mini-heartbeat/bin/watch-dispatch.sh --fresh
#
# Helpers (after sourcing deploy/mini-heartbeat/bin/shell-aliases.sh):
#   gddp-watch          attach or create
#   gddp-watch-fresh    kill broken/partial session and recreate
#   gddp-watch-status   pane count + running state
set -euo pipefail

SESSION=gddp-watch
EXPECTED_PANES=6
# Default tmux size (80x24) only fits ~4 panes; need headroom for 6 tiled lanes.
SESSION_WIDTH=300
SESSION_HEIGHT=80
REPO_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
DB="$REPO_DIR/db/queue.db"
GH_REPO=skchaudr/gddp-runtime
TMUX_CONF="$(dirname "$0")/../tmux/gddp-minimal.conf"

_tmux() {
  tmux -f "$TMUX_CONF" "$@"
}

_fresh=0
for arg in "$@"; do
  case "$arg" in
    --fresh|-f) _fresh=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
  esac
done

if [[ "$_fresh" -eq 1 ]]; then
  _tmux kill-session -t "$SESSION" 2>/dev/null || true
fi

if _tmux has-session -t "$SESSION" 2>/dev/null; then
  pane_count="$(_tmux list-panes -t "$SESSION" 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$pane_count" -lt "$EXPECTED_PANES" ]]; then
    echo "session '$SESSION' has $pane_count/$EXPECTED_PANES panes (likely a partial build)" >&2
    echo "rebuild with: gddp-watch-fresh   or: $0 --fresh" >&2
  else
    echo "session '$SESSION' already running — attaching"
  fi
  if [[ -n "${TMUX:-}" ]]; then
    exec tmux -f "$TMUX_CONF" switch-client -t "$SESSION"
  else
    exec tmux -f "$TMUX_CONF" attach -t "$SESSION"
  fi
fi

_tmux new-session -d -s "$SESSION" -c "$REPO_DIR" -x "$SESSION_WIDTH" -y "$SESSION_HEIGHT"

# Lane 1+2: live service logs. tail -F survives log rotation/recreation.
_tmux send-keys -t "$SESSION" \
  "tail -F ~/Library/Logs/gddp-intake.log" C-m

_tmux split-window -t "$SESSION" -c "$REPO_DIR"
_tmux send-keys -t "$SESSION" \
  "tail -F ~/Library/Logs/gddp-heartbeat.log" C-m

# Lane 3: events table. -readonly so the watcher can never hold a write lock.
_tmux split-window -t "$SESSION" -c "$REPO_DIR"
_tmux send-keys -t "$SESSION" \
  "while true; do clear; date '+%H:%M:%S  EVENTS'; sqlite3 -readonly -column -header '$DB' \"SELECT substr(event_id,5) AS event, event_type, issue_number AS num, status FROM events WHERE repo='$GH_REPO' ORDER BY rowid DESC LIMIT 8;\"; sleep 10; done" C-m

# Lane 4: jobs table — status AND queue_state so divergence is visible.
_tmux split-window -t "$SESSION" -c "$REPO_DIR"
_tmux send-keys -t "$SESSION" \
  "while true; do clear; date '+%H:%M:%S  JOBS'; sqlite3 -readonly -column -header '$DB' \"SELECT substr(job_id,5) AS job, node_id, status, queue_state FROM jobs ORDER BY rowid DESC LIMIT 8;\"; sleep 10; done" C-m

# Lane 5+6: GitHub side. 45s interval keeps gh API usage modest.
_tmux split-window -t "$SESSION" -c "$REPO_DIR"
_tmux send-keys -t "$SESSION" \
  "while true; do clear; date '+%H:%M:%S  ISSUES (jules label = dispatched)'; gh issue list -R $GH_REPO --limit 8 --json number,title,labels --template '{{range .}}#{{.number}} {{.title}} [{{range .labels}}{{.name}} {{end}}]{{\"\\n\"}}{{end}}'; sleep 45; done" C-m

_tmux split-window -t "$SESSION" -c "$REPO_DIR"
_tmux send-keys -t "$SESSION" \
  "while true; do clear; date '+%H:%M:%S  PRS'; gh pr list -R $GH_REPO --limit 8; sleep 45; done" C-m

_tmux select-layout -t "$SESSION" tiled

pane_count="$(_tmux list-panes -t "$SESSION" | wc -l | tr -d ' ')"
if [[ "$pane_count" -lt "$EXPECTED_PANES" ]]; then
  echo "failed to create $EXPECTED_PANES panes (got $pane_count)" >&2
  _tmux kill-session -t "$SESSION" 2>/dev/null || true
  exit 1
fi

# From inside tmux, attach nests badly — switch the client instead.
if [[ -n "${TMUX:-}" ]]; then
  exec tmux -f "$TMUX_CONF" switch-client -t "$SESSION"
else
  exec tmux -f "$TMUX_CONF" attach -t "$SESSION"
fi