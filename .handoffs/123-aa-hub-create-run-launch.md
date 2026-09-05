# 123 — aa-hub-create graph launched: node 0 on cursor_cli/grok

------------------------------------------------ Agent Section START

Date: 2026-09-05
Worktree: /Users/sab-mini/repos/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

New graph `aa-hub-create` (6 nodes, linear chain, retry_budget 2, cursor_cli) authored in gddp-config@96f1f26 from the PRD (`aa-cli/hub-rs/docs/PRD-aa-hub-create.md`) + lovable spec (`aa-cli/docs/tui-pass/lovable-prototype-spec.md`). Node 0 `nav-input-repair` dispatched via cursor_cli with model `cursor-grok-4.6-xhigh-fast`; executor pid 84895 streaming events at session start. Three launch blockers fixed en route: missing `GDDP_CURSOR_CLI_SPOOL_DIR`, queue.db schema drift (5 additive columns via `scripts/init_db.py`), and a crash-claimed frontier event manually reset to `received` (planner vocabulary is `received`, not `pending` — runner.py:385).

### Scope touched (One file per line, +/- for only what was changed)

- deploy/mini-heartbeat/env/gddp.env (+GDDP_CURSOR_CLI_SPOOL_DIR; file is gitignored)
- db/queue.db (additive migration + one event status reset; db/ is gitignored; backup at db/queue.db.bak-20260905)
- gddp-config: graphs/aa-hub-create/{project.yaml,nodes/*.yaml}, scripts/{validate.py,import_node.py} (+cursor_cli mode) — committed 96f1f26, pushed
- aa-cli: docs/tui-pass/lovable-prototype-spec.md (e8ce19c, +card-screen fix 1c7d2e7) — pushed
- NOT touched: S1's uncommitted orchestrator_decision.py / orchestrator_prompt.py work in this repo

### Constrained areas touched (none / list + justification)

- db/queue.db direct UPDATE on events row (crash recovery; jobs_status.py has no event-reset path; runtime state, not graph truth)

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

gddp-runtime main == origin/main except S1's uncommitted files (leave alone). gddp-config and aa-cli main == origin/main.

### Artifacts (Filepath - Description, 1 line max per artifact)

- jobs/cursor-cli-spool/job_20260905T095152563d9351acedb8-attempt-0-c68b9af5.../ — live attempt dir (events.jsonl, pid, packet.json)
- aa-cli/docs/tui-pass/lovable-prototype-spec.md — 13-screenshot visual spec
- aa-cli/hub-rs/docs/PRD-aa-hub-create.md — PRD with acceptance A–F

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Watch attempt: `tail jobs/cursor-cli-spool/<dir>/events.jsonl`, `kill -0 $(cat <dir>/pid)`, wait for exit.json/result.json. Next tick reconciles + runs evaluator automatically: `bash -c 'source deploy/mini-heartbeat/bin/common.sh && cd "$GDDP_RUNTIME_ROOT" && export GDDP_REPO_ROOT="$GDDP_REPOS_ROOT" PYTHONPATH="$GDDP_RUNTIME_ROOT" && GDDP_CURSOR_CLI_MODEL=<model> "$GDDP_PYTHON" -m scripts.runtime.heartbeat.runner --project aa-hub-create --repo skchaudr/aa-cli --config-path "$GDDP_CONFIG_PATH"'`. Model plan: grok on nodes 0+5, composer-2.5 on 1–4 (set GDDP_CURSOR_CLI_MODEL per tick; chain is linear so one job in flight).

------------------------------------------------ Agent Section END
