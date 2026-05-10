# GDDP Runtime

**Graph-Driven Agentic Development Control Plane**

---

## What This Is

GDDP is a system for turning software projects into explicit maps of work, then using agents to move through those maps without losing human control.

Where most agentic developer tools operate as black boxes — you give them a task and hope for the best — GDDP breaks projects into explicit dependency graphs with acceptance criteria, constraints, and bounded scopes. Agents read those graphs, execute work, and produce receipts. The system does not automatically declare work complete. Instead, it stops at review: a human decides whether to accept, retry, or block each piece of work before graph truth advances.

This is the runtime repository: the execution and orchestration machinery. It reads human-owned project truth from a separate configuration repository (`gddp-config`), dispatches bounded work to executor agents, persists runtime state and structured receipts in SQLite, and stops at review. It does not define project truth, and it does not automatically mutate graph state on the return path.

---

## Why This Matters

### For Engineers

This is a working control plane for bounded agent autonomy. Most agent frameworks either operate as suggestion layers (GitHub Copilot, Claude in an editor) or run autonomously until they hit a token limit or get lost. GDDP sits between those extremes: agents do real work — opening PRs, writing tests, refactoring modules — but within explicit scopes defined by the graph, and they produce structured evidence that humans review before declaring nodes complete.

The system has:
- **Graph-driven dispatch**: A heartbeat loop reads the project graph from YAML, identifies ready nodes (all dependencies complete, no active jobs), and dispatches work to executor adapters.
- **Receipt-based return flow**: When a PR merges, the system converts it into a structured receipt with artifact references and moves the job into `awaiting_review` state. No silent writeback to graph truth.
- **SQLite state persistence**: Events, jobs, queue records, and results are persisted in a local SQLite database. Replay utilities allow reprocessing or retracing state from recorded history.
- **Executor adapters**: The system is not married to a single agent. `adapters/jules_action_adapter.py` dispatches work to Jules via GitHub Actions labels. Future adapters can route to Codex, Vertex, or custom executors.
- **Manual review workflow**: When a job lands in `awaiting_review`, the operator reviews the receipt plus artifacts and takes exactly one manual action: accept (update graph truth), retry (re-dispatch from persisted state), block (record the blocker), defer (leave for later), or reopen/supersede (revisit if downstream evidence invalidates it).

No automatic node advancement, no automatic review, no automatic graph writeback in this phase.

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
- **Test coverage**: 40 passing tests covering intake, heartbeat modules, state recording, executor adapters, and return routing.
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
- `scripts/runtime/heartbeat/runner.py` is the canonical entry point. It reads the project graph from `gddp-config`, identifies ready nodes (status=pending, all dependencies complete), checks for active jobs, classifies events, builds job payloads from node specs, and dispatches to executor adapters.
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
- Deployed as a systemd service (`opclaw-intake.service`) on the live control plane.

**Operational tooling**:
- `scripts/dry_run.py`: Local dry-run flow for practicing the runtime loop.
- `scripts/rollback.py`: Job rollback utility.
- `python3 -m runtime.replay`: Replay utilities for reprocessing or retracing state from recorded history.

**Deployment**:
- `deploy/deploy.sh`: Canonical deploy command. Copies committed runtime snapshot to `~/opclaw/scripts` and writes a deploy marker.
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
| `docs/` | Host roles, OpenClaw draft spec, and operator-practice notes |

---

## Local Development

### Prerequisites

- Python 3.9+
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

The `--config-path` flag is optional for local development if `gddp-config` is a sibling repo. It is required for deployed runs because the deployed runtime lives in `~/opclaw/scripts`, not next to the `gddp-config` checkout.

### Run tests

```bash
python3 -m pytest -q
```

Expected: 40 passing tests.

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
| `GITHUB_TOKEN` or `GH_TOKEN` | Required for Jules GitHub issue dispatch | Required for Jules adapter |
| `GITHUB_WEBHOOK_SECRET` | Optional webhook signature validation secret for `scripts/intake_server.py` | Optional |

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
- OpenClaw review/accept powers are draft/future (see `docs/openclaw-spec.md`), not the current stable contract
- `return_router.py` still has a hardcoded allowlist for `skchaudr/vault-doctor`

**Why this matters**: These limits are documented, not hidden. The system operates within a stable contract and does not attempt features that contradict the frozen runtime boundary.

---

## Related Documentation

- **Operational runbook**: `deploy/BIGPI_RUNBOOK.md` — deployment, service status, manual review workflow, troubleshooting
- **Change history**: `CHANGELOG.md` — Runtime milestones and boundary changes
- **Host roles**: `docs/host-roles.md` — OpenClaw topology, gateway vs worker nodes, deployment architecture
- **OpenClaw spec**: `docs/openclaw-spec.md` — Draft v0 spec for reasoning and control layer (future scope, not current contract)
- **Config repository**: `gddp-config` — Schemas, graphs, templates, and project truth

---

## Related Repos

| Repository | Purpose |
|---|---|
| `gddp-config` | Schemas, graphs, templates, doctrine |
| `gddp-runtime` | Runtime/orchestration layer |
| project repos | Where executor work and PRs actually happen |

---

## Status

- **Tests**: 40 passing (`python3 -m pytest -q`)
- **Live deployment**: Running on a Raspberry Pi control plane with systemd service units, webhook intake, and manual review workflow
- **Graph projects**: `vault-doctor` (7/7 nodes complete), `gddp-runtime` (1/1 nodes complete; OpenClaw expansion pending on `feat/openclaw-nodes`)
- **Current phase**: Frozen at receipt routing plus human review

---

## License

Not specified. Contact repository owner for licensing questions.
