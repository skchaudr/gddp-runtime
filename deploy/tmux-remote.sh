#!/usr/bin/env bash
# tmux-remote.sh — bootstrap or reattach the canonical remote tmux session.
#
# Usage:
#   bash deploy/tmux-remote.sh sab-ssd@ssd-big
#   bash deploy/tmux-remote.sh sab-ssd@ssd-small openclaw

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  bash deploy/tmux-remote.sh <ssh-target> [session-name]

Examples:
  bash deploy/tmux-remote.sh sab-ssd@ssd-big
  bash deploy/tmux-remote.sh sab-ssd@ssd-small openclaw
EOF
}

if (($# < 1 || $# > 2)); then
    usage >&2
    exit 1
fi

SSH_TARGET="$1"
SESSION_NAME="${2:-openclaw}"

case "$SESSION_NAME" in
    *[!A-Za-z0-9_.-]*|'')
        echo "Invalid session name: $SESSION_NAME" >&2
        echo "Use only letters, numbers, dot, underscore, or hyphen." >&2
        exit 1
        ;;
esac

ssh -t "$SSH_TARGET" "bash -lc '
set -euo pipefail

if ! command -v tmux >/dev/null 2>&1; then
  echo \"tmux is not installed on this host.\" >&2
  exit 1
fi

if ! tmux has-session -t \"$SESSION_NAME\" 2>/dev/null; then
  tmux new-session -d -s \"$SESSION_NAME\" -n ops
  tmux new-window -t \"$SESSION_NAME\":1 -n work
  tmux new-window -t \"$SESSION_NAME\":2 -n logs
  tmux set-option -t \"$SESSION_NAME\" remain-on-exit on
  tmux send-keys -t \"$SESSION_NAME\":0 \"cd ~/repos/gddp-runtime 2>/dev/null || cd ~\" C-m
  tmux send-keys -t \"$SESSION_NAME\":1 \"cd ~/repos/gddp-runtime 2>/dev/null || cd ~\" C-m
  tmux send-keys -t \"$SESSION_NAME\":2 \"cd ~/repos/gddp-runtime 2>/dev/null || cd ~\" C-m
fi

exec tmux attach -t \"$SESSION_NAME\"
'"
