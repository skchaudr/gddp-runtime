# Configuration reference

Values come from `/Users/sab-mini/repos/gddp-runtime/README.md` and the mini/rig deployment env examples. Command variables should resolve secrets; they should not contain secret values.

| Variable | Purpose | Default or notes |
| --- | --- | --- |
| `GDDP_RUNTIME_ROOT` | Root for SQLite, events, jobs, and runtime-relative paths | Repo root locally; deploy tooling may fall back to `OPCLAW_ROOT` or historical `~/opclaw` |
| `OPCLAW_ROOT` | Legacy runtime-root compatibility fallback | Avoid in new host configuration |
| `GDDP_CONFIG_PATH` | `gddp-config` checkout used for graph reads | Sibling `~/repos/gddp-config` in mini kit; required in deployment |
| `GDDP_REPOS_ROOT` | Root under which project repositories resolve | `~/repos` |
| `GDDP_REPO_ROOT` | Compatibility/project repository root used by runtime resolution | Defaults to `GDDP_REPOS_ROOT` |
| `GDDP_PROJECT_ID` | Target project for single-project smoke/manual ticks | `gddp-runtime` in mini kit |
| `GDDP_PROJECT_REPO` | GitHub owner/repository for the target project | `skchaudr/gddp-runtime` |
| `GDDP_PYTHON` | Interpreter rendered into service definitions | `.venv/bin/python` when present, otherwise host Python |
| `GITHUB_TOKEN`, `GH_TOKEN` | GitHub API authentication for Jules-mediated dispatch | Required by relevant adapter |
| `GITHUB_WEBHOOK_SECRET` | Direct webhook HMAC secret override | Prefer command resolver in deployed service |
| `GDDP_WEBHOOK_SECRET_CMD` | Command that emits webhook secret | `pass show gddp/webhook-secret` |
| `GDDP_INTAKE_INSECURE` | Permit intake without HMAC secret | Only value `1`; localhost development only |
| `DEEPSEEK_API_KEY` | Interactive semantic evaluator credential | Optional direct override |
| `GDDP_DEEPSEEK_KEY_CMD` | Command that resolves DeepSeek credential | `pass show api/deepseek` |
| `JULES_API_KEY` | Interactive Jules credential | Optional direct override |
| `GDDP_JULES_KEY_CMD` | Command that resolves Jules credential | `pass show api/jules`; Rig 1 uses a mode-0600 file command |
| `GDDP_LOCAL_SUBPROCESS_ARGV` | JSON argv for generic direct executor | Must be an absolute, smoke-tested route |
| `GDDP_DROID_SUBPROCESS_ARGV` | JSON argv for Droid-specialized local executor | Optional; adapter has built-in Droid default |
| `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` | Durable direct-attempt spool | `$GDDP_RUNTIME_ROOT/jobs/local-subprocess-spool` |
| `GDDP_MISSION_SESSION_DIR` | Durable Factory mission session records and evidence | `db/mission-sessions` |
| `GDDP_FACTORY_MISSION_DIR` | Factory's mission state directory | `~/.factory/missions` |
| `GDDP_INTEGRITY_MODE` | Integrity-lane override | On by default; `off` is local debugging only |
| `GDDP_IDLE_SHUTDOWN_MINUTES` | Idle limit used by the optional VM idle-shutdown service | Falls back to the command's `--idle-minutes` setting |
| `MINI_HEARTBEAT_ARM` | Human activation guard for mini intake/heartbeat | Must be `1` for `arm.sh` |
| `RIG1_HEARTBEAT_ARM` | Human activation guard for heartbeat-only Rig 1 | Must be `1` for Rig 1 `arm.sh` |

After changing `/Users/sab-mini/repos/gddp-runtime/deploy/mini-heartbeat/env/gddp.env` on macOS, re-run `arm.sh` so values are rendered into the installed plist, then run `smoke.sh` to detect drift.
