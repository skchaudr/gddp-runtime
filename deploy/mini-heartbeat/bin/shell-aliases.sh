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

_gddp_zellij_config_dir() {
  printf '%s' "$(_gddp_runtime_root)/deploy/mini-heartbeat/zellij"
}

gddp-watch() {
  ZELLIJ_CONFIG_DIR="$(_gddp_zellij_config_dir)" \
    bash "$(_gddp_runtime_root)/deploy/mini-heartbeat/bin/watch-dispatch.sh" "$@"
}

gddp-watch-fresh() {
  ZELLIJ_CONFIG_DIR="$(_gddp_zellij_config_dir)" \
    zellij kill-session gddp-watch 2>/dev/null || true
  gddp-watch
}

gddp-watch-status() {
  if ! ZELLIJ_CONFIG_DIR="$(_gddp_zellij_config_dir)" \
      zellij list-sessions -s -n 2>/dev/null | grep -qx gddp-watch; then
    echo "gddp-watch: not running"
    return 1
  fi
  echo "gddp-watch: running (6-pane layout)"
}