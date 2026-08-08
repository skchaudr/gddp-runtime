# Systems

Active contributors: Saboor

## Purpose

This section documents the runtime subsystems that turn graph state and intake events into executor attempts, evidence, and human review. For the system-wide map, see [Architecture](../overview/architecture.md). For the authority boundary between runtime evidence and human-owned graph truth, see [Doctrine](../background/doctrine.md).

## Subsystems

| System | Responsibility |
|---|---|
| [Heartbeat](heartbeat.md) | Reconcile active executor sessions, advance the eligible frontier, reserve work, dispatch attempts, and record outcomes |
| [Executor adapters](executor-adapters.md) | Present one executor-neutral lifecycle across Jules, local subprocesses, Droid, and mediated dispatch |
| [Factory mission](factory-mission.md) | Project ordered node packets into a multi-feature Factory mission and collect feature-scoped git evidence |
| [Verification](verification.md) | Produce a deterministic and semantic criteria verdict, combine it with the intent and integrity lane, and write a receipt |
| [Intake and control plane](intake-and-control-plane.md) | Normalize GitHub events, persist the SQLite control-plane schema, and expose runtime job inspection and mutation |
| [Return and review](return-and-review.md) | Route merged PRs and direct executor returns into structured results and human review |
| [Decision loop legacy](decision-loop-legacy.md) | Describe the inherited secondary wake, decide, act path |
| [Graph reader](graph-reader.md) | Read project and node YAML without mutating graph truth |
| [Graph updater](graph-updater.md) | Open evidence PR proposals for human review |
| [State persistence](state-persistence.md) | Describe the restored SQLite schema and persistence helpers |
| [Return router](return-router.md) | Detail the merged-PR return path covered more broadly by Return and review |
| [Intake server](intake-server.md) | Detail webhook receipt and normalization covered more broadly by Intake and control plane |
| [Replay](replay.md) | Re-run selected persisted return or dispatch operations |
| [Decision loop](decision-loop.md) | Restored historical detail for the secondary decision path |

## Operating boundary

The runtime owns events, jobs, queue records, executor sessions, results, evaluation receipts, and provisional scheduling evidence. It does not own final graph truth. An executor result or evaluator pass may place a node in `provisional`, but only a human changes a node to `complete`.

Production heartbeat processes on armed hosts must be started through `deploy/mini-heartbeat/bin/`, which loads the required environment through `deploy/mini-heartbeat/bin/common.sh`. Do not invoke `scripts/runtime/heartbeat/runner.py` directly on an armed host. Deployment topology is documented in [Deployment](../deployment/index.md).
