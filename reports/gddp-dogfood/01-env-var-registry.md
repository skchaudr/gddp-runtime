# GDDP_* environment-variable registry

Node: `node-01-env-var-registry`  
Job: `job_20260811T0430093101088246d28d` (attempt 1)  
Base: `450eca1cffe1113b3af15db0b2ab65b7c0eb5b61`  
Inventory date: 2026-08-11  
Scope: live reads in this worktree (active Python + mini-heartbeat shell). Archive-only names are listed separately.

## Method

Read-only inventory. Commands run in this worktree:

```text
rg -n 'os\.environ|getenv|environ\.get' -g '*.py' | rg -i 'GDDP_'
rg -n 'GDDP_[A-Z0-9_]+' -g '*.py' -g '*.sh' -g '*.env*'
```

Plus a small Python walk that matched `os.environ.get/[]`, `os.getenv`, `_FOO_ENV = "GDDP_…"`, and shell `${GDDP_…}` expansions, then each cited line was re-checked with `sed -n`.

### Sample raw matches (quoted)

```text
scripts/init_db.py:17:RUNTIME_ROOT  = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
scripts/runtime/heartbeat/dispatcher.py:63:    override = os.environ.get("GDDP_EXECUTOR_OVERRIDE", "")
scripts/adapters/local_subprocess_adapter.py:23:_ARGV_ENV = "GDDP_LOCAL_SUBPROCESS_ARGV"
scripts/adapters/local_subprocess_adapter.py:282:        raw = os.environ.get(env_var)
scripts/intake_server.py:41:    secret_cmd = os.environ.get("GDDP_WEBHOOK_SECRET_CMD", "pass show gddp/webhook-secret")
scripts/runtime/repo_resolver.py:57:        for env_name in ("GDDP_REPO_ROOT", "GDDP_REPOS_ROOT"):
deploy/mini-heartbeat/bin/common.sh:17:GDDP_RUNTIME_ROOT="${GDDP_RUNTIME_ROOT:-$HOME/repos/gddp-runtime}"
```

**Read site rule:** primary citation is the first active `os.environ.get` / `os.getenv` / shell expansion that consumes the name. Where code binds a constant (e.g. `_ARGV_ENV = "GDDP_…"`) and later calls `os.environ.get(that_constant)`, the constant definition is cited when that is the unambiguous binding, and the get-site is noted in Purpose.

## Registry (active reads)

