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

**Not in git:** live `db/queue.db`, `env/gddp.env`, API key files under `~/.config/gddp/`.

## Dormancy contract

1. `install-dormant` may place files and register a plist that does **not** start.
2. `arm.sh` exits unless `RIG1_HEARTBEAT_ARM=1`.
3. No intake agent is installed. GitHub webhooks stay on sab-mini; this rig
   reconciles Jules sessions by polling the adapter.

## Secrets (0600 files — not keychain)

**Why:** the login keychain locks. Unattended launchd cannot assume an unlocked
session. Verified 2026-07-28: `security find-generic-password -w …` returns
rc=36 (`errSecInteractionNotAllowed`) and `JulesApiAdapter._load_api_key()`
returns `''`. An armed overnight heartbeat would dispatch/reconcile with no
credential. `pass` has the same unattended unlock problem.

**Layout:**

| File | Mode | Used by |
|---|---|---|
| `~/.config/gddp/` | `0700` | directory |
| `~/.config/gddp/jules-api-key` | `0600` | `GDDP_JULES_KEY_CMD=cat …` |
| `~/.config/gddp/deepseek-api-key` | `0600` | `GDDP_DEEPSEEK_KEY_CMD=cat …` |

`*_KEY_CMD` stays a command (never inline the key). launchd does **not** read
`~/.zshlocal`. Values are baked into the rendered plist via `render_plist`.
Commands run via `shlex.split` (no shell) — expand `$HOME` at source/render time.

### Seed once (Terminal.app — GUI can Allow keychain access)

```bash
mkdir -p ~/.config/gddp && chmod 700 ~/.config/gddp
security find-generic-password -w -s jules-api-key -a "$USER" > ~/.config/gddp/jules-api-key
chmod 600 ~/.config/gddp/jules-api-key
stat -f 'mode=%Lp size=%z' ~/.config/gddp/jules-api-key   # size > 0
```

DeepSeek the same way when you have a source (keychain item or one-time paste
into the file). Do not commit or log the file contents.

### Rotate

1. Rewrite the file (seed from keychain again, or paste a new key).
2. `chmod 600` the file.
3. Re-run `bash deploy/rig1-heartbeat/bin/install-dormant.sh` (or `arm.sh` if
   already armed) so the plist still points at the same path — no re-render
   needed unless the path or command changes.

## Bring-up

```bash
cd ~/repos/gddp-runtime
# seed keys first (section above)
bash deploy/rig1-heartbeat/bin/install-dormant.sh

# proof of rendered job (should show scripts.runtime.heartbeat.runner + cat …)
plutil -p ~/Library/LaunchAgents/com.gddp.rig1.heartbeat.plist

# manual one-shot (empty queue is a pass)
export GDDP_JULES_KEY_CMD="cat $HOME/.config/gddp/jules-api-key"
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
