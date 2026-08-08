# Features

Active contributors: Saboor

GDDP Runtime preserves forward agentic momentum without transferring graph authority away from the human operator. Its features turn explicit node intent into bounded execution, durable evidence, evaluation, and review.

## Execution features

- [Explicit node routing](explicit-node-routing.md) requires a `node: <id>` tag before public intake can spend executor capacity.
- [Parallel dispatch](parallel-dispatch.md) reserves work transactionally, enforces project capacity, and launches independent work concurrently.
- [Provisional status and frontier advance](provisional-and-frontier.md) let evaluated work unblock dependents without claiming human acceptance.
- [Mission engagements](mission-engagements.md) batch compatible nodes into Factory mission runs while preserving one result per node.

## Evidence and decision features

- [Evaluation pipeline](evaluation-pipeline.md) evaluates a pinned commit through criteria and integrity lanes and records context coverage.
- [Retries](retries.md) distinguish corrective work attempts from executor-plumbing replacement and require actionable evidence.
- [Human review](human-review.md) exposes `awaiting_review` evidence while keeping runtime job state separate from graph truth.

## Restored finer-grained and historical pages

- [Receipt-based return](receipt-based-return.md) details the merged-PR receipt flow covered more broadly by [Return and review](../systems/return-and-review.md).
- [Retry loop](retry-loop.md) details the mediated evaluator retry path covered more broadly by [Retries](retries.md).
- [Natural guard](natural-guard.md) records a peripheral historical agent-harness feature that is not active runtime source.

## Feature boundaries

These features share four rules:

1. A node is the unit of project intent.
2. Jobs, attempts, commits, receipts, and verdicts are evidence about a node, not graph truth.
3. `provisional` may advance scheduling, but only a human may mark a node `complete`.
4. Executors are replaceable transports behind the same node packet and result contracts.

For the full control flow, see [Architecture](../overview/architecture.md), [Heartbeat](../systems/heartbeat.md), [Verification](../systems/verification.md), and [Node and graph truth](../primitives/node-and-graph.md).
