#!/usr/bin/env bash
# watch-dispatch.sh — 6-pane zellij rig for watching a node dispatch end to end.
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
#   gddp-watch-fresh    kill session and recreate
#   gddp-watch-status   running state
#
# Cycling (normal mode): Tab / Shift+Tab, p, or hjkl.
set -euo pipefail

SESSION=gddp-watch
EXPECTED_PANES=6
REPO_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
DB="$REPO_DIR/db/queue.db"
GH_REPO=skchaudr/gddp-runtime
ZELLIJ_CONFIG_DIR="$(dirname "$0")/../zellij"
export ZELLIJ_CONFIG_DIR
ZELLIJ_CMD=(env ZELLIJ_CONFIG_DIR="$ZELLIJ_CONFIG_DIR" zellij)

_kdl_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

_session_exists() {
  "${ZELLIJ_CMD[@]}" list-sessions -s -n 2>/dev/null | grep -qx "$SESSION"
}

_generate_layout() {
  local repo db events_cmd jobs_cmd issues_cmd prs_cmd
  repo="$(_kdl_escape "$REPO_DIR")"
  db="$(_kdl_escape "$DB")"

  events_cmd="while true; do clear; date '+%H:%M:%S  EVENTS'; sqlite3 -readonly -column -header '$DB' \"SELECT substr(event_id,5) AS event, event_type, issue_number AS num, status FROM events WHERE repo='$GH_REPO' ORDER BY rowid DESC LIMIT 8;\"; sleep 10; done"
  jobs_cmd="while true; do clear; date '+%H:%M:%S  JOBS'; sqlite3 -readonly -column -header '$DB' \"SELECT substr(job_id,5) AS job, node_id, status, queue_state FROM jobs ORDER BY rowid DESC LIMIT 8;\"; sleep 10; done"
  issues_cmd="while true; do clear; date '+%H:%M:%S  ISSUES (jules label = dispatched)'; gh issue list -R $GH_REPO --limit 8 --json number,title,labels --template '{{range .}}#{{.number}} {{.title}} [{{range .labels}}{{.name}} {{end}}]{{\"\\n\"}}{{end}}'; sleep 45; done"
  prs_cmd="while true; do clear; date '+%H:%M:%S  PRS'; gh pr list -R $GH_REPO --limit 8; sleep 45; done"

  cat <<EOF
layout {
    cwd "$repo"
    pane split_direction="vertical" {
        pane split_direction="horizontal" {
            pane name="intake" command="tail" {
                args "-F" "$(_kdl_escape "$HOME/Library/Logs/gddp-intake.log")"
            }
            pane name="heartbeat" command="tail" {
                args "-F" "$(_kdl_escape "$HOME/Library/Logs/gddp-heartbeat.log")"
            }
        }
        pane split_direction="horizontal" {
            pane name="events" command="bash" {
                args "-c" "$(_kdl_escape "$events_cmd")"
            }
            pane name="jobs" command="bash" {
                args "-c" "$(_kdl_escape "$jobs_cmd")"
            }
        }
        pane split_direction="horizontal" {
            pane name="issues" command="bash" {
                args "-c" "$(_kdl_escape "$issues_cmd")"
            }
            pane name="prs" command="bash" {
                args "-c" "$(_kdl_escape "$prs_cmd")"
            }
        }
    }
    pane size=1 borderless=true {
        plugin location="zellij:compact-bar"
    }
}
EOF
}

_fresh=0
for arg in "$@"; do
  case "$arg" in
    --fresh|-f) _fresh=1 ;;
    -h|--help)
      sed -n '2,22p' "$0"
      exit 0
      ;;
  esac
done

if [[ "$_fresh" -eq 1 ]]; then
  "${ZELLIJ_CMD[@]}" kill-session "$SESSION" 2>/dev/null || true
fi

if _session_exists; then
  echo "session '$SESSION' already running — attaching"
  if [[ -n "${ZELLIJ:-}" ]]; then
    exec "${ZELLIJ_CMD[@]}" action switch-session "$SESSION"
  else
    exec "${ZELLIJ_CMD[@]}" attach "$SESSION"
  fi
fi

layout_file="$(mktemp /tmp/gddp-watch-XXXXXX.kdl)"
trap 'rm -f "$layout_file"' EXIT
_generate_layout > "$layout_file"

echo "starting session '$SESSION' ($EXPECTED_PANES panes)"
exec "${ZELLIJ_CMD[@]}" -n "$layout_file" -s "$SESSION"