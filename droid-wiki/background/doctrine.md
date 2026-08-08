# Doctrine

GDDP is an intent-preservation and graph-integrity layer around agentic work. It is not the executor or the agent harness. Active contributor: Saboor.

## Four kinds of truth

1. **Canon** states the invariants and architectural boundaries that must remain true.
2. **Graph** states the human-authored work, dependencies, and current frontier.
3. **Evidence** records attempts: jobs, sessions, commits, tests, artifacts, traces, and evaluator verdicts.
4. **Human acceptance** decides whether evidence is sufficient to change canonical graph truth.

Confusing these categories causes most architectural drift. A job is not a node. A passing test is not acceptance. An evaluator pass is not completion.

## Ten operating invariants

1. The node is the unit of project intent; jobs and sessions are attempts to satisfy it.
2. Only a human marks a node `complete`.
3. Tests, criteria, receipts, and verdicts remain evidence rather than graph truth.
4. Runtime job and queue mutations never silently mutate graph/node completion.
5. Every executor uses the same neutral node packet and returned-result boundary.
6. Executors and transports are replaceable; no executor owns graph truth.
7. Durable, attributable evidence must return before evaluation.
8. The evaluator renders criteria and intent/integrity judgments and must not be blocked merely to protect merge purity.
9. Dependency edges sequence work; evidence links explain it but do not become DAG dependencies.
10. Infrastructure must improve node turnaround, concurrency, recovery, observability, or integrity and remain subordinate to moving real nodes.

## Evaluator boundary

The evaluator asks two questions: did the attempt satisfy the node's criteria, and did it preserve user intent, project canon, and structural integrity? The worst lane shapes the verdict. The evaluator reads graph and canonical context rather than adopting executor instructions as truth.

The evaluator is the second-to-last gate. It emits evidence for review and never writes `complete`. A local implementation can pass tests while violating the project contract; it can also have failing tests while preserving accepted graph progress. The human weighs both.

## Provisional flow

`provisional` separates “may downstream execution continue?” from “has the project accepted this node?” A qualifying evaluator pass can open dependents while human review trails. A node with `human_gate: true` opts out and blocks at review. `complete` remains human-only.

Provisional work compounds risk by design. Base-chaining ensures a dependent actually builds on its one provisional predecessor's result. Rejection can return the predecessor to `ready`, freezing its downstream frontier. Provisional is scheduler-visible evidence, not final truth.

## The AGENTS anti-pattern

The repository's standing warning is empirical: an agent assumes a behavior, designs around it without verification, the assumption fails, and another workaround is added until the workaround is treated as architecture. The correction is not “add a safer layer.” Verify the premise, identify what the layer compensates for, and prefer removing a false mechanism to guarding it.

`AGENTS.md` is executor canon and is deliberately excluded from evaluator context. It tells workers how to behave; the graph and canonical project documents tell evaluators what must remain true.

Sources: `/Users/sab-mini/repos/gddp-runtime/PROJECT-BRIEF.md`, `/Users/sab-mini/repos/gddp-runtime/docs/Tests-can-fail-nodes-can-pass.md`, and `/Users/sab-mini/repos/gddp-runtime/docs/GDDP-becomes-small-and-real.md`.
