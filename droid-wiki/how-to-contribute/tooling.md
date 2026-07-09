# Tooling

This page covers the build system, development tools, and deployment scripts used in GDDP Runtime.

## Python

Python 3.11+ is the runtime language. The standard library does most of the work. External dependencies are limited to Flask, PyYAML, Pydantic, and the Anthropic SDK, all listed in `requirements.txt`.

```bash
pip install -r requirements.txt
```

The `setup.sh` script at the repo root handles the basic setup: checks Python version, installs Flask, verifies key scripts exist, runs the dry run, and prints a snapshot of the branch and Python version.

```bash
bash setup.sh
```

There is no virtual environment tooling configured. Use whatever venv or conda environment you prefer. The only hard requirement is Python 3.11+.

## No linter

No linter is configured. There is no `pyproject.toml` with ruff or flake8 settings, no pre-commit hooks, and no lint step in any CI or deployment script. Code style is enforced by convention, not tooling. See [Patterns and conventions](patterns-and-conventions.md) for the coding conventions the project follows.

## pytest

Testing uses pytest. The suite is 212 tests, all passing:

```bash
python3 -m pytest -q
```

Test files live alongside source files (`test_*.py` in the same directory as the module they test). See [Testing](testing.md) for the full breakdown of test categories.

## gh CLI

The GitHub CLI (`gh`) is the dispatch mechanism for the Jules executor adapter. It creates GitHub issues on target repositories with bounded work packets. The adapter respects `GITHUB_TOKEN` or `GH_TOKEN` environment variables, or the CLI's own auth state.

```bash
gh auth status
```

See [Debugging](debugging.md) for what to do when `gh` is not authenticated.

## Flask dev server

The intake server (`scripts/intake_server.py`) is a Flask app that runs on port 5050. For local development:

```bash
python3 scripts/intake_server.py
```

This starts the Flask dev server on `http://127.0.0.1:5050`. To expose it to GitHub webhooks during local development, use ngrok:

```bash
ngrok http 5050
```

Then paste the ngrok HTTPS URL into the GitHub repository webhook settings. The server checks for `db/queue.db` on startup and exits if it does not exist. See [Debugging](debugging.md) for the health endpoint and common startup issues.

## systemd

Production intake runs as a systemd service on Big Pi. The service file is `gddp-intake.service`, running `scripts/intake_server.py` directly from the repo checkout.

```bash
sudo systemctl status gddp-intake --no-pager
sudo systemctl restart gddp-intake
```

The intake server loads code at start, so restarting the service picks up new code. See the [Big Pi runbook](../../deploy/BIGPI_RUNBOOK.md) and [Deployment](../deployment.md) for the full operational details.

## cron

The heartbeat runs on a user crontab, every 5 minutes, executing `python3 -m scripts.runtime.heartbeat.runner` from the repo checkout. Unlike the intake server, the heartbeat picks up new code on the next cron tick automatically, no restart needed.

```bash
crontab -l | grep heartbeat
```

To run the heartbeat manually:

```bash
python3 -m scripts.runtime.heartbeat.runner \
  --project <project-id> \
  --repo <owner/repo> \
  --config-path /path/to/gddp-config
```

## deploy.sh

`deploy/deploy.sh` is the canonical deployment script for Big Pi. It copies a committed `gddp-runtime` snapshot into the runtime scripts directory and writes a deploy marker (`.gddp-runtime-deploy.json`) recording exactly which git commit is running.

```bash
bash deploy/deploy.sh
bash deploy/deploy.sh --restart-intake
```

The `--restart-intake` flag restarts the systemd service after syncing scripts. The script creates the runtime directory structure (`db/`, `events/raw`, `events/normalized`, `jobs/`) if it does not exist, backs up the previous scripts directory, and writes the deploy marker. See [Debugging](debugging.md) for how to read the deploy marker.

## dry_run.py

`scripts/dry_run.py` is the local practice tool. It walks one mock GitHub PR event through the full pipeline with SQLite only, no real executors, no GitHub API, no LLM calls. Use it to validate pipeline plumbing changes without dispatching real work.

```bash
python3 scripts/dry_run.py
```

## graphify

Graphify generates a knowledge graph from the repository structure and documentation. The output lives in `graphify-out/` (excluded from git). The current branch is `chore/graphify-update`, which refreshes the knowledge graph. Graphify is not part of the runtime itself, it is a documentation and exploration tool.

## Related pages

- [Testing](testing.md) - the 212-test suite
- [Debugging](debugging.md) - inspecting state and common issues
- [Deployment](../deployment.md) - full deployment guide
- [Getting started](../overview/getting-started.md) - install and first run
