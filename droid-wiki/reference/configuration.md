# Configuration

GDDP Runtime has no YAML or TOML config file of its own. Behavior is driven by environment variables plus the project graph YAML that lives in the separate `gddp-config` checkout. This page lists every environment variable the runtime reads, where it is read, and what happens when it is unset. Paths below are resolved at import time in several modules, so set these before starting the intake server, heartbeat, or bridge.

The two path variables that matter most are `GDDP_CONFIG_PATH` (where the graph lives) and `GDDP_RUNTIME_ROOT` (where runtime state lives). Everything else is credentials, provider tuning, or evaluator timeouts.

## Paths and runtime root

| Variable | Purpose | Default | Required |
|---|---|---|---|
| `GDDP_CONFIG_PATH` | Root of the `gddp-config` checkout. Read by the graph reader, bridge, return router, and graph updater to locate `graphs/<project_id>/project.yaml` and node YAML. | `<runtime_root>/../gddp-config` (sibling directory convention) | No, but the default only works if `gddp-config` is checked out next to `gddp-runtime`. |
| `GDDP_RUNTIME_ROOT` | Root directory for runtime state: `db/queue.db`, `events/raw/`, `events/normalized/`, `jobs/`. Used by intake server, heartbeat, results store, decision loop, rollback, and dry run. | Directory two levels up from `scripts/` (the repo root). | No. |
| `OPCLAW_ROOT` | Legacy alias for `GDDP_RUNTIME_ROOT`. Read only as a fallback when `GDDP_RUNTIME_ROOT` is unset. | (none) | No. Kept for backward compatibility with older Pi deployments. |

## GitHub credentials and webhook security

| Variable | Purpose | Default | Required |
|---|---|---|---|
| `GITHUB_TOKEN` | GitHub auth token used by the Jules action adapter to create dispatch issues and interact with the GitHub API. | (none) | Yes, for dispatch. Falls back to `GH_TOKEN`. |
| `GH_TOKEN` | Alternate name for the GitHub auth token. Used only if `GITHUB_TOKEN` is unset. | (none) | No, alternate for `GITHUB_TOKEN`. |
| `GITHUB_WEBHOOK_SECRET` | Shared secret used by the intake server to verify `X-Hub-Signature-256` on incoming webhooks. When unset, the server falls back to `GDDP_WEBHOOK_SECRET_CMD`. If neither resolves, signature verification is disabled and the server prints a warning. | (none) | Yes in any public-facing deployment. |
| `GDDP_WEBHOOK_SECRET_CMD` | Shell command that prints the webhook secret to stdout, so the secret never sits in a plaintext env file. Run only when `GITHUB_WEBHOOK_SECRET` is empty. | `pass show gddp/webhook-secret` | No. Used when `GITHUB_WEBHOOK_SECRET` is not set directly. |

## LLM provider credentials and endpoints

The semantic lane and the decision loop both call OpenAI-compatible endpoints. DeepSeek is the default provider; GLM is the fallback. The bridge and CLI auto-select whichever has a key present when `GDDP_SEMANTIC_PROVIDER` is `auto`.

| Variable | Purpose | Default | Required |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | API key for the DeepSeek endpoint. Read by the semantic CLI, the bridge, and the decision loop engine. | (none) | Yes for live semantic verification with the DeepSeek provider. |
| `DEEPSEEK_BASE_URL` | Base URL for the DeepSeek OpenAI-compatible endpoint. | `https://api.deepseek.com` | No. |
| `DEEPSEEK_MODEL` | Model id sent to the DeepSeek endpoint. | `deepseek-chat` | No. |
| `GLM_API_KEY` | API key for the GLM (Zhipu) endpoint. Used when DeepSeek is not configured or when the provider is explicitly `glm`. | (none) | Yes for live semantic verification with the GLM provider. |
| `GLM_BASE_URL` | Base URL for the GLM OpenAI-compatible endpoint. | `https://open.bigmodel.cn/api/paas/v4` | No. |
| `GLM_MODEL` | Model id sent to the GLM endpoint. | `glm-4-flash` | No. |
| `GDDP_DEEPSEEK_KEY_CMD` | Shell command that prints the DeepSeek API key to stdout. The bridge runs this when `DEEPSEEK_API_KEY` is missing from the environment (cron and non-login contexts do not source shell secrets). Best-effort: if the fetch fails, the verifier's own error surfaces in the error record. | `pass show api/deepseek` | No. Used when the key is not exported into the environment. |