| Variable | Read site (file:line) | Default / fallback (as coded) | Purpose (one line) |
|---|---|---|---|
| `GDDP_RUNTIME_ROOT` | `scripts/init_db.py:17` | `OPCLAW_ROOT`, else repo-relative default | Runtime state root (`db/`, `jobs/`, `events/`). |
| `GDDP_CONFIG_PATH` | `scripts/jobs_status.py:327` | `{RUNTIME_ROOT.parent}/gddp-config` | Local path to gddp-config / graphs. |
| `GDDP_CONFIG_REPO` | `scripts/runtime/graph_updater.py:152` | `skchaudr/gddp-config` | GitHub slug for config repo operations. |
| `GDDP_REPOS_ROOT` | `scripts/runtime/verification/bridge.py:45` | `_RUNTIME_ROOT.parent` | Parent directory of checked-out project repos. |
| `GDDP_REPO_ROOT` | `scripts/runtime/repo_resolver.py:57` | none (optional candidate root) | Alternate single-repo root; tried with `GDDP_REPOS_ROOT` when resolving basenames. |
| `GDDP_WEBHOOK_SECRET_CMD` | `scripts/intake_server.py:41` | `pass show gddp/webhook-secret` | Shell command that prints the GitHub webhook secret. |
| `GDDP_INTAKE_INSECURE` | `scripts/intake_server.py:57` | empty (secure) | When `1`, disables webhook signature verification (local dev). |
| `GDDP_EXECUTOR_OVERRIDE` | `scripts/runtime/heartbeat/dispatcher.py:63` | empty | Force executor id for dispatch without graph edits. |
| `GDDP_LOCAL_SUBPROCESS_ARGV` | `scripts/adapters/local_subprocess_adapter.py:23` | required when that executor is used (`os.environ.get` at `:282` via `_ARGV_ENV`) | JSON argv for local subprocess executor. |
| `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` | `scripts/adapters/local_subprocess_adapter.py:24` | required (`os.environ.get(_SPOOL_ENV)` at `:361`) | Spool root for local/droid attempt dirs. |
| `GDDP_LOCAL_SUBPROCESS_CWD` | `scripts/adapters/local_subprocess_adapter.py:25` | none (`os.environ.get(_CWD_ENV)` at `:48`) | Optional cwd override for local subprocess. |
| `GDDP_DROID_SUBPROCESS_ARGV` | `scripts/adapters/local_subprocess_adapter.py:301` | built-in droid default argv (`get` via `_DROID_ARGV_ENV` ~`:355`) | JSON argv for droid/factory local transport (model/autonomy host config). |
| `GDDP_WORKTREE_MAP_PATH` | `scripts/local_agent_executor.py:38` | `~/.local/share/droid-observability/gddp-worktree-map.ndjson` (via `_WORKTREE_MAP_ENV` at `:20`) | NDJSON map of agent worktrees. |
| `GDDP_JULES_KEY_CMD` | `scripts/adapters/jules_api_adapter.py:301` | empty string | Command that prints the Jules API key. |
| `GDDP_JULES_STARTING_BRANCH` | `scripts/adapters/jules_api_adapter.py:44` | none (other sources first) | Starting branch hint for Jules sessions. |
| `GDDP_DEEPSEEK_KEY_CMD` | `scripts/runtime/verification/bridge.py:303` | `pass show api/deepseek` | Command that prints the DeepSeek API key for semantic verify. |
| `GDDP_MISSION_SESSION_DIR` | `scripts/adapters/mission_adapter.py:60` | none | Mission adapter session directory override. |
| `GDDP_FACTORY_MISSION_DIR` | `scripts/adapters/mission_adapter.py:65` | none | Factory mission directory override. |
| `GDDP_MISSION_MODEL` | `scripts/adapters/mission_adapter.py:70` | none | Orchestrator model for factory mission. |
| `GDDP_MISSION_REASONING_EFFORT` | `scripts/adapters/mission_adapter.py:72` | none | Orchestrator reasoning effort. |
| `GDDP_MISSION_WORKER_MODEL` | `scripts/adapters/mission_adapter.py:75` | none | Worker model for factory mission. |
| `GDDP_MISSION_WORKER_REASONING_EFFORT` | `scripts/adapters/mission_adapter.py:78` | none | Worker reasoning effort. |
| `GDDP_MISSION_VALIDATOR_MODEL` | `scripts/adapters/mission_adapter.py:81` | none | Validator model for factory mission. |
| `GDDP_MISSION_VALIDATOR_REASONING_EFFORT` | `scripts/adapters/mission_adapter.py:85` | none | Validator reasoning effort. |
| `GDDP_RECEIPTS_PATH` | `scripts/gddp_node_receipt.py:72` | required when running `gddp receipt` (`RECEIPTS_PATH_ENV` at `:16`) | JSONL ledger path for node receipts. |
| `GDDP_RECEIPTS_DIR` | `scripts/runtime/verification/receipt_sink.py:21` | `~/.gddp/receipts` | Directory for verification verdict receipts. |
| `GDDP_VERIFY_TIMEOUT_SECONDS` | `scripts/runtime/verification/bridge.py:34` | `0` | Overall verification timeout budget. |
| `GDDP_VERIFY_SEMANTIC_ARGS` | `scripts/runtime/verification/bridge.py:261` | `DEFAULT_SEMANTIC_ARGS` | Extra CLI args passed into semantic verification. |
| `GDDP_INTEGRITY_MODE` | `scripts/runtime/verification/bridge.py:273` | `on` | When `off`, passes `--integrity off` to the verifier. |
| `GDDP_SEMANTIC_PROVIDER` | `scripts/runtime/verification/cli.py:111` | `auto` | Semantic provider selection for verifier CLI. |
| `GDDP_SEMANTIC_HARNESS` | `scripts/runtime/verification/cli.py:150` | `auto` | Semantic harness selection. |
| `GDDP_SEMANTIC_THINKING` | `scripts/runtime/verification/cli.py:160` | `medium` | Thinking level for semantic pass. |
| `GDDP_SEMANTIC_PI_MODEL` | `scripts/runtime/verification/cli.py:165` | empty | Pi model override for semantic harness. |
| `GDDP_COMMAND_PROOF_TIMEOUT` | `scripts/runtime/verification/deterministic/probes.py:231` | `300` | Timeout (s) for command-proof deterministic probes. |
| `GDDP_PI_TIMEOUT_SECONDS` | `scripts/runtime/verification/semantic/timeouts.py:8` | `1200` | Pi semantic harness wall timeout. |
| `GDDP_VERIFY_TIMEOUT_OVERHEAD_SECONDS` | `scripts/runtime/verification/semantic/timeouts.py:10` | `120` | Overhead added around Pi timeout. |
| `GDDP_PI_RPC_CWD` | `scripts/adapters/pi_rpc_adapter.py:76` | none | Working directory for pi_rpc executor. |
| `GDDP_PI_RPC_MODEL` | `scripts/adapters/pi_rpc_adapter.py:78` | adapter `_DEFAULT_MODEL` (`_MODEL_ENV` at `:39`) | Model for pi_rpc turns. |
| `GDDP_PI_RPC_BINARY` | `scripts/adapters/pi_rpc_adapter.py:79` | `pi` (`_BINARY_ENV` at `:40`) | Pi binary path/name. |
| `GDDP_PI_RPC_TOOLS` | `scripts/adapters/pi_rpc_adapter.py:80` | adapter default tools (`_TOOLS_ENV` at `:41`) | Tool allow-list string for pi_rpc. |
| `GDDP_PI_RPC_TURN_TIMEOUT_S` | `scripts/adapters/pi_rpc_adapter.py:85` | adapter default (`_TIMEOUT_ENV` at `:42`) | Per-turn timeout seconds. |
| `GDDP_PI_RPC_SPOOL_DIR` | `scripts/adapters/pi_rpc_adapter.py:612` | falls back to `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` (`_SPOOL_ENV` at `:38`) | Spool root for pi_rpc attempts. |
| `GDDP_IDLE_SHUTDOWN_MINUTES` | `deploy/mini-heartbeat/bin/idle_shutdown.py:76` | CLI `--idle-minutes` | Idle minutes before host shutdown helper acts. |
| `GDDP_PYTHON` | `deploy/mini-heartbeat/bin/common.sh:22` | `$GDDP_RUNTIME_ROOT/.venv/bin/python` or `/usr/bin/python3` | Python interpreter for heartbeat kit. |
| `GDDP_PROJECT_ID` | `deploy/mini-heartbeat/bin/common.sh:20` | `gddp-runtime` | Project id for graph paths / smoke checks. |
| `GDDP_PROJECT_REPO` | `deploy/mini-heartbeat/bin/common.sh:21` | `skchaudr/gddp-runtime` | GitHub repo slug for the project under control. |

