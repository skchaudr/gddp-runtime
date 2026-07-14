# GDDP Runtime

**Graph-Driven Agentic Development Control Plane**

Don’t let code define correctness. Don’t let any single artifact define correctness.

---

## What This Is

GDDP is a system for turning software projects into explicit maps of work, then using agents to move through those maps without losing human control.

The rise of agentic coding tools has been rapid and varied — from inline completions in Copilot, to fast CLI agents that generate entire plans and features, to their IDE counterparts with richer UIs and easily surfaced toolsets and product integrations.

With the primary editing surfaces being covered, execution modes were the next novel advancement. Agents can be cold-started for each task, or kept idle and waiting — roughly, on-demand instantiation vs. an always-on, synchronous process. The two flavors that interested me most were both always-on: the synchronous, remotely persistent agent, and the asynchronous, dispatchable background agent. Tools like OpenClaw, and later Claude Code, picked up scheduling features that let them be triggered to pick up work on their own.

That raised the question: how do you get a synchronous, remotely persistent agent to coordinate with an asynchronous, dispatchable one?

Both camps share an assumption: the agent owns scope. It figures out what to do, then does it. GDDP starts from a different premise — scope is not the agent's job. Work is decomposed up front into a dependency graph with explicit acceptance criteria, constraints, and bounded scopes. Agents read nodes from that graph, execute the work, and produce structured receipts. The system does not automatically declare work complete; it stops at review, where a human decides whether to accept, retry, or block each piece before graph truth advances.

In short: the human operator declares what; the agents determine how. The relationship is asymmetric — "what" always trumps "how". This repository — gddp-runtime — is all about respecting the how.

Bounded work is dispatched to an agent through a thin adapter, with Jules wired in today and Codex or a local harness ready to take its place tomorrow. Runtime state and structured receipts are stored in SQLite for persistence. Crucially, the executor halts at the review gate, leaving the graph state unchanged.

Project truth lives in a separate repository (gddp-config); gddp-runtime reads it but never writes it.

---

## Why This Matters

This is a working control plane for **bounded agent autonomy**. I use "Graph-Driven Development Pipeline" as shorthand, but more accurately, this project is a semi-autonomous graph-driven agentic development pipeline with human-in-the-loop style review.

If you've used Jules or Devin, you know the async model: write a prompt, get a PR, review the diff, and hope the agent picked the right scope. If you've used Cursor or Claude Code, you know the synchronous model: the agent runs in your editor while you steer turn by turn. Both work. Neither answers a different question: how does a long-running software project decide what work is ready to execute next?

GDDP's answer is a human-owned project graph in `gddp-config`. Each node defines its own scope, acceptance criteria, dependencies, and execution constraints. The graph defines what work is possible — but nothing dispatches on its own. A human marks a node ready in the graph and files an implementation request: an issue tagged `node: <id>`. Untagged issues are deliberately ignored, never guessed. The runtime maps that request to the ready node, verifies it is safe to dispatch (all dependencies complete, no job already in flight), builds a job packet from the node specification, and hands it to an executor adapter.

Today that adapter files a GitHub issue labeled `jules`; Jules's GitHub Action in the target repo detects the label and runs the task. The dispatch contract is executor-agnostic: Codex, Pi, Droid, or any custom execution harness can implement the same interface while the graph remains the canonical source of project intent.

The system has:

- **Graph-driven dispatch**: A heartbeat loop reads the project graph
  from YAML, loads human-marked ready nodes, classifies inbound events
  against them, guards each dispatch (dependencies complete, no active
  job — `awaiting_review` counts as active), builds job payloads from
  node specs, and dispatches via executor adapters.
- **Receipt-based return flow**: When a PR merges, the system converts
  it into a structured receipt with artifact references and moves the
  job into `awaiting_review`. No silent writeback to graph truth, no
  claiming work is valid, complete, or accepted.
- **SQLite state persistence**: Every event, job, queue record, and
  result is a row. State is auditable and replayable;
  `python3 -m runtime.replay` lets you reprocess return events or
  re-dispatch jobs from persisted state.
- **Executor adapters**: `adapters/jules_action_adapter.py` is the
  working adapter. Adding a new executor means writing a new adapter
  against the same dispatch contract — not rewriting the orchestration
  layer.
- **Manual review workflow**: When a job lands in `awaiting_review`,
  the operator takes exactly one manual action: accept (update graph
  truth), retry (re-dispatch from persisted state), block (record the
  blocker), defer (leave for later), or reopen/supersede.

No automatic node advancement. No automatic review. No automatic graph
writeback. The graph is isolated to preserve human intent; nothing is
accepted until *you* say so.

### For Operators & Reviewers

This was built to manage real multi-month projects across multiple repos with agent assistance while keeping a human in control.

