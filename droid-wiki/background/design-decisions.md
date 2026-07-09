# Design decisions

GDDP Runtime's architecture is the result of specific choices made for specific reasons. This page documents the key decisions and the trade-offs behind them. The unifying theme: the runtime is an intent-preservation and graph-integrity layer, not an executor and not an agent harness. Each decision below serves that boundary.

## 1. Two-repo split: config truth vs. execution machinery

`gddp-config` holds project truth as declarative YAML: schemas, project graphs, nodes, constraints, acceptance criteria. `gddp-runtime` holds the execution machinery: heartbeat runner, executor adapters, webhook intake, SQLite state, receipt handling, verification, decision loop.

The split exists so that graph truth and execution code can evolve independently and so the runtime can never silently rewrite the graph. The runtime reads config. It never writes it. Graph state moves only through human-merged PRs against `gddp-config`. If the runtime had a bug and tried to advance a node, it would have to open a PR and a human would have to merge it, which is the point.

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

Dispatch goes through an adapter interface. `scripts/adapters/jules_action_adapter.py` is the live adapter today, dispatching to Jules via GitHub issues. The adapter pattern means new adapters for Codex, Vertex, local harnesses, or custom executors can plug in behind the same dispatch contract without touching the heartbeat, scope checker, or job factory.

The runtime does not know or care what executor is doing the work. It builds a job packet, hands it to an adapter, and waits for a receipt. Executors are interchangeable because the contract is narrow.

## 7. SQLite over Postgres

The runtime uses SQLite for all state: `events`, `jobs`, `queue_records`, `results`, `artifact_verifications`, `decision_results`. Six tables, one file, no server.

This is a single-host system running on a Raspberry Pi. SQLite is embedded, has zero operational overhead, and produces a single replayable file. Postgres would add a process to manage, a connection pool to tune, and a failure mode that does not exist with a file-based database. The trade-off is concurrency limits, but the heartbeat uses atomic SQLite claims to handle concurrent runs, and the workload is small enough that SQLite's limits are not the bottleneck.

## 8. Cron heartbeat instead of an always-on process

The heartbeat runs every 5 minutes via user crontab, not as a long-running daemon. Each tick wakes, reads the graph, finds ready nodes, classifies events, dispatches jobs, records outcomes, and exits.

An always-on process would need to manage its own lifecycle, handle restarts, deal with event loops, and stay healthy indefinitely. A cron tick is stateless between runs: if the Pi reboots, the next tick picks up where the last one left off. If a tick crashes, the one after it recovers. The 5-minute interval is short enough for near-real-time response and long enough to avoid stepping on itself. The intake server is the only always-on component, and it is a thin Flask listener behind systemd's `Restart=always`.

## 9. graph_updater.py as evidence PR opener

`scripts/runtime/graph_updater.py` opens evidence-packaged PRs against `gddp-config` proposing to mark nodes complete. It never pushes directly. The PR body contains the full evidence packet (source PR reference, acceptance criteria verdicts, scope verification, test status, review metadata) so the human can rubber-stamp or scrutinize.

This replaced an earlier design where `graph_updater.py` was a disabled stub. The stub existed because the original instinct was to have the runtime write graph truth directly, and that instinct was wrong. The evidence PR model preserves the invariant (runtime never mutates graph truth) while still giving the human a packaged proposal to review instead of requiring them to assemble the evidence themselves. It aligns with GitOps patterns: git is source of truth, machines propose, humans approve.

## Related pages

- [Architecture](../overview/architecture.md)
- [Doctrine](doctrine.md)
- [Patterns and conventions](../how-to-contribute/patterns-and-conventions.md)
- [Getting started](../overview/getting-started.md)
