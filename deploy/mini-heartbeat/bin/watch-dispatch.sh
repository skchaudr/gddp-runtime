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
# Usage: bash deploy/mini-heartbeat/bin/watch-dispatch.sh
set -euo pipefail

SESSION=gddp-watch
REPO_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
DB="$REPO_DIR/db/queue.db"
GH_REPO=skchaudr/gddp-runtime

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "session '$SESSION' already running — attaching"
  exec tmux attach -t "$SESSION"
fi

tmux new-session -d -s "$SESSION" -c "$REPO_DIR"

# Lane 1+2: live service logs. tail -F survives log rotation/recreation.
tmux send-keys -t "$SESSION" \
  "tail -F ~/Library/Logs/gddp-intake.log" C-m

tmux split-window -t "$SESSION" -c "$REPO_DIR"
tmux send-keys -t "$SESSION" \
  "tail -F ~/Library/Logs/gddp-heartbeat.log" C-m

# Lane 3: events table. -readonly so the watcher can never hold a write lock.
tmux split-window -t "$SESSION" -c "$REPO_DIR"
tmux send-keys -t "$SESSION" \
  "while true; do clear; date '+%H:%M:%S  EVENTS'; sqlite3 -readonly -column -header '$DB' \"SELECT substr(event_id,5) AS event, event_type, issue_number AS num, status FROM events WHERE repo='$GH_REPO' ORDER BY rowid DESC LIMIT 8;\"; sleep 10; done" C-m

# Lane 4: jobs table — status AND queue_state so divergence is visible.
tmux split-window -t "$SESSION" -c "$REPO_DIR"
tmux send-keys -t "$SESSION" \
  "while true; do clear; date '+%H:%M:%S  JOBS'; sqlite3 -readonly -column -header '$DB' \"SELECT substr(job_id,5) AS job, node_id, status, queue_state FROM jobs ORDER BY rowid DESC LIMIT 8;\"; sleep 10; done" C-m

# Lane 5+6: GitHub side. 45s interval keeps gh API usage modest.
tmux split-window -t "$SESSION" -c "$REPO_DIR"
tmux send-keys -t "$SESSION" \
  "while true; do clear; date '+%H:%M:%S  ISSUES (jules label = dispatched)'; gh issue list -R $GH_REPO --limit 8 --json number,title,labels --template '{{range .}}#{{.number}} {{.title}} [{{range .labels}}{{.name}} {{end}}]{{\"\\n\"}}{{end}}'; sleep 45; done" C-m

tmux split-window -t "$SESSION" -c "$REPO_DIR"
tmux send-keys -t "$SESSION" \
  "while true; do clear; date '+%H:%M:%S  PRS'; gh pr list -R $GH_REPO --limit 8; sleep 45; done" C-m

tmux select-layout -t "$SESSION" tiled

# From inside tmux, attach nests badly — switch the client instead.
if [ -n "${TMUX:-}" ]; then
  exec tmux switch-client -t "$SESSION"
else
  exec tmux attach -t "$SESSION"
fi
