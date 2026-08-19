# Addendum: piobs observability in Pi Orchestrator v1

## How piobs works

**Hub**: BigPi (100.78.181.120:43190), systemd user service `piobs-hub.service`. Central observability server. All hosts report to it.

**Client wiring** (`piobs install` / `install-client.sh`):
1. Copies `vendor/extension/pi-observability.ts` to `~/.config/pi-observability/vendor/`
2. Adds the extension path to `~/.pi/agent/settings.json` under `extensions` — loads globally for every Pi session on that host
3. Creates a host overlay env file (`~/.config/pi-observability/env.air`, `env.mini`, etc.) that sources the shared `env` (token + server URL) and sets `OBS_NAME`, `OBS_TAG`, `OBS_POOL`
4. Adds a shell hook to `~/.config/zsh/local.zsh` that sources the host overlay on login

**What the extension does**: reads `OBS_SERVER_URL`, `OBS_AUTH_TOKEN`, `OBS_NAME`, `OBS_TAG`, `OBS_POOL` from the environment. Streams session lifecycle events (session start, turn start/end, tool calls, usage) to the hub. No raw prompts or tool output sent — only metadata and spans.

**`piobs pi`**: convenience wrapper that sources the host env overlay and execs `pi "$@"`. Equivalent to manually sourcing the env then running pi.

**Current state on sab-air** (verified):
- `~/.config/pi-observability/env` exists (token + server URL)
- `~/.config/pi-observability/env.air` exists (`OBS_NAME=air`, `OBS_TAG=host:air`)
- Extension in `~/.pi/agent/settings.json`: `/Users/sab-mini/.config/pi-observability/vendor/extension/pi-observability.ts`
- `piobs` on PATH at `/Users/sab-mini/.local/bin/piobs`
- Shell hook sources `env.air` on login

So on sab-air, any Pi session from a login shell already has observability. The extension loads from settings.json, and the env vars are set from the shell hook.

## Three Pi surfaces that need observability

### 1. Executor Pi (pi_rpc_adapter) — already wired

`_observability_env` in `scripts/adapters/pi_rpc_adapter.py` reads `~/.config/pi-observability/env` for the base config (token, server URL), then overrides:

```
OBS_POOL = "gddp"
OBS_NAME = "gddp-<project_id>"
OBS_TAG  = "host:<hostname>,gddp,project:<project_id>"
```

These are passed as env vars to the `pi --mode rpc` subprocess. The extension picks them up and streams events to the hub with project-level identification.

This already works on any host that has piobs installed, including sab-air. No change needed.

### 2. Orchestrator Pi (the launcher script) — needs explicit wiring

The launcher script (`deploy/bin/gddp-orchestrator`) must source the piobs env and set role-identifying tags. Without this, the orchestrator session is either invisible (no env vars) or mislabeled (inherits `host:air` without a role tag).

Updated launcher:

```bash
#!/usr/bin/env bash
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$KIT_ROOT/deploy/mini-heartbeat/env/gddp.env"

# Source pi-observability fleet env (same as `piobs pi`)
if [[ -r "$HOME/.config/pi-observability/env" ]]; then
  source "$HOME/.config/pi-observability/env"
  # Override for orchestrator role — distinguish from executor sessions
  export OBS_POOL="gddp"
  export OBS_NAME="orchestrator-$(hostname -s)"
  export OBS_TAG="host:$(hostname -s),gddp,role:orchestrator"
fi

# Block gddp steer — reserved for the human operator
gddp() { [[ "$1" == "steer" ]] && { echo "gddp steer is reserved for the human operator" >&2; return 1; }; command gddp "$@"; }
export -f gddp

exec pi \
  --model "${GDDP_PI_RPC_MODEL:-openai-codex/gpt-5.6-sol}" \
  --tools read,bash,grep,find,ls,subagent \
  --append-system-prompt "@$KIT_ROOT/deploy/orchestrator/doctrine.md" \
  --cwd "$GDDP_RUNTIME_ROOT" \
  "$@"
```

What this gives you in the piobs dashboard:
- `OBS_NAME=orchestrator-air` — distinguishable from `gddp-myapi-part2` (executor)
- `OBS_TAG=host:air,gddp,role:orchestrator` — filterable by role
- `OBS_POOL=gddp` — grouped with executor sessions in the same pool

### 3. Evaluator Pi — context-dependent

The evaluator has two paths:

**Direct path** (`gddp verify node --live`): runs `verify_job_return` in `scripts/runtime/verification/bridge.py`, which calls the DeepSeek API directly from Python. This is not a Pi session — observability is a separate concern (the evaluator's own logging, not piobs).

**Pi-harness path** (the `pi-evaluator-harness` node, `.pi/prompts/gddp-eval-receipt.md`): dispatches a `reviewer` subagent to run the evaluation through Pi. This IS a Pi session. If launched from the orchestrator session (via `subagent` tool), it inherits the orchestrator's observability env — but with the subagent's own session identity. If launched independently, it needs its own piobs env sourcing.

For v1, the evaluator's observability is inherited when dispatched as a subagent from the orchestrator. A standalone evaluator launcher (if needed later) would follow the same pattern: source piobs env, set `OBS_NAME=evaluator-<host>`, `OBS_TAG=host:<host>,gddp,role:evaluator`.

## What you see in the dashboard

With all three surfaces wired, `piobs ui` shows:

```
Pool: gddp
  orchestrator-air     role:orchestrator    [live]    turns: 12    tools: 8
  gddp-myapi-part2     project:myapi-part2  [live]    turns: 3     tools: 15
  gddp-myapi-part2     project:myapi-part2  [done]    turns: 8     tools: 22
```

You can filter by tag:
- `role:orchestrator` — just the orchestrator
- `project:myapi-part2` — just executors for that project
- `host:air` — everything on sab-air

## What does NOT change

- The pi-observability extension is already installed on sab-air (in settings.json). No new extension installation needed.
- The hub on BigPi is already running. No new infrastructure.
- The executor Pi (pi_rpc_adapter) already handles observability via `_observability_env`. No adapter change.
- The `piobs` CLI is already on PATH on sab-air. No new binary.

The only addition is the piobs env sourcing + role tags in the orchestrator launcher script (~5 lines).
