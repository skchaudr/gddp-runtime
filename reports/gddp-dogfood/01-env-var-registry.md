# GDDP_* environment-variable registry

- **Node:** `node-01-env-var-registry`
- **Base commit:** `450eca1cffe1113b3af15db0b2ab65b7c0eb5b61`
- **Generated:** 2026-08-11T04:32:34Z
- **Method:** live `rg`/`python` scan of the worktree for `os.environ`/`os.getenv`/`env.GDDP_*`/`${GDDP_*}` reads; one primary citation per variable (production preferred over tests).
- **Scope:** production runtime, adapters, verify harness, mini-heartbeat deploy kit. Archive-only vars noted separately.

## Registry

| Variable | Read at | Purpose | Default / unset behavior |
|---|---|---|---|
| `GDDP_RUNTIME_ROOT` | `scripts/runtime/results_store.py:16` | Runtime state root (db/events/jobs); OPCLAW_ROOT legacy fallback | repo root locally |
| `GDDP_CONFIG_PATH` | `scripts/runtime/graph_updater.py:143` | Filesystem path to gddp-config graphs | required if no CLI --config-path / sibling |
| `GDDP_CONFIG_REPO` | `scripts/runtime/graph_updater.py:152` | GitHub slug for config repo writes | skchaudr/gddp-config |
| `GDDP_REPO_ROOT` | `scripts/runtime/repo_resolver.py:57` | Primary checkout root for graph repo basenames | unset |
| `GDDP_REPOS_ROOT` | `scripts/runtime/verification/bridge.py:45` | Repos parent used when resolving project checkouts | parent of runtime root |
| `GDDP_EXECUTOR_OVERRIDE` | `scripts/runtime/heartbeat/dispatcher.py:63` | Force executor name regardless of graph mode | empty (use graph) |
| `GDDP_WEBHOOK_SECRET_CMD` | `scripts/intake_server.py:41` | Shell command that prints GitHub webhook secret | pass show gddp/webhook-secret |
| `GDDP_INTAKE_INSECURE` | `scripts/intake_server.py:57` | Disable webhook signature verification when set to 1 | off |
| `GDDP_LOCAL_SUBPROCESS_ARGV` | `scripts/adapters/local_subprocess_adapter.py:282` | JSON argv array for local_subprocess executor | required for local_subprocess |
| `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` | `scripts/adapters/local_subprocess_adapter.py:361` | Spool root for local subprocess handoffs | required |
| `GDDP_LOCAL_SUBPROCESS_CWD` | `scripts/adapters/local_subprocess_adapter.py:48` | Working directory override for local subprocess | adapter default |
| `GDDP_DROID_SUBPROCESS_ARGV` | `scripts/adapters/local_subprocess_adapter.py:301` | JSON argv override for droid executor | built-in droid exec default |
| `GDDP_JULES_KEY_CMD` | `scripts/adapters/jules_api_adapter.py:301` | Command that prints Jules API key | empty |
| `GDDP_JULES_STARTING_BRANCH` | `scripts/adapters/jules_api_adapter.py:44` | Starting branch for Jules sessions | adapter/code default |
| `GDDP_MISSION_SESSION_DIR` | `scripts/adapters/mission_adapter.py:60` | Durable factory_mission session records root | db/mission-sessions (code default path) |
| `GDDP_FACTORY_MISSION_DIR` | `scripts/adapters/mission_adapter.py:65` | Factory missions state directory | ~/.factory/missions |
| `GDDP_MISSION_MODEL` | `scripts/adapters/mission_adapter.py:70` | Orchestrator model for mission mode | unset |
| `GDDP_MISSION_REASONING_EFFORT` | `scripts/adapters/mission_adapter.py:71` | Orchestrator reasoning effort | unset |
| `GDDP_MISSION_WORKER_MODEL` | `scripts/adapters/mission_adapter.py:74` | Worker model for mission mode | unset |
| `GDDP_MISSION_WORKER_REASONING_EFFORT` | `scripts/adapters/mission_adapter.py:77` | Worker reasoning effort | unset |
| `GDDP_MISSION_VALIDATOR_MODEL` | `scripts/adapters/mission_adapter.py:80` | Validator model for mission mode | unset |
| `GDDP_MISSION_VALIDATOR_REASONING_EFFORT` | `scripts/adapters/mission_adapter.py:85` | Validator reasoning effort | unset |
| `GDDP_RECEIPTS_PATH` | `scripts/gddp_node_receipt.py:72` | JSONL ledger path for node receipts | required when emitting receipts |
| `GDDP_RECEIPTS_DIR` | `scripts/runtime/verification/receipt_sink.py:21` | Directory for verification receipt files | ~/.gddp/receipts |
| `GDDP_DEEPSEEK_KEY_CMD` | `scripts/runtime/verification/bridge.py:303` | Command that prints DeepSeek API key for semantic verify | pass show api/deepseek |
| `GDDP_VERIFY_TIMEOUT_SECONDS` | `scripts/runtime/verification/bridge.py:34` | Hard timeout budget for verify bridge (0 = derive) | 0 |
| `GDDP_VERIFY_SEMANTIC_ARGS` | `scripts/runtime/verification/bridge.py:261` | Extra CLI args string for semantic verify subprocess | DEFAULT_SEMANTIC_ARGS |
| `GDDP_INTEGRITY_MODE` | `scripts/runtime/verification/bridge.py:273` | Toggle integrity lane on/off for verify bridge | on |
| `GDDP_SEMANTIC_PROVIDER` | `scripts/runtime/verification/cli.py:111` | Semantic provider selection for verify CLI | auto |
| `GDDP_SEMANTIC_HARNESS` | `scripts/runtime/verification/cli.py:150` | Semantic harness selection (pi/etc.) | auto |
| `GDDP_SEMANTIC_THINKING` | `scripts/runtime/verification/cli.py:160` | Thinking level for semantic harness | medium |
| `GDDP_SEMANTIC_PI_MODEL` | `scripts/runtime/verification/cli.py:165` | Model id for pi semantic harness | empty |
| `GDDP_PI_TIMEOUT_SECONDS` | `scripts/runtime/verification/semantic/timeouts.py:8` | Pi semantic run timeout seconds | 1200 |
| `GDDP_VERIFY_TIMEOUT_OVERHEAD_SECONDS` | `scripts/runtime/verification/semantic/timeouts.py:10` | Overhead added atop pi timeout for outer budget | 120 |
| `GDDP_COMMAND_PROOF_TIMEOUT` | `scripts/runtime/verification/deterministic/probes.py:231` | Timeout for deterministic command-proof probes | 300 |
| `GDDP_VERDICT_OUT` | `scripts/runtime/verification/semantic/pi_harness/gddp_verifier.ts:65` | Path where pi submit_verdict writes SemanticOutput JSON | set by pi_runner per run |
| `GDDP_TOOL_TRACE` | `scripts/runtime/verification/semantic/pi_harness/gddp_verifier_guard.ts:49` | JSONL path for pi tool-call trace during verify | set by pi_runner per run |
| `GDDP_INTEGRITY_OUT` | `scripts/runtime/verification/semantic/pi_harness/gddp_integrity.ts:77` | Path where integrity submit writes verdict JSON | set by integrity runner |
| `GDDP_PI_RPC_CWD` | `scripts/adapters/pi_rpc_adapter.py:76` | cwd for pi RPC adapter sessions | unset |
| `GDDP_PI_RPC_MODEL` | `scripts/adapters/pi_rpc_adapter.py:78` | Model for pi RPC executor | adapter default |
| `GDDP_PI_RPC_BINARY` | `scripts/adapters/pi_rpc_adapter.py:79` | pi binary path/name | pi |
| `GDDP_PI_RPC_TOOLS` | `scripts/adapters/pi_rpc_adapter.py:80` | Tools flag/value for pi RPC | adapter default |
| `GDDP_PI_RPC_TURN_TIMEOUT_S` | `scripts/adapters/pi_rpc_adapter.py:85` | Per-turn timeout seconds for pi RPC | adapter default |
| `GDDP_PI_RPC_SPOOL_DIR` | `scripts/adapters/pi_rpc_adapter.py:612` | Spool directory for pi RPC handoffs | falls back to GDDP_LOCAL_SUBPROCESS_SPOOL_DIR |
| `GDDP_WORKTREE_MAP_PATH` | `scripts/local_agent_executor.py:38` | Path to worktree map file for local agent executor | code default map path |
| `GDDP_IDLE_SHUTDOWN_MINUTES` | `deploy/mini-heartbeat/bin/idle_shutdown.py:76` | Idle minutes before mini-heartbeat idle shutdown | CLI --idle-minutes |
| `GDDP_PROJECT_ID` | `deploy/mini-heartbeat/bin/common.sh:20` | Active project id for heartbeat kit | gddp-runtime |
| `GDDP_PROJECT_REPO` | `deploy/mini-heartbeat/bin/common.sh:21` | owner/repo for active project | skchaudr/gddp-runtime |
| `GDDP_PYTHON` | `deploy/mini-heartbeat/bin/common.sh:22` | Python interpreter for mini-heartbeat | .venv/bin/python or /usr/bin/python3 |

