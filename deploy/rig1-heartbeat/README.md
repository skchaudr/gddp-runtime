# rig1-heartbeat

Dormant LaunchAgent pack for **Rig 1 / sab-air** (macOS). Heartbeat only —
no intake. Install anytime; nothing ticks until you explicitly arm.

This is an **additive** third lane (async Jules), not a cutover of mini.
Do **not** reuse `deploy/mini-heartbeat/bin/install-dormant.sh` (that kit
installs intake + heartbeat and carries a one-plane exclusivity contract).

## What this is

| Piece | Role |
|---|---|
| `bin/install-dormant.sh` | Write env, load **heartbeat** LaunchAgent **disabled** |
| `bin/arm.sh` | Enable + start heartbeat only (`RIG1_HEARTBEAT_ARM=1`) |
| `bin/disarm.sh` | Stop + disable Rig 1 heartbeat |
| `launchd/com.gddp.rig1.heartbeat.plist` | 300s interval; `RunAtLoad=false` in git |
| `env/gddp.env.example` | Paths + secret resolver commands — no secrets |

**Label:** `com.gddp.rig1.heartbeat` (does not collide with mini's `com.gddp.heartbeat`).

**Logs:** `~/Library/Logs/gddp-rig1-heartbeat.log` and `.err.log` (separate from mini).

**Not in git:** live `db/queue.db`, `env/gddp.env`, Keychain secrets.

## Dormancy contract

1. `install-dormant` may place files and register a plist that does **not** start.
2. `arm.sh` exits unless `RIG1_HEARTBEAT_ARM=1`.
3. No intake agent is installed. GitHub webhooks stay on sab-mini; this rig
   reconciles Jules sessions by polling the adapter.

## Bring-up

```bash
cd ~/repos/gddp-runtime
# on branch with this kit, or after merge
bash deploy/rig1-heartbeat/bin/install-dormant.sh

# proof of rendered job (should show scripts.runtime.heartbeat.runner)
plutil -p ~/Library/LaunchAgents/com.gddp.rig1.heartbeat.plist

# manual one-shot (empty queue is a pass)
export GDDP_JULES_KEY_CMD='security find-generic-password -w -s jules-api-key -a '"$USER"
.venv/bin/python -m scripts.runtime.heartbeat.runner \
  --project gddp-runtime \
  --repo skchaudr/gddp-runtime \
  --config-path "$HOME/repos/gddp-config"
```

## Arm (human only)

```bash
RIG1_HEARTBEAT_ARM=1 bash deploy/rig1-heartbeat/bin/arm.sh
# park again
bash deploy/rig1-heartbeat/bin/disarm.sh
```

## Env notes

- launchd does **not** read `~/.zshlocal`. `GDDP_JULES_KEY_CMD` must be in the
  rendered plist (via `env/gddp.env` + `render_plist`) or exported for manual runs.
- Key cmd is executed with `shlex.split` (no shell). Expand `${USER}` at source
  time, not as a literal `$USER` string inside the plist.
