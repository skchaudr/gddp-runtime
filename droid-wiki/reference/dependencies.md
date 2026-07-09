# Dependencies

GDDP Runtime is intentionally light on dependencies. The control plane is Python 3.11+ stdlib plus four packages, a SQLite database, and a couple of external binaries for GitHub dispatch and credential resolution. There is no `requirements.txt` for dev or test tooling: `pytest` is used for the test suite but is not listed and must be installed separately.

## Python packages

Declared in `/Users/sab-mini/repos/gddp-runtime/requirements.txt`. Install with `pip install -r requirements.txt`.

| Package | Minimum version | Purpose |
|---|---|---|
| `flask` | `>=3.0` | The intake webhook server in `scripts/intake_server.py`. Only the `/webhook` and `/health` routes depend on it. |
| `pyyaml` | `>=6.0` | Loading project graphs and node YAML from `gddp-config`, plus shape profiles in the verifier CLI. |
| `pydantic` | `>=2.0` | Verdict, semantic, and integrity models in `scripts/runtime/verification/schemas.py`. Uses `BaseModel`, `Field`, and `model_validator`. |
| `anthropic` | `>=0.40` | Anthropic SDK, available for model interactions. The live semantic lane currently runs through OpenAI-compatible DeepSeek and GLM endpoints rather than the Anthropic API directly. |

## Standard library

Used throughout and always available on Python 3.11+.

| Module | Where |
|---|---|
| `sqlite3` | All database access: `scripts/init_db.py`, `scripts/intake_server.py`, `scripts/runtime/results_store.py`, `scripts/runtime/return_router.py`. |
| `dataclasses` | `NodeData`, `ProjectGraph`, `DeterministicResult`, `CriterionCheck`, `ConstraintCheck` in the schemas and graph reader. |
| `enum` | `Verdict` enum in `scripts/runtime/verification/schemas.py`. |
| `argparse` | Verifier CLI in `scripts/runtime/verification/cli.py`. |
| `hmac`, `hashlib` | Webhook signature verification in `scripts/intake_server.py`. |
| `subprocess`, `shlex` | Bridge subprocess invocation and credential command resolution. |
| `pathlib`, `os`, `json`, `re`, `datetime` | Pervasive. |

## External binaries

| Binary | Purpose | Required |
|---|---|---|
| `gh` (GitHub CLI) | Dispatching jobs as GitHub issues via the Jules action adapter. The adapter shells out to `gh` to create issues and interact with the repo. | Yes, for dispatch. |
| `pass` (password manager) | Optional credential resolution. The bridge and intake server default to `pass show ...` commands for `DEEPSEEK_API_KEY` and `GITHUB_WEBHOOK_SECRET` when those env vars are absent. Both commands are configurable via `GDDP_DEEPSEEK_KEY_CMD` and `GDDP_WEBHOOK_SECRET_CMD`, so `pass` itself is not hard-required, only the configured credential command must resolve. | No, but the default credential commands assume it. |

## Dev and test tooling

`pytest` runs the test suite (`python3 -m pytest -q`) but is not listed in `requirements.txt`. Install it separately in your dev environment. The end-to-end fake flow (`python3 scripts/dry_run.py`) needs only the runtime dependencies above plus a SQLite database initialized by `scripts/init_db.py`.

No linter is configured for this repo.

For the environment variables that configure these dependencies, see [configuration](configuration.md). For the data structures they produce and consume, see [data models](data-models.md).