**Distinct variables in table:** 49

## Quoted primary matches

Exact source lines at the cited locations (verified by reading the file):

- `GDDP_RUNTIME_ROOT` — `scripts/runtime/results_store.py:16`
  ```
  RUNTIME_ROOT = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
  ```
- `GDDP_CONFIG_PATH` — `scripts/runtime/graph_updater.py:143`
  ```
      env_path = os.environ.get("GDDP_CONFIG_PATH")
  ```
- `GDDP_CONFIG_REPO` — `scripts/runtime/graph_updater.py:152`
  ```
      return os.environ.get("GDDP_CONFIG_REPO", "skchaudr/gddp-config")
  ```
- `GDDP_REPO_ROOT` — `scripts/runtime/repo_resolver.py:57`
  ```
          for env_name in ("GDDP_REPO_ROOT", "GDDP_REPOS_ROOT"):
  ```
- `GDDP_REPOS_ROOT` — `scripts/runtime/verification/bridge.py:45`
  ```
      return Path(os.environ.get("GDDP_REPOS_ROOT", str(_RUNTIME_ROOT.parent)))
  ```
- `GDDP_EXECUTOR_OVERRIDE` — `scripts/runtime/heartbeat/dispatcher.py:63`
  ```
      override = os.environ.get("GDDP_EXECUTOR_OVERRIDE", "")
  ```
