# AGENTS.md — gddp-runtime

GitHub webhook intake → classify → scope → queue → execute pipeline.
Python scripts in `scripts/`, deploy configs in `deploy/`, docs in `docs/`.
No requirements.txt — scripts use stdlib + Flask (see `deploy/setup.sh`).

Portfolio brief + system narrative: [`PROJECT-BRIEF.md`](PROJECT-BRIEF.md).

## Environment

| Var | Purpose | Set by |
|---|---|---|
| `GDDP_RUNTIME_ROOT` | Override default runtime root path | Optional |
| `GITHUB_WEBHOOK_SECRET` | Validate incoming webhook signatures | Operator |

## Project snapshot

- **Language:** Python 3.11+ (stdlib + Flask)
- **Install:** `pip install flask` (see `deploy/setup.sh` for full pi-big setup)
- **Test:** `python3 -m pytest -q` (suite); `python3 scripts/dry_run.py` for an
  end-to-end fake flow (SQLite only)
- **Lint:** none configured
- **Heavy dirs excluded from git:** `db/`, `jobs/`, `events/` (runtime state, never committed)
- **Key files:** `scripts/intake_server.py`, `scripts/dry_run.py`, `scripts/runtime/`
