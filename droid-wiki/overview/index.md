# GDDP Runtime overview

GDDP Runtime is the execution machinery for Graph-Driven Development: a control plane that dispatches bounded work from a human-owned project graph, collects durable evidence from replaceable executors, evaluates that evidence, and stops at human review. It never silently advances graph truth.

## What this repository is

`gddp-runtime` is one half of a two-repo split:

| Repository | Owns |
| --- | --- |
| **gddp-config** | Human-owned project truth: schemas, graphs, nodes, constraints, acceptance criteria |
| **gddp-runtime** | Heartbeat, intake, executor adapters, SQLite state, evaluator, operator tooling |

The human operator declares **what** work exists. Agents and executors determine **how**. Runtime observes attempts, produces structured receipts, and presents review decisions. Only a human moves a node to `complete`.

## Who uses it

- **Operators** who run the control plane on hosts such as `sab-mini`, arm/disarm heartbeat and intake, and accept or reject review candidates in `gddp-config`.
- **Agents and developers** who change runtime machinery (adapters, heartbeat, evaluator) while preserving the boundary that graph truth stays outside this repo.
- **Executor workers** (Jules, Droid, local subprocess, Factory mission) that receive a neutral `NodePacket` and return patches or commit refs.

## Core loop

```text
ready node + explicit event
  → heartbeat claims, scopes, reserves
  → executor adapter dispatches
  → durable session / commit evidence returns
  → two-lane evaluator (criteria + integrity)
  → awaiting_review (+ optional provisional)
  → human accept / retry / block / defer
```

Nothing in that path writes completion into `gddp-config`. Evaluators produce evidence. Humans produce graph truth.

## Major surfaces

| Surface | Where | Role |
| --- | --- | --- |
| Heartbeat | [`scripts/runtime/heartbeat/`](../../scripts/runtime/heartbeat/) | Canonical scheduler: reconcile, frontier, plan, dispatch, finalize |
| Intake | [`scripts/intake_server.py`](../../scripts/intake_server.py) | GitHub webhook normalization into SQLite events |
| Adapters | [`scripts/adapters/`](../../scripts/adapters/) | Jules, local subprocess/Droid, Factory mission |
| Evaluator | [`scripts/runtime/verification/`](../../scripts/runtime/verification/) | Deterministic criteria floor + semantic + integrity lanes |
| Operator backend | [`scripts/jobs_status.py`](../../scripts/jobs_status.py) | Runtime job reads/writes; never graph/node status |
| Deploy kits | [`deploy/mini-heartbeat/`](../../deploy/mini-heartbeat/), [`deploy/rig1-heartbeat/`](../../deploy/rig1-heartbeat/) | launchd/systemd arm/smoke/disarm |

## Quick links

- [Architecture](architecture.md) — component map and data flows
- [Getting started](getting-started.md) — install, DB, tests, local heartbeat
- [Glossary](glossary.md) — node, provisional, NodePacket, VerdictReceipt, and more
- [Heartbeat](../systems/heartbeat.md) — tick lifecycle
- [Factory mission](../systems/factory-mission.md) — multi-node engagements
- [Deployment](../deployment/index.md) — topology and mini-heartbeat kit
- [Doctrine background](../background/doctrine.md) — invariants and four kinds of truth

## Status snapshot

- Language: Python 3.11+ (stdlib + Flask, PyYAML, Pydantic; semantic lane may use Anthropic)
- Persistence: SQLite WAL under `db/` (runtime state, not committed)
- Graph truth: external `gddp-config` checkout via `GDDP_CONFIG_PATH`
- Production control plane: `sab-mini` (macOS launchd); Linux hosts use the mini-heartbeat systemd units
- Known boundary: evaluator and runtime never complete nodes; mission-mode Factory adapter is live with residual push-bypass detection

## Related wiki sections

- [Systems](../systems/index.md) — internal building blocks
- [Features](../features/index.md) — cross-cutting capabilities
- [Primitives](../primitives/index.md) — domain objects that show up everywhere
- [How to contribute](../how-to-contribute/index.md) — workflow, tests, conventions