- `GDDP_WEBHOOK_SECRET_CMD` — `scripts/intake_server.py:41`
  ```
      secret_cmd = os.environ.get("GDDP_WEBHOOK_SECRET_CMD", "pass show gddp/webhook-secret")
  ```
- `GDDP_INTAKE_INSECURE` — `scripts/intake_server.py:57`
  ```
  _INTAKE_INSECURE = os.environ.get("GDDP_INTAKE_INSECURE", "").strip() == "1"
  ```
- `GDDP_LOCAL_SUBPROCESS_ARGV` — `scripts/adapters/local_subprocess_adapter.py:282`
  ```
          raw = os.environ.get(env_var)
  ```
- `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` — `scripts/adapters/local_subprocess_adapter.py:361`
  ```
      configured = spool_root if spool_root is not None else os.environ.get(_SPOOL_ENV)
  ```
- `GDDP_LOCAL_SUBPROCESS_CWD` — `scripts/adapters/local_subprocess_adapter.py:48`
  ```
          configured_cwd = cwd if cwd is not None else os.environ.get(_CWD_ENV)
  ```
- `GDDP_DROID_SUBPROCESS_ARGV` — `scripts/adapters/local_subprocess_adapter.py:301`
  ```
  _DROID_ARGV_ENV = "GDDP_DROID_SUBPROCESS_ARGV"
  ```
- `GDDP_JULES_KEY_CMD` — `scripts/adapters/jules_api_adapter.py:301`
  ```
          command = os.environ.get("GDDP_JULES_KEY_CMD", "").strip()
  ```
- `GDDP_JULES_STARTING_BRANCH` — `scripts/adapters/jules_api_adapter.py:44`
  ```
              or os.environ.get("GDDP_JULES_STARTING_BRANCH")
  ```
