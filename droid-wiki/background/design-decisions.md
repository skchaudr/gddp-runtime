# Design decisions

> Restored from the 2026-07-13 wiki. This is historical rationale, not an operational specification. Corrections below name current behavior where the old rationale became false.

GDDP Runtime's architecture is the result of specific choices made for specific reasons. This page documents the key decisions and the trade-offs behind them. The unifying theme: the runtime is an intent-preservation and graph-integrity layer, not an executor and not an agent harness. Each decision below serves that boundary.

## 1. Two-repo split: config truth vs. execution machinery

`gddp-config` holds project truth as declarative YAML: schemas, project graphs, nodes, constraints, acceptance criteria. `gddp-runtime` holds the execution machinery: heartbeat runner, executor adapters, webhook intake, SQLite state, receipt handling, verification, decision loop.

The split keeps human acceptance separate from execution. Current runtime code does write scheduler-visible `provisional` and `ready` statuses into config YAML when a project opts into frontier advancement. It never writes `complete`; only the human does that. The older claim that runtime never writes config at all is no longer true.

## 2. Receipt-based return instead of auto-advancement

When an executor's PR merges, the runtime does not update the graph. It creates a structured receipt in the `results` table with a verification verdict and routes the job to `awaiting_review`. A human then decides whether graph truth changes.

Auto-advancement was the obvious shortcut and it was deliberately not taken. The reasoning: a decision-loop bug or a deceptive executor return should not be able to corrupt the graph. Worst case with receipts is a bad receipt that the reviewer declines. The receipt model also makes the review step a 3-second rubber stamp when the verdict is clean, so it does not slow down momentum when nothing is wrong.

## 3. Two-lane evaluator: criteria + integrity

The evaluator has two lanes that run independently:

- **Lane 1 (criteria):** Deterministic probes check acceptance criteria using regex, file existence, command execution, and tier configuration. Indeterminate criteria escalate to a semantic LLM agent that investigates the repo with read-only tools. A 12-row decision matrix combines deterministic and semantic results into a criteria verdict.
- **Lane 2 (integrity):** A fresh-eyes drift review that asks whether the work preserves the node's intended role in the project graph. This is the lane that catches a node that passes its local tests but damages the project's shape.

The criteria lane answers "did the expected mechanical thing happen?" The integrity lane answers "does this still mean what the project meant?" Both questions matter. Neither is sufficient alone.

## 4. Worst-of verdict combination

The integrity combiner takes the worst-of the two lanes. Integrity can only worsen the criteria verdict, never upgrade it. A pass on criteria stays pass only if integrity also passes. Any integrity failure (drift, contradicted, block) floors the verdict at needs-human-review.

This is conservative by design. The system's purpose is to prevent drift, so the evaluator should err toward flagging rather than toward green-lighting. If integrity says the work damaged the project, a clean criteria result does not override that.

## 5. Subprocess isolation for verification

The verification bridge runs the evaluator as a subprocess so a crash, hang, or timeout in the evaluator cannot take down the return router. The bridge retries once on transient failures.

Verification deals with LLM agents, network calls, and arbitrary code execution for test runs. All of those can fail in ways that are hard to predict. Isolating the evaluator behind a subprocess boundary means the return path stays reliable even when the evaluator does not.

## 6. Executor-agnostic adapter pattern

Dispatch goes through the executor-neutral contract in `scripts/adapters/executor_protocol.py`. Current adapters include Jules transports, local subprocess/Droid execution, and the live `factory_mission` engagement adapter. New executors can plug in behind the same node-packet, session, and result contracts without taking ownership of graph truth.

The runtime does not know or care what executor is doing the work. It builds a job packet, hands it to an adapter, and waits for a receipt. Executors are interchangeable because the contract is narrow.

## 7. SQLite over Postgres

The runtime uses SQLite for execution state: `events`, `jobs`, `queue_records`, `results`, `artifact_verifications`, `decision_results`, and `executor_sessions`. Seven tables, one file, no server.

This is a single-host system running on a Raspberry Pi. SQLite is embedded, has zero operational overhead, and produces a single replayable file. Postgres would add a process to manage, a connection pool to tune, and a failure mode that does not exist with a file-based database. The trade-off is concurrency limits, but the heartbeat uses atomic SQLite claims to handle concurrent runs, and the workload is small enough that SQLite's limits are not the bottleneck.

## 8. Periodic heartbeat instead of an always-on scheduler

The heartbeat is a short-lived periodic process, not a long-running scheduler. Production on `sab-mini` launches it through the `deploy/mini-heartbeat` launchd kit; Linux mini-heartbeat hosts use systemd user units. Each tick wakes, reads the graph, reconciles sessions, advances the eligible frontier, dispatches bounded attempts, records outcomes, and exits.

An always-on scheduler would need to manage its own lifecycle, restarts, event loops, and indefinite health. Short ticks recover from durable SQLite and executor-session state. On armed hosts, agents must use `deploy/mini-heartbeat/bin/` entrypoints so the required environment and spool configuration are loaded; direct runner invocation is unsafe.

## 9. graph_updater.py is inactive legacy code

`scripts/runtime/graph_updater.py` still contains an evidence-PR implementation, including branch mutation and a force-push. The live return path does not call it. Its only non-test caller is the untriggered legacy decision-loop power.

Treat it as historical implementation evidence, not the supported graph-update path. Current return handling creates receipts and review state; it does not invoke `graph_updater.py`.

## Related pages

- [Architecture](../overview/architecture.md)
- [Doctrine](doctrine.md)
- [Patterns and conventions](../how-to-contribute/patterns-and-conventions.md)
- [Getting started](../overview/getting-started.md)
