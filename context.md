# context.md — GDDP Runtime Global Context & Authority Map

This file is the root entry point for navigating and understanding `gddp-runtime`. It declares the authority hierarchy across all repository directories, establishes named-object resolution routes, and defines how agents must progressively narrow context.

---

## 1. Epistemic Authority Hierarchy

Prose and code in this repository do not compete at equal authority. When resolving conflicts, precedence flows strictly top-to-bottom:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. INVARIANTS (docs/invariants/, AGENTS.md)                │  MUST REMAIN TRUE
├─────────────────────────────────────────────────────────────┤
│ 2. CURRENT TRUTH (docs/current/, TOPOLOGY.md)              │  TRUE RIGHT NOW
├─────────────────────────────────────────────────────────────┤
│ 3. ACCEPTED DECISIONS (docs/decisions/)                     │  WHY WE CHOSE X
├─────────────────────────────────────────────────────────────┤
│ 4. RUNTIME CODE & SCRIPTS (scripts/runtime/, scripts/)      │  HOW IT EXECUTES
├─────────────────────────────────────────────────────────────┤
│ 5. PROPOSALS (docs/proposals/)                             │  MAY BECOME TRUE
├─────────────────────────────────────────────────────────────┤
│ 6. LEARNING & POSTMORTEMS (docs/learning/)                  │  EMPIRICAL EVIDENCE
├─────────────────────────────────────────────────────────────┤
│ 7. ARTIFACTS & RECEIPTS (docs/artifacts/, node_status_hist/)│  PAST OUTPUTS
├─────────────────────────────────────────────────────────────┤
│ 8. ARCHIVE (docs/archive/, deploy/_archive/)               │  HISTORICAL / OBSOLETE
└─────────────────────────────────────────────────────────────┘
```

- **Invariants:** Fundamental system laws (e.g. human operator is sole authority on graph truth; tests/receipts are evidence, not truth).
- **Current Truth:** Active contracts, live topology (`sab-mini`), active operating loop.
- **Decisions:** Accepted architectural records explaining rationale.
- **Proposals:** Non-canonical work proposals (do not assume accepted until promoted).
- **Archive:** Superseded or decommissioned architecture (must not be resurrected without explicit node authorization).

---

## 2. Global Directory Map

| Path | Authority Tier | Local Context Map | Description |
|---|---|---|---|
| [`/`](.) | Top-level | `context.md` | Global map, vocabulary resolution, entities index |
| [`vocabulary.md`](vocabulary.md) | Canon | — | Closed namespace resolution table |
| [`entities/`](entities/) | Index | — | Cross-cutting named thing definitions and pointers |
| [`docs/`](docs/) | Layered | [`docs/context.md`](docs/context.md) | Epistemic tiers: invariants, current, decisions, proposals, learning, archive |
| [`scripts/runtime/`](scripts/runtime/) | Implementation | [`scripts/runtime/context.md`](scripts/runtime/context.md) | Active execution engine (decision loop, gates, verifiers, return router) |
| [`scripts/`](scripts/) | Utilities & DB | — | Control plane backend (`jobs_status.py`), receipt CLI, init scripts |
| [`deploy/`](deploy/) | Deployment | [`deploy/context.md`](deploy/context.md) | Host deployment configs (`sab-mini` active, `pi-big` disarmed) |
| [`node_status_history/`](node_status_history/) | Evidence | [`node_status_history/context.md`](node_status_history/context.md) | Durable trace of human acceptance and verdict receipts |
| [`jobs/`](jobs/) | Mutable State | [`jobs/context.md`](jobs/context.md) | Ephemeral runtime job state and execution directories (untracked) |
| [`events/`](events/) | Telemetry | [`events/context.md`](events/context.md) | Ephemeral operational telemetry event logs (untracked) |
| [`db/`](db/) | Rebuildable Index | — | Local SQLite databases (`db/queue.db`) — rebuildable cache |

---

## 3. Named Entities Index

For cross-cutting concepts spanning code, deployment, and documentation, navigate directly via `entities/`:

- [`entities/node.md`](entities/node.md) — The atomic unit of project intent.
- [`entities/graph.md`](entities/graph.md) — Directed acyclic graph of nodes and acceptance authority.
- [`entities/heartbeat.md`](entities/heartbeat.md) — Periodic dispatch daemon and entrypoint constraints.
- [`entities/executor.md`](entities/executor.md) — Agent session worker and worktree isolation.
- [`entities/evaluator.md`](entities/evaluator.md) — Two-lane verification engine and evidence generation.
- [`entities/receipt.md`](entities/receipt.md) — Execution evidence and evaluation verdict records.

---

## 4. Progressive Context Narrowing Rules

Agents must navigate hierarchically rather than ingesting the entire repository:

1. **Resolve Terminology First:** Consult [`vocabulary.md`](vocabulary.md) before interpreting unfamiliar terms.
2. **Consult Global Map:** Identify which subtree holds authority over the question from this document.
3. **Traverse to Local Context:** Read the directory's `context.md` (e.g. [`scripts/runtime/context.md`](scripts/runtime/context.md), [`deploy/context.md`](deploy/context.md)) to identify active vs frozen modules.
4. **Inspect Specific Implementation:** Read the targeted source or decision record.

---

## 5. Operations & Runtime Startup Quickstart

👉 **Canonical Runbook:** [`deploy/STARTUP.md`](deploy/STARTUP.md)

| Action | Host | Command |
|---|---|---|
| **Preflight Smoke** | `sab-mini` | `bash deploy/mini-heartbeat/bin/smoke.sh` |
| **Arm / Start** | `sab-mini` | `MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh` |
| **Disarm / Stop** | `sab-mini` | `bash deploy/mini-heartbeat/bin/disarm.sh` |
| **Watch Fleet** | Any | `gddp watch` |
| **Steer Session** | Any | `gddp steer <node_id> "<guidance>"` |
| **Queue Status** | Any | `python3 scripts/jobs_status.py --summary` |
| **Fresh Linux Stand-up** | Linux | [`deploy/mini-heartbeat/FRESH-HOST-STANDUP.md`](deploy/mini-heartbeat/FRESH-HOST-STANDUP.md) |