- `GDDP_MISSION_SESSION_DIR` — `scripts/adapters/mission_adapter.py:60`
  ```
              or os.environ.get("GDDP_MISSION_SESSION_DIR")
  ```
- `GDDP_FACTORY_MISSION_DIR` — `scripts/adapters/mission_adapter.py:65`
  ```
              or os.environ.get("GDDP_FACTORY_MISSION_DIR")
  ```
- `GDDP_MISSION_MODEL` — `scripts/adapters/mission_adapter.py:70`
  ```
          self.model = model or os.environ.get("GDDP_MISSION_MODEL")
  ```
- `GDDP_MISSION_REASONING_EFFORT` — `scripts/adapters/mission_adapter.py:71`
  ```
          self.reasoning_effort = reasoning_effort or os.environ.get(
  ```
- `GDDP_MISSION_WORKER_MODEL` — `scripts/adapters/mission_adapter.py:74`
  ```
          self.worker_model = worker_model or os.environ.get(
  ```
- `GDDP_MISSION_WORKER_REASONING_EFFORT` — `scripts/adapters/mission_adapter.py:77`
  ```
          self.worker_reasoning_effort = worker_reasoning_effort or os.environ.get(
  ```
- `GDDP_MISSION_VALIDATOR_MODEL` — `scripts/adapters/mission_adapter.py:80`
  ```
          self.validator_model = validator_model or os.environ.get(
  ```
- `GDDP_MISSION_VALIDATOR_REASONING_EFFORT` — `scripts/adapters/mission_adapter.py:85`
  ```
              or os.environ.get("GDDP_MISSION_VALIDATOR_REASONING_EFFORT")
  ```
- `GDDP_RECEIPTS_PATH` — `scripts/gddp_node_receipt.py:72`
  ```
      configured_path = os.environ.get(RECEIPTS_PATH_ENV)
  ```
- `GDDP_RECEIPTS_DIR` — `scripts/runtime/verification/receipt_sink.py:21`
  ```
      root = base or Path(os.environ.get("GDDP_RECEIPTS_DIR", Path.home() / ".gddp" / "receipts"))
  ```
- `GDDP_DEEPSEEK_KEY_CMD` — `scripts/runtime/verification/bridge.py:303`
  ```
          key_cmd = os.environ.get("GDDP_DEEPSEEK_KEY_CMD", "pass show api/deepseek")
  ```
- `GDDP_VERIFY_TIMEOUT_SECONDS` — `scripts/runtime/verification/bridge.py:34`
  ```
      int(os.environ.get("GDDP_VERIFY_TIMEOUT_SECONDS", "0"))
  ```
- `GDDP_VERIFY_SEMANTIC_ARGS` — `scripts/runtime/verification/bridge.py:261`
  ```
          os.environ.get("GDDP_VERIFY_SEMANTIC_ARGS", DEFAULT_SEMANTIC_ARGS)
  ```
- `GDDP_INTEGRITY_MODE` — `scripts/runtime/verification/bridge.py:273`
  ```
          "--integrity", "off" if os.environ.get("GDDP_INTEGRITY_MODE", "on").lower() == "off" else "on",
  ```
- `GDDP_SEMANTIC_PROVIDER` — `scripts/runtime/verification/cli.py:111`
  ```
          default=os.environ.get("GDDP_SEMANTIC_PROVIDER", "auto"),
  ```
- `GDDP_SEMANTIC_HARNESS` — `scripts/runtime/verification/cli.py:150`
  ```
          default=os.environ.get("GDDP_SEMANTIC_HARNESS", "auto"),
  ```
- `GDDP_SEMANTIC_THINKING` — `scripts/runtime/verification/cli.py:160`
  ```
          default=os.environ.get("GDDP_SEMANTIC_THINKING", "medium"),
  ```
- `GDDP_SEMANTIC_PI_MODEL` — `scripts/runtime/verification/cli.py:165`
  ```
          default=os.environ.get("GDDP_SEMANTIC_PI_MODEL", ""),
  ```
- `GDDP_PI_TIMEOUT_SECONDS` — `scripts/runtime/verification/semantic/timeouts.py:8`
  ```
  PI_TIMEOUT_SECONDS = int(os.environ.get("GDDP_PI_TIMEOUT_SECONDS", "1200"))
  ```