**Distinct active variables in table: 46.**

Also expanded with default at shell layer (same names already cited above as Python reads where applicable):

| Variable | Shell read site | Notes |
|---|---|---|
| `GDDP_RUNTIME_ROOT` | `deploy/mini-heartbeat/bin/common.sh:17` | Default `$HOME/repos/gddp-runtime` before Python sees it. |
| `GDDP_CONFIG_PATH` | `deploy/mini-heartbeat/bin/common.sh:18` | Default `$HOME/repos/gddp-config`. |
| `GDDP_REPOS_ROOT` | `deploy/mini-heartbeat/bin/common.sh:19` | Default `$HOME/repos`. |
| `GDDP_LOCAL_SUBPROCESS_ARGV` | `deploy/mini-heartbeat/bin/common.sh:66` | Rendered into launchd plist env. |
| `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` | `deploy/mini-heartbeat/bin/common.sh:67` | Default `$GDDP_RUNTIME_ROOT/jobs/local-subprocess-spool`. |
| `GDDP_DROID_SUBPROCESS_ARGV` | `deploy/mini-heartbeat/bin/common.sh:64` | Optional; empty default. |
| `GDDP_WEBHOOK_SECRET_CMD` | `deploy/mini-heartbeat/bin/common.sh:68` | Default `pass show gddp/webhook-secret`. |
| `GDDP_DEEPSEEK_KEY_CMD` | `deploy/mini-heartbeat/bin/common.sh:63` | Default `pass show api/deepseek`. |
| `GDDP_JULES_KEY_CMD` | `deploy/mini-heartbeat/bin/common.sh:65` | Default `pass show api/jules`. |
| `GDDP_PROJECT_ID` / `GDDP_PROJECT_REPO` | `deploy/mini-heartbeat/bin/baseline.sh:134` | Consumed when invoking runner-adjacent tooling. |

