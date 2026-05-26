# Handoff for Pi README Agent

This document is a cold-start handoff for a Pi-side agent that will draft a portfolio README for GDDP. Do not write the README in this pass unless explicitly asked; this file exists to prepare the next agent.

## Project identity

GDDP is a system for turning software projects into explicit maps of work, then using agents to move through those maps without losing human control. Underneath that plain-language idea is a graph-driven agentic development control plane: `gddp-config` defines project truth as schemas, graphs, nodes, constraints, and acceptance criteria; `gddp-runtime` reads that truth, dispatches bounded work, records jobs/results/receipts in SQLite, and stops at human review instead of silently rewriting the graph.

## Repo topology

GDDP is split across two repos:

- `gddp-runtime`: the primary repo for the portfolio README. It contains the runtime/orchestration layer, the Big Pi deployment scripts, the heartbeat loop, executor adapters, webhook intake, result/receipt handling, tests, and operational docs.
- `gddp-config`: the technical source-of-truth repo. It contains schemas, templates, and project graphs. It should be referenced from the runtime README, not merged into it.

Recommended README placement:

- Draft the primary portfolio `README.md` in `gddp-runtime`.
- Keep `gddp-config/README.md` as a smaller technical contract for schemas/graphs/templates.
- In the runtime README, include a concise topology section explaining that the config repo is where project truth lives and the runtime repo is the execution/control-plane layer.

## Current state (post-hygiene)

### gddp-runtime

Current branch: `main`, clean and pushed to `origin/main`.

Recent commit arc:

- `adb597b chore: ignore local runtime artifacts`
- `dc9ce4d chore: remove empty vscode recommendations`
- `8f08adc docs: move operator practice notes`
- `fa0ac90 docs; sync to khoj VM for operator checklist runs`
- `79be0c7 docs: make runtime README environment-agnostic`
- `433ce21 chore: document manual operator boundary and harden adapter auth`
- `4526dc2 docs: freeze receipt review workflow`
- `24a3bc7 runtime: sever graph mutation from return flow`

Top-level structure:

- `README.md`: current operational README; accurate but too technical/closed-door for a mixed portfolio audience.
- `CHANGELOG.md`: recent runtime milestones and boundary changes.
- `scripts/`: runtime code, tests, adapters, heartbeat modules, return routing, replay, and decision-loop draft pieces.
- `deploy/`: Big Pi setup/deploy scripts, systemd unit, and operator runbook.
- `docs/`: host roles, decision-loop draft spec, and operator-practice notes.
- `.vscode/gddp-runtime.code-workspace`: kept because it is the useful multi-root workspace pointer.

What works:

- Runtime tests pass locally: `python3 -m pytest -q` -> `40 passed`.
- `scripts/init_db.py` initializes the SQLite schema.
- `scripts/intake_server.py` handles GitHub webhook intake and optional `GITHUB_WEBHOOK_SECRET` signature validation.
- `scripts/runtime/heartbeat/runner.py` is the canonical graph-driven heartbeat entrypoint.
- `scripts/runtime/heartbeat/graph_reader.py` reads `gddp-config` via `--config-path`, `GDDP_CONFIG_PATH`, or sibling repo fallback.
- `scripts/adapters/jules_action_adapter.py` dispatches Jules work through GitHub issues and requires `GITHUB_TOKEN` or `GH_TOKEN`.
- `scripts/runtime/return_router.py` converts merged-PR return events into review receipts.
- `scripts/runtime/results_store.py` writes receipt rows to the canonical `results` table.
- `deploy/deploy.sh` copies a committed runtime snapshot into `~/opclaw/scripts` and writes a deploy marker.
- `deploy/BIGPI_RUNBOOK.md` is the operational runbook for the live Big Pi control plane.

What is intentionally incomplete or frozen:

- Runtime must not mutate `gddp-config` automatically.
- Merged PRs create structured receipts and move work to review-needed states; human review decides whether graph truth changes.
- `scripts/runtime/graph_updater.py` remains only as a disabled compatibility stub.
- No auto-review, richer graph state machine, or automatic return-path completion in the frozen phase.
- `scripts/adapters/jules_cli_adapter.py` is a stub.
- Decision-loop review/accept powers are draft/future, not the current stable contract.
- `docs/host-roles.md` says Small Pi worker cutover is still pending.
- Some decision-loop draft code appears ahead of the frozen runtime contract; treat it as experimental until verified on Pi.
- `return_router.py` still has a hardcoded allowlist for `skchaudr/vault-doctor`.

Existing README assessment:

- Keep the factual boundary language: config truth vs runtime machinery vs executors vs human review.
- Keep the concrete structure table and local commands, but move them below a clearer human-readable opening.
- Replace the first impression. The current README starts like an internal operations memo; a portfolio README should open with what was built, why it matters, and why this is technically serious.
- Layer docs explicitly: `README.md` for portfolio + current operating contract, `deploy/BIGPI_RUNBOOK.md` for Big Pi ops, `docs/operator-practice/` for learning/manual-run drills, and `docs/decision-loop-spec.md` as draft/future design.
- Fix later nit: the current runbook link is absolute (`/work/repos/...`) and should become relative.

### gddp-config

Current branch name: `feat/openclaw-nodes`. The active graph objects now use decision-loop naming; the branch name is historical.

Recent commit arc:

- `c7287fc chore: ignore local agent artifacts`
- `201d5bc docs: archive april update transcript`
- `d91b38d git ignore`
- `cbdf8d2 feat: add decision-loop nodes to gddp-runtime graph`
- `fd50333 feat: triage-cli-core -> complete - vault-doctor 7/7 nodes done (#6)` on `origin/main`

