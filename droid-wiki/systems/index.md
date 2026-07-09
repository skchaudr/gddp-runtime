# Systems

GDDP Runtime is built from a small set of cooperating subsystems, each with a single responsibility. The heartbeat drives forward dispatch; the return router handles receipts from merged PRs; the executor adapters translate job packets into a specific agent's wire format; the decision loop adds an event-driven reasoning layer on top; and the graph reader turns `gddp-config` YAML into in-memory graph state. The pages below cover each one in depth. For how they fit together, see [overview/architecture.md](../overview/architecture.md); for running them on a host, see [deployment](../deployment.md).

## System pages

- [Heartbeat](heartbeat.md) — graph-driven dispatch loop that claims events, classifies them, scope-checks, and dispatches jobs to executors in parallel worker threads.
- [Return router](return-router.md) — converts merged PRs into structured review receipts and routes them through verification.
- [Executor adapters](executor-adapters.md) — translate runtime job packets into a specific executor's wire format (Jules today, agent-agnostic by design).
- [Decision loop](decision-loop.md) — event-driven reasoning layer that cleans stale state and decides verify / dispatch / escalate / no-op on each wake.
- [Graph reader](graph-reader.md) — reads `gddp-config` YAML into `NodeData` and `ProjectGraph` objects, resolving config path by arg > env > sibling dir.

## Related

- [Features](../features/index.md)
- [Deployment](../deployment.md)
