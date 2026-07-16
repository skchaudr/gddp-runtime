#!/usr/bin/env bash
# shell-aliases.sh — helper aliases/functions for mini-heartbeat on sab-mini.
#
# Zsh (recommended):
#   source ~/repos/gddp-runtime/deploy/mini-heartbeat/bin/shell-aliases.sh
#
# One-liner for .zshrc:
#   [[ -f ~/repos/gddp-runtime/deploy/mini-heartbeat/bin/shell-aliases.sh ]] && \
#     source ~/repos/gddp-runtime/deploy/mini-heartbeat/bin/shell-aliases.sh

_gddp_runtime_root() {
  if [[ -n "${GDDP_RUNTIME_ROOT:-}" && -d "$GDDP_RUNTIME_ROOT" ]]; then
    printf '%s' "$GDDP_RUNTIME_ROOT"
    return 0
  fi
  local here="$PWD"
  while [[ "$here" != "/" ]]; do
    if [[ -f "$here/deploy/mini-heartbeat/bin/watch-dispatch.sh" ]]; then
      printf '%s' "$here"
      return 0
    fi
    here="$(dirname "$here")"
  done
  printf '%s' "$HOME/repos/gddp-runtime"
}

gddp-watch() {
  bash "$(_gddp_runtime_root)/deploy/mini-heartbeat/bin/watch-dispatch.sh" "$@"
}

gddp-watch-fresh() {
  local root="$(_gddp_runtime_root)"
  local conf="$root/deploy/mini-heartbeat/tmux/gddp-minimal.conf"
  tmux -f "$conf" kill-session -t gddp-watch 2>/dev/null || true
  gddp-watch
}

gddp-watch-status() {
  local root="$(_gddp_runtime_root)"
  local conf="$root/deploy/mini-heartbeat/tmux/gddp-minimal.conf"
  if ! tmux -f "$conf" has-session -t gddp-watch 2>/dev/null; then
    echo "gddp-watch: not running"
    return 1
  fi
  local panes
  panes="$(tmux -f "$conf" list-panes -t gddp-watch 2>/dev/null | wc -l | tr -d ' ')"
  echo "gddp-watch: running ($panes panes)"
}