Top-level structure:

- `README.md`: source-of-truth contract for schemas, graphs, and templates.
- `CHANGELOG.md`: schema/config change history.
- `schemas/v1/`: canonical YAML schemas for events, jobs, nodes, results, queue records, artifact verification, and task packets.
- `templates/`: reusable node and job templates.
- `graphs/`: project graphs for `_template`, `vault-doctor`, and `gddp-runtime`.
- `upgrade-strategy.md`: schema versioning, rollback, executor adapter, and credential isolation policy.
- `_archive/april-update.txt`: raw-ish historical terminal/conversation artifact; not operational documentation.
- `rules/`, `scripts/`, `workflows/`: present as future/empty local dirs, not tracked source yet.

What works:

- All YAML graph/schema/template files parse locally: `parsed 24 yaml files`.
- `graphs/vault-doctor` is complete with 7/7 nodes complete.
- `graphs/gddp-runtime/project.yaml` currently maps:
  - `return-router`: complete
  - `decision-loop-spec`: complete
  - `decision-loop-runtime`: pending
  - `decision-loop-review-gate`: pending
- Node files under `graphs/gddp-runtime/nodes/` hold the real acceptance criteria, constraints, allowed execution modes, and required artifacts.
- The repo's operating rule is clear: agents read it; they do not write to it.

What is intentionally incomplete or future:

- No executable validation/utility scripts yet.
- No rule configs yet.
- No workflow configs yet.
- `decision-loop-runtime` is the next real build node and expects implementation in `gddp-runtime`.
- `decision-loop-review-gate` follows `decision-loop-runtime`; do not pull it forward.

Existing README assessment:

- Keep `gddp-config/README.md` as a technical source-of-truth contract.
- Do not turn it into the main portfolio README.
- In a later polish pass, add a small current graph-state note or link so cold readers can see that `gddp-runtime` has two complete and two pending graph nodes.
- Note for future hardening: `graphs/gddp-runtime/project.yaml` uses `schema_type: project`, while the template/vault-doctor graph use `project_graph`. YAML parses, but a strict consumer may need compatibility or normalization.

## Portfolio framing (Pi agent voice — quote verbatim)

"This is a portfolio README for a project built solo by a recent CS graduate who entered the field later in life and is working at the technical frontier. Audience is mixed: senior engineers should see technical depth and honest tradeoffs; recruiters should see scope and seriousness; people without context should understand what was built and why it's interesting. Confident and accurate — not boastful, not self-deprecating."

## Pi agent deliverables

- Draft `README.md` in `gddp-runtime`, with appropriate cross-references to `gddp-config`.
- Produce a separate polish punchlist covering hardening opportunities across both repos.
- Do not push to GitHub. Drafts only.

Suggested README shape:

1. One plain-language opening: what GDDP does and why it is interesting.
2. A short architecture/topology section: config repo as project truth, runtime repo as control plane, agents as executors, human review as authority.
3. A concrete "what exists today" section that is honest about the frozen receipt-review boundary.
4. A "why this matters" section aimed at mixed readers: visible systems thinking, bounded autonomy, traceable agent work, human-in-the-loop control.
5. A technical depth section for engineers: SQLite receipts/jobs/results, graph-driven heartbeat, config schemas, executor adapters, Big Pi deployment.
6. A "current limits / next hardening" section that does not hide the incomplete decision-loop pieces.
7. Links to `gddp-config`, `deploy/BIGPI_RUNBOOK.md`, `docs/operator-practice/`, and `docs/decision-loop-spec.md`.

## Gotchas

Paths:

- Runtime repo on this machine: `/Users/saboor/repos/gddp-runtime`
- Config repo on this machine: `/Users/saboor/repos/gddp-config`
- Big Pi source runtime checkout: `~/repos/gddp-runtime`
- Big Pi source config checkout: `~/repos/gddp-config`
- Big Pi deployed execution surface: `~/opclaw/scripts`
- Big Pi live runtime state: `~/opclaw/db`, `~/opclaw/events`, `~/opclaw/jobs`

Environment variables:

- `GDDP_CONFIG_PATH`: path to the sibling `gddp-config` repo for graph reads.
- `GDDP_RUNTIME_ROOT`: runtime state root. Legacy `OPCLAW_ROOT` may still be accepted by older scripts as a compatibility fallback.
- `GITHUB_TOKEN` or `GH_TOKEN`: required for Jules GitHub issue dispatch.
- `GITHUB_WEBHOOK_SECRET`: optional webhook signature validation secret for `scripts/intake_server.py`.

Files/dirs to skip:

- Do not use `_archive/april-update.txt` as live docs; it is historical transcript material.
- Do not treat `.claude/`, `.aider*`, `.DS_Store`, `.pytest_cache/`, or `__pycache__/` as source material.
- Do not draft into `gddp-config` unless Saboor explicitly asks for a technical README update there.
- Do not mutate graph truth from runtime. The current contract is receipt creation plus human review.
- Do not make `docs/decision-loop-spec.md` the main README. It is useful design context, but it includes future/draft ideas that can contradict the frozen runtime boundary.
- Do not assume `rules/`, `scripts/`, or `workflows/` in `gddp-config` are implemented because the README mentions them as future surfaces.

Verification already run during this handoff:

- `gddp-runtime`: `python3 -m pytest -q` -> `40 passed`.
- `gddp-config`: Python/YAML parse pass over graphs, schemas, and templates -> `parsed 24 yaml files`.