- `GDDP_VERIFY_TIMEOUT_OVERHEAD_SECONDS` — `scripts/runtime/verification/semantic/timeouts.py:10`
  ```
      os.environ.get("GDDP_VERIFY_TIMEOUT_OVERHEAD_SECONDS", "120")
  ```
- `GDDP_COMMAND_PROOF_TIMEOUT` — `scripts/runtime/verification/deterministic/probes.py:231`
  ```
          timeout = int(os.environ.get("GDDP_COMMAND_PROOF_TIMEOUT", "300"))
  ```
- `GDDP_VERDICT_OUT` — `scripts/runtime/verification/semantic/pi_harness/gddp_verifier.ts:65`
  ```
        const outPath = env.GDDP_VERDICT_OUT;
  ```
- `GDDP_TOOL_TRACE` — `scripts/runtime/verification/semantic/pi_harness/gddp_verifier_guard.ts:49`
  ```
    const tracePath = env.GDDP_TOOL_TRACE;
  ```
- `GDDP_INTEGRITY_OUT` — `scripts/runtime/verification/semantic/pi_harness/gddp_integrity.ts:77`
  ```
        const outPath = env.GDDP_INTEGRITY_OUT;
  ```
- `GDDP_PI_RPC_CWD` — `scripts/adapters/pi_rpc_adapter.py:76`
  ```
          configured_cwd = cwd if cwd is not None else os.environ.get("GDDP_PI_RPC_CWD")
  ```
- `GDDP_PI_RPC_MODEL` — `scripts/adapters/pi_rpc_adapter.py:78`
  ```
          self.model = model or os.environ.get(_MODEL_ENV) or _DEFAULT_MODEL
  ```
- `GDDP_PI_RPC_BINARY` — `scripts/adapters/pi_rpc_adapter.py:79`
  ```
          self.pi_binary = pi_binary or os.environ.get(_BINARY_ENV) or "pi"
  ```
- `GDDP_PI_RPC_TOOLS` — `scripts/adapters/pi_rpc_adapter.py:80`
  ```
          self.tools = tools or os.environ.get(_TOOLS_ENV) or _DEFAULT_TOOLS
  ```
- `GDDP_PI_RPC_TURN_TIMEOUT_S` — `scripts/adapters/pi_rpc_adapter.py:85`
  ```
                  os.environ.get(_TIMEOUT_ENV, str(_DEFAULT_TIMEOUT_S))
  ```
- `GDDP_PI_RPC_SPOOL_DIR` — `scripts/adapters/pi_rpc_adapter.py:612`
  ```
          else os.environ.get(_SPOOL_ENV)
  ```
- `GDDP_WORKTREE_MAP_PATH` — `scripts/local_agent_executor.py:38`
  ```
          path = Path(os.environ.get(_WORKTREE_MAP_ENV) or _DEFAULT_WORKTREE_MAP)
  ```
- `GDDP_IDLE_SHUTDOWN_MINUTES` — `deploy/mini-heartbeat/bin/idle_shutdown.py:76`
  ```
      idle_limit = int(os.environ.get("GDDP_IDLE_SHUTDOWN_MINUTES", args.idle_minutes))
  ```
- `GDDP_PROJECT_ID` — `deploy/mini-heartbeat/bin/common.sh:20`
  ```
  GDDP_PROJECT_ID="${GDDP_PROJECT_ID:-gddp-runtime}"
  ```
- `GDDP_PROJECT_REPO` — `deploy/mini-heartbeat/bin/common.sh:21`
  ```
  GDDP_PROJECT_REPO="${GDDP_PROJECT_REPO:-skchaudr/gddp-runtime}"
  ```
- `GDDP_PYTHON` — `deploy/mini-heartbeat/bin/common.sh:22`
  ```
  if [[ -z "${GDDP_PYTHON:-}" ]]; then
  ```

## Multi-line reads (mission adapter)

