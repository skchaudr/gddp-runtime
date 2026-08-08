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

The direct executor set now also includes the single-node `local_subprocess`/`droid` transport and the multi-node `factory_mission` adapter. `factory_mission` projects an eligible graph subgraph into one unattended Factory headless mission while preserving a separate evidence and review record for every source node.

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
  Direct adapters include `local_subprocess`/`droid` for one packet per
  process and `factory_mission` for an engagement containing multiple
  topologically ordered node packets.
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
- `scripts/adapters/local_subprocess_adapter.py`: Runs one executor-neutral node packet per durable local subprocess; its `DroidSubprocessAdapter` specialization invokes `droid exec`.
- `scripts/adapters/mission_adapter.py`: Runs a selected subgraph as one Factory headless mission (`droid exec --mission`) and exposes engagement-level dispatch, status, collect, and cancel operations.

**SQLite state persistence**:
- `scripts/init_db.py` initializes the schema: `events`, `jobs`, `queue`, `results`.
- All mutations go through `state_recorder.py`. No ad hoc SQL scattered across the codebase.

**Webhook intake**:
- `scripts/intake_server.py` handles GitHub webhook intake, optional signature validation (`GITHUB_WEBHOOK_SECRET`), and event normalization.
- Deployed as a systemd service on the live control plane.

**Operational tooling**:
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
| `scripts/rollback.py` | Job rollback utility |
| `scripts/adapters/` | Executor adapters |
| `scripts/adapters/mission_projection.py` | Graph-node to Factory-mission projection |
| `scripts/adapters/mission_evidence.py` | Per-node evidence slicing after a mission |
| `scripts/adapters/mission_git_verify.py` | Per-node base-to-result git verification |
| `scripts/adapters/mission_push_guard.py` | PATH-shim and pre-push-hook mission push policy |
| `scripts/gddp_node_receipt.py` | Worker-facing per-feature git receipt CLI |
| `deploy/` | Deployment scripts and operator runbooks |
| `docs/` | Host roles and operator-practice notes |

---

## Factory Mission Executor

`factory_mission` lets GDDP dispatch a bounded, dependency-ordered subgraph as one Factory Mission engagement rather than cold-starting one executor process per node. It is an executor adapter, not a new scheduler, graph, evaluator, or review system: mission results return through the existing executor-session reconciler, two-lane evaluator, and human review gate.

### How it works

1. The heartbeat selects eligible ready work according to the graph and `execution_policy`, then sends topologically ordered `NodePacket`s through the engagement extension of `ExecutorAdapter`.
2. `mission_projection.py` renders `mission.md` with a contract-imposed **1:1 mapping**: every GDDP node becomes exactly one Factory feature with the same ID and order. Added, removed, renamed, split, merged, or reordered features park the engagement for human review.
3. `MissionAdapter` creates an isolated `gddp/<engagement-id>` work branch and launches:

   ```bash
   droid exec --mission -f <generated-mission.md> --auto high -w gddp/<engagement-id>
   ```

4. Each feature captures its starting SHA, makes exactly one commit carrying `GDDP-Node-Id: <node-id>`, invokes `gddp-node-receipt`, and pushes only its own commit to the engagement branch. Push policy is enforced twice: by a guarded `git` executable on `PATH` and by a pre-push hook.
5. After the mission terminates, GDDP slices the engagement artifacts into one evidence manifest per node. It independently verifies the declared base→result boundary, commit trailer, ancestry, changed paths, receipt, and remote reachability before the existing reconciler/evaluator/review pipeline consumes the result.

The contractual surface is **git**, not Factory's internal state. Factory's process exit and mission progress are coarse engagement evidence; per-node commits, refs, ancestry, and receipts establish what work can be attributed to each graph node.

### Records discipline and node fidelity

One mission process may execute several nodes, but it does not collapse their identities. Each `executor_sessions` row retains its own expected base, result commit, evidence manifest, and completion state. Completion IDs are nullable until independently observed; `completion_digest_sha256` binds accepted completion content, while `completion_quarantine_reason` records malformed or conflicting completion evidence instead of silently promoting it. `VerdictReceipt` may link the resulting judgment back to `execution_attempt_id`, `evidence_manifest_sha256`, and `mission_receipt_id`.

This is intentionally implemented through the existing adapter, session, reconciler, evaluator, and review seams. No new GDDP subsystem owns mission truth, and mission success never changes graph/node status.

### Configure and run mission mode

Prerequisites:

- Factory Droid installed, authenticated, and available as `droid`.
- A local checkout of the target repository with an `origin` remote.
- `gddp-config` available through `GDDP_CONFIG_PATH`.
- `gddp-node-receipt` on the mission workers' `PATH`.

Expose the checked-in receipt CLI under the contract name and configure the runtime:

```bash
mkdir -p "$HOME/.local/bin"
ln -sf "$PWD/scripts/gddp_node_receipt.py" "$HOME/.local/bin/gddp-node-receipt"
export PATH="$HOME/.local/bin:$PATH"
export GDDP_CONFIG_PATH=/path/to/gddp-config
export GDDP_RUNTIME_ROOT="$PWD"
```

Select mission mode in the human-owned graph. Every included node must allow `factory_mission`; the project policy controls the bounded engagement size:

```yaml
# graphs/<project-id>/project.yaml
execution_policy:
  default_executor: factory_mission
  max_concurrent_jobs: 4
  mission_engagement_size: 2
  mission_max_pairs: 2

# graphs/<project-id>/nodes/<node-id>.yaml
allowed_execution_modes:
  - factory_mission
```

For an armed control plane, use the mini-heartbeat kit so its environment, spool, and executor settings are loaded:

```bash
bash deploy/mini-heartbeat/bin/smoke.sh
MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh
```

Do not invoke the raw heartbeat runner or manually launch the generated mission during normal operation. The mini-heartbeat entrypoint loads `GDDP_CONFIG_PATH` and the executor environment, while the adapter owns the exact `droid exec --mission` command, receipt path, push guards, process supervision, and durable session record. Optional storage overrides are `GDDP_MISSION_SESSION_DIR` (default: `db/mission-sessions`) and `GDDP_FACTORY_MISSION_DIR` (default: `~/.factory/missions`).

Run the mission adapter and end-to-end pipeline tests with:

```bash
.venv/bin/python -m pytest -q \
  scripts/adapters/test_mission_adapter.py \
  scripts/adapters/test_mission_projection.py \
  scripts/adapters/test_mission_evidence.py \
  scripts/adapters/test_mission_git_verify.py \
  scripts/adapters/test_mission_push_guard.py \
  scripts/runtime/heartbeat/test_mission_config.py \
  scripts/runtime/heartbeat/test_mission_reconciler.py \
  scripts/runtime/heartbeat/test_mission_pipeline_e2e.py \
  scripts/test_gddp_node_receipt.py
```

---

## Local Development

### Prerequisites

- Python 3.11+
- `gddp-config` repository cloned locally (sibling to `gddp-runtime` or set via `GDDP_CONFIG_PATH`)

### Initialize the DB

```bash
python3 scripts/init_db.py
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
| `GDDP_MISSION_SESSION_DIR` | Durable `factory_mission` session records, logs, receipts, and evidence; defaults to `db/mission-sessions` | Optional |
| `GDDP_FACTORY_MISSION_DIR` | Factory mission state directory; defaults to `~/.factory/missions` | Optional |

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