- **Visible state machines**: Every job, event, and result is a row in SQLite. You can audit the system's history, replay decisions, or trace why a job was dispatched.
- **Traceable agent work**: Executor outputs are structured receipts with artifact paths, PR links, and metadata. You know what the agent did and where the evidence lives.
- **Human-in-the-loop control**: Runtime does not silently rewrite graph truth. Merged PRs create receipts; humans decide whether graph truth changes.
- **Deployment rigor**: The system has a canonical deploy script (`deploy/deploy.sh`) that copies committed runtime snapshots to the execution surface and writes a deploy marker. No ad hoc script copying. No guessing what version is running.

This is not a demo. It runs on a live Raspberry Pi control plane, managing work across multiple projects with Jules as the executor agent. The operational runbook (`deploy/BIGPI_RUNBOOK.md`) documents the live deployment, service status, manual review workflow, and troubleshooting procedures.

### Why It's Technically Serious

- **Schema-driven architecture**: Project graphs, nodes, jobs, and results follow explicit YAML schemas in the config repository. The runtime reads those schemas; it does not invent its own structure.
- **Frozen boundaries**: This phase is intentionally frozen at receipt routing plus human review. The system does not attempt richer graph states, auto-review logic, or fully autonomous graph state machines. It stops at a stable contract and documents what is incomplete.
- **Replay and rollback**: Runtime state is replayable. `python3 -m runtime.replay --result-id <id>` recreates receipt/state routing for a recorded return event. `python3 -m runtime.replay --job-id <id>` re-dispatches a specific job after explicit operator confirmation.
- **Test coverage**: 255 passing tests covering intake, heartbeat modules, state recording, executor adapters, return routing, verification, and runtime-root configuration.
- **Operational hardening**: The live deployment has systemd service units, GitHub webhook signature validation (`GITHUB_WEBHOOK_SECRET`), and a documented review workflow. This is not a prototype running in a tmux session.

---

## Architecture

### Topology

GDDP is split across two repositories:

| Repository | Purpose |
|---|---|
| **gddp-config** | Human-owned project truth: schemas, templates, and project graphs. Agents read it; they do not write to it. |
| **gddp-runtime** | Execution machinery: heartbeat runner, executor adapters, webhook intake, SQLite state, receipt handling, and operational tooling. |

Current boundary rule:
- `gddp-config`: human-owned project truth
- `gddp-runtime`: execution machinery
- executors/agents: produce work and structured receipts
- human review: decides whether graph truth changes

Runtime does not mutate graph truth automatically. Merged PRs and executor outputs may create structured receipts. Runtime may move jobs into review-needed state. Runtime may not write completion into `gddp-config`.

### What Exists Today

**Graph-driven heartbeat**:
- `scripts/runtime/heartbeat/runner.py` is the canonical entry point. It reads the project graph from `gddp-config`, identifies ready nodes (status=ready in project.yaml), checks for active jobs, classifies events, builds job payloads from node specs, and dispatches to executor adapters.
- Modular heartbeat: `graph_reader.py`, `classifier.py`, `scope_checker.py`, `job_factory.py`, `state_recorder.py`, and `dispatcher.py` replace the Phase 3 hardcoded dispatcher with extensible components.

**Receipt-only return flow**:
- `scripts/runtime/return_router.py` converts merged PRs into structured review receipts. It no longer mutates graph truth or calls `graph_updater.py`.
- `scripts/runtime/results_store.py` writes return receipts into the canonical `results` table and preserves the `needs_review` status.
- Merged PR handling routes matching jobs and queue records to `awaiting_review` instead of implying automatic node completion.

**Executor adapters**:
- `scripts/adapters/jules_action_adapter.py`: Dispatches Jules work through GitHub issues with the `jules` label. Requires `GITHUB_TOKEN` or `GH_TOKEN`.
- `scripts/adapters/jules_cli_adapter.py`: CLI adapter stub (not implemented).

**SQLite state persistence**:
- `scripts/init_db.py` initializes the schema: `events`, `jobs`, `queue`, `results`.
- All mutations go through `state_recorder.py`. No ad hoc SQL scattered across the codebase.

**Webhook intake**:
- `scripts/intake_server.py` handles GitHub webhook intake, optional signature validation (`GITHUB_WEBHOOK_SECRET`), and event normalization.
- Deployed as a systemd service on the live control plane.

**Operational tooling**:
- `scripts/dry_run.py`: Local dry-run flow for practicing the runtime loop.
- `scripts/rollback.py`: Job rollback utility.
- `python3 -m runtime.replay`: Replay utilities for reprocessing or retracing state from recorded history.

**Deployment**:
- `deploy/deploy.sh`: Canonical deploy command. Copies committed runtime snapshot to the runtime install path and writes a deploy marker.
- `deploy/BIGPI_RUNBOOK.md`: Operational runbook for the live control plane.

---

## Structure

| Path | Purpose |
|---|---|
| `scripts/runtime/heartbeat/` | Canonical graph-driven heartbeat runner |
| `scripts/runtime/return_router.py` | Receipt-only merged-PR return handling |
| `scripts/runtime/results_store.py` | Receipt persistence into the canonical `results` table |
| `scripts/init_db.py` | SQLite schema initialization |
| `scripts/intake_server.py` | Webhook intake and event normalization |
| `scripts/dry_run.py` | Local dry-run flow for practicing the runtime loop |
| `scripts/rollback.py` | Job rollback utility |
| `scripts/adapters/` | Executor adapters |
| `deploy/` | Deployment scripts and operator runbooks |
| `docs/` | Host roles and operator-practice notes |

