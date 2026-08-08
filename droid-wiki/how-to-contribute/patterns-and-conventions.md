# Patterns and conventions

Conventions that keep GDDP Runtime coherent: graph truth stays outside this repo, evidence is durable, and new machinery must not compensate for unexamined assumptions.

## Hard boundaries

1. **Human-only completion.** Executors, evaluators, and runtime jobs never set graph node status to `complete`. Write receipts and `awaiting_review` / `provisional` signals instead.
2. **`jobs_status` is runtime-only.** [`scripts/jobs_status.py`](../../scripts/jobs_status.py) may update job/queue state and must never update graph/node status in `gddp-config`.
3. **Heartbeat entrypoint.** On armed hosts, use [`deploy/mini-heartbeat/bin/`](../../deploy/mini-heartbeat/bin/) (`arm.sh`, `smoke.sh`). Do not call `python -m scripts.runtime.heartbeat.runner` as the operator path; missing env creates failed jobs before any executor launches.
4. **Explicit node tags.** Classification requires `node: <id>` (or equivalent explicit routing). Do not invent fallback node guesses.
5. **Config repo is read-only from runtime.** Graph YAML is loaded through `GraphReader`; automatic writeback of acceptance is frozen out of the return path.

## Anti-pattern called out in AGENTS.md

A recurring failure mode in this project:

1. Assume a behavior exists.
2. Design around the assumption without verifying.
3. System fails because the assumption was false.
4. Invent workaround machinery that becomes architecture.

Before adding a layer, establish what missing invariant it compensates for. Prefer deleting a mechanism to guarding a broken one. Architecture here is challengeable when evidence shows it rests on a false assumption.

## Evidence over ceremony

- **Tests are evidence, not graph truth.** An accepted node can still have failing implementation tests; a green suite does not complete a node. See [`docs/Tests-can-fail-nodes-can-pass.md`](../../docs/Tests-can-fail-nodes-can-pass.md).
- **Evaluator verdicts are evidence.** The evaluator is the second-to-last gate. Humans are last.
- **Retry requires citations.** Evaluator-triggered retries need a concrete repo path (optionally `:line`), graph node id, or canonical document. Vague findings go to human review, never to work.
- **Same node on retry.** Retry re-attempts the unchanged node with a fix-list injected. Out-of-scope discovery becomes a continuation proposal for the human, not silent scope expansion. Agents never author nodes into the live graph.

## Module and packet conventions

- **One executor-neutral packet.** Use `NodePacket` from [`scripts/adapters/executor_protocol.py`](../../scripts/adapters/executor_protocol.py). Nested values are deep-frozen; serialization is deterministic.
- **Adapters are transports.** Add a new executor by implementing the adapter protocol; do not fork the heartbeat for a new brand of agent.
- **Coordinator owns SQLite writes.** Heartbeat worker threads return outcomes; they do not share the coordinator connection. Reservations happen under `BEGIN IMMEDIATE` before external launch.
- **Direct vs mediated returns.** Prefer direct commit-ref collect for short round trips. Keep Jules/PR mediation as inherited infrastructure, not the required bus.
- **Mission 1:1 mapping.** Factory mission projection requires exactly one feature per demanded node ID and order. Drift parks the engagement for review.

## Python style (observed)

- Stdlib-first scripts under `scripts/` with pytest modules living beside the code (`test_*.py`).
- Type-oriented contracts via dataclasses / Pydantic models in verification and protocol modules.
- No repo-wide formatter or linter is configured; match neighboring file style.
- Tests use temp DB paths and fixtures; avoid depending on production `db/queue.db`.

## Logging and failure

- Prefer durable on-disk artifacts (spool `exit.json`, mission push audit, receipt JSONL) over ephemeral stdout alone.
- Unknown or conflicting completion evidence should **quarantine**, not overwrite or invent success.
- Transient polling failures stay non-terminal; do not convert “unknown” into pass.
- Gate token write failures are non-fatal; handle conservatively on the admission side.

## Documentation and handoffs

- Session work that changes repo state should leave a numbered handoff under `.handoffs/` using the template pattern.
- Co-author commits with agent identity when an agent authors the change (project requirement in AGENTS.md).
- Canonical operator-facing narrative lives in `README.md`, `PROJECT-BRIEF.md`, and doctrine docs under `docs/`. Generated wikis and handoffs are reference, not canon.
- Evaluator context deliberately excludes `AGENTS.md` (executor-facing). Integrity/criteria lanes read README, project brief, foundational node, and DAG neighbors.

## Naming

| Prefer | Avoid |
| --- | --- |
| node / graph truth | “task done because PR merged” |
| evidence / receipt | “auto-accepted” |
| provisional | “soft-complete” as graph truth |
| execution attempt | anonymous “run” without attempt id |
| engagement | treating multi-node mission as one graph node |

## Related

- [Doctrine](../background/doctrine.md)
- [Development workflow](development-workflow.md)
- [Testing](testing.md)
- [Architecture](../overview/architecture.md)