These four variables split the env name onto the line after `os.environ.get(`:

  71|         self.reasoning_effort = reasoning_effort or os.environ.get(
  72|             "GDDP_MISSION_REASONING_EFFORT"
  73|         )
  74|         self.worker_model = worker_model or os.environ.get(
  75|             "GDDP_MISSION_WORKER_MODEL"
  76|         )
  77|         self.worker_reasoning_effort = worker_reasoning_effort or os.environ.get(
  78|             "GDDP_MISSION_WORKER_REASONING_EFFORT"
  79|         )
  80|         self.validator_model = validator_model or os.environ.get(
  81|             "GDDP_MISSION_VALIDATOR_MODEL"
  82|         )
  83|         self.validator_reasoning_effort = (
  84|             validator_reasoning_effort
  85|             or os.environ.get("GDDP_MISSION_VALIDATOR_REASONING_EFFORT")

## Constant-indirection reads

Some modules bind the env name to a constant, then `os.environ.get(CONST)`:

| Variable | Constant binding | Read site |
|---|---|---|
| `GDDP_LOCAL_SUBPROCESS_ARGV` | `scripts/adapters/local_subprocess_adapter.py:23` `_ARGV_ENV` | `:282` |
| `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` | `scripts/adapters/local_subprocess_adapter.py:24` `_SPOOL_ENV` | `:361` |
| `GDDP_LOCAL_SUBPROCESS_CWD` | `scripts/adapters/local_subprocess_adapter.py:25` `_CWD_ENV` | `:48` |
| `GDDP_DROID_SUBPROCESS_ARGV` | `scripts/adapters/local_subprocess_adapter.py:301` `_DROID_ARGV_ENV` | `:355` → `:282` |
| `GDDP_RECEIPTS_PATH` | `scripts/gddp_node_receipt.py:16` `RECEIPTS_PATH_ENV` | `:72` |
| `GDDP_WORKTREE_MAP_PATH` | `scripts/local_agent_executor.py:20` `_WORKTREE_MAP_ENV` | `:38` |
| `GDDP_PI_RPC_SPOOL_DIR` | `scripts/adapters/pi_rpc_adapter.py:38` `_SPOOL_ENV` | `:612` |
| `GDDP_PI_RPC_MODEL` | `scripts/adapters/pi_rpc_adapter.py:39` `_MODEL_ENV` | `:78` |
| `GDDP_PI_RPC_BINARY` | `scripts/adapters/pi_rpc_adapter.py:40` `_BINARY_ENV` | `:79` |
| `GDDP_PI_RPC_TOOLS` | `scripts/adapters/pi_rpc_adapter.py:41` `_TOOLS_ENV` | `:80` |
| `GDDP_PI_RPC_TURN_TIMEOUT_S` | `scripts/adapters/pi_rpc_adapter.py:42` `_TIMEOUT_ENV` | `:85` |

## Archive-only (not in main table)

Present under `scripts/_archive/` only:

| Variable | Read at |
|---|---|
| `GDDP_PUSH_AUDIT_PATH` | `scripts/_archive/mission_push_guard.py:17` (`_AUDIT_ENV`) |
| `GDDP_ENGAGEMENT_BRANCH` | `scripts/_archive/mission_push_guard.py:18` (`_BRANCH_ENV`) |
| `GDDP_REAL_GIT` | `scripts/_archive/mission_push_guard.py:19` (`_REAL_GIT_ENV`) |
| `GDDP_PUSH_WRAPPER_ACTIVE` | `scripts/_archive/mission_push_guard.py:20` (`_WRAPPER_ACTIVE_ENV`) |

## Validation

Command: `python3 -m pytest -q`

Tail line (verbatim):

```
4 failed, 622 passed in 37.02s
```

Failures observed in this worktree are pre-existing environment gaps (missing `flask` import in intake tests; one rig1 plist render assertion), not caused by this report-only change. Short summary of failures:

```
FAILED deploy/rig1-heartbeat/test_rig1_render_plist.py::test_render_heartbeat_invokes_real_runner_module
FAILED scripts/test_intake_server.py::test_health_returns_ok_with_webhook_verification_when_secret_resolved
FAILED scripts/test_intake_server.py::test_health_returns_503_when_secret_unresolved
FAILED scripts/test_intake_webhook_roundtrip.py::test_signed_webhook_post_creates_event_row_and_raw_payload
```