---

## Local Development

### Prerequisites

- Python 3.11+
- `gddp-config` repository cloned locally (sibling to `gddp-runtime` or set via `GDDP_CONFIG_PATH`)

### Initialize the DB

```bash
python3 scripts/init_db.py
```

### Run the dry run

```bash
python3 scripts/dry_run.py
```

### Run the heartbeat

```bash
python3 -m runtime.heartbeat.runner \
  --project <project-id> \
  --repo <owner/repo> \
  --config-path /path/to/gddp-config
```

The `--config-path` flag is optional for local development if `gddp-config` is a sibling repo. It is required for deployed runs because the deployed runtime does not live next to the `gddp-config` checkout.

### Run tests

```bash
.venv/bin/python -m pytest -q scripts
```

Expected: 255 passing tests.

---

## Manual Review Workflow

Runtime stops at receipts. When a job lands in `awaiting_review`, the operator reviews the `results` row plus job artifacts and then takes exactly one manual action:

1. **accept**: Update graph truth manually in `gddp-config`.
2. **retry**: Re-dispatch the job from persisted state.
3. **block**: Leave graph truth unchanged and record the blocker outside runtime.
4. **defer**: Leave the receipt/job in review-needed state for later.
5. **reopen** or **supersede**: Revisit or replace the work later if downstream evidence invalidates it.

There is no automatic node advancement, automatic review, or automatic graph writeback in this phase.

---

## Replay

Replay reuses persisted runtime state rather than re-receiving or re-classifying events.

**Recreate receipt/state routing for a recorded return event**:
```bash
python3 -m runtime.replay --result-id <result-id>
```

**Re-dispatch a specific job after explicit operator confirmation**:
```bash
python3 -m runtime.replay --job-id <job-id>
```

---

## Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `GDDP_CONFIG_PATH` | Path to the sibling `gddp-config` repo for graph reads | Optional for local dev if sibling; required in deployment |
| `GDDP_RUNTIME_ROOT` | Runtime state root for SQLite, events, and jobs; defaults to the repo root locally and `~/opclaw` in deployment | Optional for local dev; set by deployed service |
| `GITHUB_TOKEN` or `GH_TOKEN` | GitHub API access for the Jules adapter (issue dispatch) | Required for Jules adapter |
| `GITHUB_WEBHOOK_SECRET` | Webhook signature validation secret for `scripts/intake_server.py` | Optional |

---

## Current Limits

This phase is intentionally frozen at receipt routing plus human review.

**What is not implemented**:
- Richer graph states (e.g., `in_review`, `review_failed`, `blocked_on_dependency`)
- Auto-review logic
- Automatic return-path graph mutation
- Fully autonomous graph state machines
- Worker-host cutover (documented in `docs/host-roles.md` as pending)
- `scripts/adapters/jules_cli_adapter.py` is a stub
- `return_router.py` still has a hardcoded allowlist for `skchaudr/vault-doctor`

**Why this matters**: These limits are documented, not hidden. The system operates within a stable contract and does not attempt features that contradict the frozen runtime boundary.

---

## Related Documentation

- **Operational runbook**: `deploy/BIGPI_RUNBOOK.md` — deployment, service status, manual review workflow, troubleshooting
- **Change history**: `CHANGELOG.md` — Runtime milestones and boundary changes
- **Host roles**: `docs/host-roles.md` — deployment topology, gateway vs worker nodes
- **Config repository**: `gddp-config` — Schemas, graphs, templates, and project truth

---

## Related Repos

| Repository | Purpose |
|---|---|
| `gddp-config` | Schemas, graphs, templates, doctrine |
| `gddp-runtime` | Runtime/orchestration layer |
| project repos | Where executor work and PRs actually happen |

---

## Canonical Documents

Four documents are canon — human-owned, kept small, and the reference when prose and code disagree:

1. The project's **foundational node** (first node listed in its `project.yaml` in `gddp-config`)
2. This **README** — the high-level idea, for every audience
3. **PROJECT-BRIEF.md** — doctrine, direction, and known gaps
4. **AGENTS.md** — executor-facing rules

Canon has audiences: AGENTS.md is canon for *executors* and is deliberately excluded from *evaluator* context — evaluators judge against graph truth, not executor instructions. Everything else (handoffs, specs, generated wikis, receipts) is disposable reference, not canon.

---

## Status

- **Tests**: 255 passing (`.venv/bin/python -m pytest -q scripts`)
- **Live deployment**: Raspberry Pi control plane (pi-big) — webhook intake + 5-minute heartbeat cron, two-lane verification (criteria + integrity), manual review workflow
- **Current phase**: live intake → dispatch → verification → human review; graph truth advances only by human acceptance

---

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](./LICENSE) for the full text.

Copyright 2024–2026 Saboor.