## Archive-only (not primary ops surface)

Present under `scripts/_archive/` only; not counted as active control-plane config:

| Variable | Read site | Purpose |
|---|---|---|
| `GDDP_PUSH_AUDIT_PATH` | `scripts/_archive/mission_push_guard.py:17` | Push-guard audit log path. |
| `GDDP_ENGAGEMENT_BRANCH` | `scripts/_archive/mission_push_guard.py:18` | Engagement branch name for push policy. |
| `GDDP_REAL_GIT` | `scripts/_archive/mission_push_guard.py:19` | Path to real `git` behind PATH shim. |
| `GDDP_PUSH_WRAPPER_ACTIVE` | `scripts/_archive/mission_push_guard.py:20` | Marker that the wrapper is on PATH. |

## Notes for operators

- **Legacy alias:** many Python entrypoints still accept `OPCLAW_ROOT` when `GDDP_RUNTIME_ROOT` is unset (`scripts/init_db.py:17` pattern).
- **Spool coupling:** `pi_rpc` prefers `GDDP_PI_RPC_SPOOL_DIR`, then `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` (`scripts/adapters/pi_rpc_adapter.py:612-613`).
- **Secret pattern:** keys and webhook secret are almost always *commands* (`*_CMD`), not raw secret values in the environment.
- **Heartbeat kit:** agents must use `deploy/mini-heartbeat/bin/*` so `GDDP_LOCAL_SUBPROCESS_ARGV` / spool are sourced; raw `python -m scripts.runtime.heartbeat.runner` skips that env (see root `AGENTS.md`).
- This registry is evidence, not an allow-list schema. Tests also set many of these via `monkeypatch.setenv`; those writes were not inventoried as read sites.

## Validation

Host `python3 -m pytest -q` first hit `ModuleNotFoundError: No module named 'flask'` (PEP 668 externally managed env; no repo `.venv`). Re-ran with an ephemeral venv:

```text
python3 -m venv /tmp/gddp-pytest-venv
/tmp/gddp-pytest-venv/bin/pip install -q -r requirements.txt pytest
/tmp/gddp-pytest-venv/bin/python -m pytest -q
```

Tail line:

```text
1 failed, 625 passed in 35.06s
```

Sole failure (pre-existing, unrelated to this report-only change):
`deploy/rig1-heartbeat/test_rig1_render_plist.py::test_render_heartbeat_invokes_real_runner_module`
— expects `--project gddp-runtime`, observed `--project pi-harness-execution`.
