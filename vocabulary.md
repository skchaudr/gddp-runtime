# vocabulary.md — Closed Project Namespace

This document is the authoritative resolution table for GDDP terminology. 

> **Agent Invariant:** Unknown term → check vocabulary → do not invent. If a term is not in this table, or marked `unresolved`, treat it as undefined and do not synthesize architecture around it.

---

## Term Resolution Table

| Term | Status | Authority / Pointer | Definition & Invariant |
|---|---|---|---|
| **node** | `defined` | [`entities/node.md`](entities/node.md) | The atomic unit of project intent. Carries goal, constraints, and acceptance criteria. Authored and approved exclusively by human operators. |
| **graph** | `defined` | [`entities/graph.md`](entities/graph.md) | The directed acyclic graph (DAG) of nodes in `gddp-config/graphs/<project>/`. Node status in the graph is graph truth and is modified solely by human keypress. |
| **heartbeat** | `defined` | [`entities/heartbeat.md`](entities/heartbeat.md) | Periodic dispatch process (`deploy/mini-heartbeat/bin/arm.sh`). Claims ready nodes from queue and hands each to an executor. SKip direct runner calls; only invoke via mini-heartbeat kit. |
| **executor** | `defined` | [`entities/executor.md`](entities/executor.md) | Agent session worker running in an isolated git worktree. Executes node packet, runs tests, and produces return receipt files. Transport/worker is replaceable; does not own graph truth. |
| **evaluator** | `defined` | [`entities/evaluator.md`](entities/evaluator.md) | Two-lane automated verification pass (deterministic + semantic criteria, intent/integrity) producing a worst-of verdict receipt. Evaluator output is evidence for human review, never graph truth. |
| **receipt** | `defined` | [`entities/receipt.md`](entities/receipt.md) | Structured evidence record (`GDDP_RECEIPTS_PATH` or `gddp-config/verification/`) documenting execution results, diffs, or evaluation verdicts. Files are truth; SQLite database is an index. |
| **gate token** | `defined` | [`scripts/runtime/gate_tokens.py`](scripts/runtime/gate_tokens.py) | Cryptographic capability token granting single-node dispatch / return transition. |
| **frontier** | `defined` | [`entities/graph.md`](entities/graph.md) | The current set of unblocked, ready nodes eligible for dispatch. |
| **continuation proposal** | `defined` | [`entities/node.md`](entities/node.md) | Proposed node YAML describing work discovered outside an active node's scope. Placed in proposals ledger; invisible to frontier until human materializes it into graph. |
| **evidence link** | `defined` | [`context.md`](context.md) | Non-dependency provenance link tying node runs, tests, or receipts to nodes without altering DAG topology. |
| **dependency edge** | `defined` | [`entities/graph.md`](entities/graph.md) | Strict topological dependency between nodes in the graph DAG governing execution order. |
| **jobs_status** | `defined` | [`scripts/jobs_status.py`](scripts/jobs_status.py) | Backend CLI and service managing runtime queue and job state in `db/queue.db`. May update runtime job state; must NEVER update graph node status. |
| **intake server** | `defined` (frozen) | [`scripts/intake_server.py`](scripts/intake_server.py) | Webhook receiver on `sab-mini:5050`. In frozen state; do not modify unless requested by a named node. |
| **provisional** | `defined` | [`docs/proposals/LOOP.md`](docs/proposals/LOOP.md) · [`docs/invariants/invariants.md`](docs/invariants/invariants.md) | Evaluator-passed, human-unaccepted intermediate status. Written by the runtime only with a concrete verdict receipt backing it; satisfies dependency edges for provisional traversal until the operator accepts (`complete`) or rejects (`ready`). |
| **MWP** | `unresolved` | — | **DO NOT EXPAND.** Unresolved term from legacy explorations. Do not design or infer architecture around MWP. |
| **conductor** | `historical/noncanonical` | [`docs/archive/`](docs/archive/) | Deprecated orchestration concept superseded by the 5-step operating loop. |
| **mission mode** | `historical/noncanonical` | [`docs/archive/`](docs/archive/) | Deprecated multi-node batch runner concept superseded by atomic node dispatch and worktree per session. |
| **OR mission** | `historical/noncanonical` | [`docs/archive/`](docs/archive/) | Deprecated concept. Demolished per `docs/089-OR-mission-demolition-work-order.md`. |