## Verifier and semantic lane tuning

These control the evaluator subprocess the bridge spawns on the return path and the CLI's semantic agent. The bridge passes a fixed default semantic argument string unless `GDDP_VERIFY_SEMANTIC_ARGS` overrides it.

| Variable | Purpose | Default | Required |
|---|---|---|---|
| `GDDP_VERIFY_TIMEOUT_SECONDS` | Wall-clock timeout for the verifier subprocess in the bridge. On timeout the bridge returns an error record and retries once. | `1500` | No. |
| `GDDP_VERIFY_SEMANTIC_ARGS` | Override string for the semantic CLI flags the bridge passes (mode, harness, provider, pi model, thinking level). Parsed with `shlex.split`. | `--semantic-mode live --semantic-harness pi --semantic-provider deepseek --semantic-pi-model deepseek-v4-flash --semantic-thinking medium` | No. |
| `GDDP_INTEGRITY_MODE` | Enables or disables lane 2 (fresh-eyes integrity review) in the bridge. The bridge defaults integrity on so every merged PR gets an integrity pass; set to `off` for dev/test runs. | `on` | No. |
| `GDDP_COMMAND_PROOF_TIMEOUT` | Timeout in seconds for deterministic command-proof probes that shell out to the repo under verification. | `300` | No. |
| `GDDP_SEMANTIC_PROVIDER` | Live semantic provider selection: `auto`, `deepseek`, or `glm`. `auto` prefers DeepSeek when a key is present, then GLM. | `auto` | No. |
| `GDDP_SEMANTIC_HARNESS` | Agent harness for the semantic phase: `auto`, `pi`, or `runner`. `pi` drives the pi coding agent with streaming read-only evidence tools; `runner` uses the built-in OpenAI-compatible loop. `auto` resolves to `runner`. | `auto` | No. |
| `GDDP_SEMANTIC_THINKING` | Pi thinking level (`off`, `minimal`, `low`, `medium`, `high`, `xhigh`) when the harness is `pi`. | `medium` | No. |
| `GDDP_SEMANTIC_PI_MODEL` | Pi model id (e.g. `deepseek-v4-flash`) for `--semantic-harness pi`. Empty string lets the pi agent pick its provider default. | (empty) | No. |
| `GDDP_SEMANTIC_MAX_TURNS` | Maximum live semantic agent turns before the agent finalizes. | `15` | No. |
| `GDDP_SEMANTIC_MAX_TOOL_CALLS` | Maximum semantic evidence tool calls before finalization. | `40` | No. |
| `GDDP_SEMANTIC_PROVIDER_MAX_TOKENS` | Maximum tokens requested from the live model per response. | `4096` | No. |
| `GDDP_SEMANTIC_MAX_TOOL_RESULT_CHARS` | Maximum serialized characters from a single semantic evidence tool result before truncation. | `50000` | No. |

## Notes on resolution order

- `GDDP_RUNTIME_ROOT` is always checked before `OPCLAW_ROOT`. If both are set, `OPCLAW_ROOT` is ignored.
- `GITHUB_TOKEN` is always checked before `GH_TOKEN`.
- The bridge resolves `DEEPSEEK_API_KEY` from the environment first, then from `GDDP_DEEPSEEK_KEY_CMD`. It never tries `pass` if the env var is already present.
- The intake server resolves `GITHUB_WEBHOOK_SECRET` from the environment first, then from `GDDP_WEBHOOK_SECRET_CMD`. If both are absent, signature verification is silently skipped and a warning is printed at startup.

For the SQLite schema these credentials protect, see [data models](data-models.md). For the libraries that parse these settings, see [dependencies](dependencies.md).
