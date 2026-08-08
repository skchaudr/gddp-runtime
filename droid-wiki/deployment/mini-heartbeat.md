# Mini-heartbeat operations

The kit at `/Users/sab-mini/repos/gddp-runtime/deploy/mini-heartbeat/` is the supported heartbeat entrypoint. It renders a checked-in, secret-free environment into host service definitions and keeps installation separate from activation.

## Dormant install, arm, smoke, and disarm

```bash
cd /Users/sab-mini/repos/gddp-runtime
bash deploy/mini-heartbeat/bin/install-dormant.sh
bash deploy/mini-heartbeat/bin/smoke.sh
MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh
bash deploy/mini-heartbeat/bin/smoke.sh
bash deploy/mini-heartbeat/bin/disarm.sh
```

`install-dormant.sh` creates runtime directories, renders service definitions, and registers them disabled. `arm.sh` refuses to activate unless `MINI_HEARTBEAT_ARM=1` is explicit. `smoke.sh` checks paths, graph presence, secret resolvers by length, GitHub and Pi availability, intake health and invalid-HMAC rejection when listening, launchd environment drift, and one dry heartbeat. `disarm.sh` stops and disables the mini services.

Do not call `python -m scripts.runtime.heartbeat.runner` directly on an armed plane. The kit sources `/Users/sab-mini/repos/gddp-runtime/deploy/mini-heartbeat/env/gddp.env`, which supplies executor argv and spool settings that a raw invocation can miss.

## Environment rendering

Copy `/Users/sab-mini/repos/gddp-runtime/deploy/mini-heartbeat/env/gddp.env.example` to the gitignored `env/gddp.env`, then set host-absolute paths and command-based secret resolvers. On macOS, `common.sh` renders the environment into installed plists. Editing `gddp.env` alone does not update a loaded LaunchAgent; re-run `arm.sh` and then `smoke.sh`. Smoke compares the environment that would be rendered with the installed plist and names stale keys.

Secrets are resolved at runtime with commands such as `pass show api/deepseek` and `pass show gddp/webhook-secret`. The env file contains commands and paths, not secret values.

## launchd and systemd

On `sab-mini`, the rendered launchd jobs are:

- `com.gddp.intake`: localhost intake on port 5050.
- `com.gddp.heartbeat`: `--all-active` heartbeat every 300 seconds.

Logs go to `~/Library/Logs/gddp-{intake,heartbeat}.log` and matching `.err.log` files.

Linux rigs install `gddp-heartbeat.service` and `gddp-heartbeat.timer` from `/Users/sab-mini/repos/gddp-runtime/deploy/mini-heartbeat/systemd/` into `~/.config/systemd/user/`. The timer uses `OnUnitActiveSec=300`. The service must retain `KillMode=process`: systemd's default `control-group` behavior kills the detached executor processes spawned by the oneshot heartbeat when the tick exits. This failure was observed on `khoj-38`.

```bash
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now gddp-heartbeat.timer
```

## Cutover and state

`/Users/sab-mini/repos/gddp-runtime/deploy/mini-heartbeat/CUTOVER.md` is the human-operated pi-big-to-mini sequence. Its important order is:

1. Update and verify both repositories.
2. Install dormant and smoke the target.
3. Establish a durable public URL and prove invalid HMAC returns 401.
4. Disarm the source and wait for heartbeat and executor writers to drain.
5. Optionally capture a consistent SQLite online backup plus `jobs/` and `events/`.
6. Arm and smoke the target.
7. Repoint webhooks, prove one real delivery end to end, and verify no source-plane duplicate.

Do not copy `queue.db` by itself while writers are active. SQLite WAL may contain committed state absent from the main file. Use `.backup`, and quiesce writers when queue, jobs, and events must agree.

## Fresh Linux hosts

`/Users/sab-mini/repos/gddp-runtime/deploy/mini-heartbeat/FRESH-HOST-STANDUP.md` records the sequence actually executed on `khoj-38` on 2026-08-04/05. It uses checkouts directly under `$HOME`, a config virtualenv, an absolute `gddp.env`, systemd user units, and a smoke tick before first dispatch. Verify the local Droid version and any model proxy before arming. Do not use the archived Big Pi setup or service files: they hard-code a retired user and `$HOME/opclaw` topology.

See [Monitoring](../how-to-monitor/index.md) for live checks.
