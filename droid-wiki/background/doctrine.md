# Doctrine

GDDP Runtime is built on a doctrine about what graph truth means, who owns it, and what role the evaluator plays. The doctrine is documented in two source files and referenced across the codebase. This page consolidates it.

## The core invariant

From `docs/Tests-can-fail-nodes-can-pass.md`:

> Node status must reflect accepted graph progress, not temporary implementation perfection.

This is the sentence that separates GDDP from a test runner. A node is not a claim that the code is perfect. A node is a claim that a bounded unit of intent has been accepted into the graph with evidence. A completed node can still leave known bugs, limitations, or follow-up nodes. That is normal project development, not corruption.

The corrupt thing would be pretending the node means something it does not mean.

## What is evidence, what is truth

Four things are evidence, not graph truth:

1. **Tests are evidence, not graph truth.** A project can have failing tests and still be moving in the correct direction. A project can have passing tests and still be architecturally wrong.
2. **Criteria are evidence, not graph truth.** A node can satisfy every local acceptance criterion and still violate the graph.
3. **Evaluator verdicts are evidence, not graph truth.** The evaluator produces structured verdicts and evidence. Those are inputs to a human decision, not the decision itself.
4. **Only human-accepted node status is graph truth.** The human operator is the final authority. No node becomes complete without human acceptance of evidence.

The practical consequence for agents working in this system:

> Do not reinterpret a failing implementation test as proof that an accepted node is false. A failing test may create a bug node, regression node, or follow-up node. It does not automatically invalidate accepted graph progress.

This is the anti-pattern that the doctrine explicitly resists: "tests fail, therefore the node status is suspicious, therefore the node is not real." That reasoning collapses graph truth into test results, which is exactly what GDDP is designed to prevent.

## GDDP is the intent-preservation layer

From `docs/GDDP-becomes-small-and-real.md`:

> GDDP is not the executor.
> GDDP is not the agent harness.
> GDDP is the intent-preservation and graph-integrity layer around work.

The system does not rebuild the dispatch loop, the executor protocol, or the agent runtime. Those already exist and are battle-tested. GDDP adds three things on top:

1. **Graph-aware packet meaning** — nodes are positioned in a DAG with dependencies, not just a flat queue.
2. **Canonical intent context** — the evaluator reads project truth (README, PROJECT-BRIEF, foundational node, DAG neighbors) to judge whether work preserves intent, not just whether it passes criteria.
3. **Human completion gate** — only the human operator moves node state. The evaluator recommends. The operator decides. The graph records.

The clean stack:

| Layer | Role |
|---|---|
| `gddp-config` | Project intent, DAG, node contracts |
| Dispatch loop / heartbeat | Packet routing, executor invocation, artifacts |
| Executor | Claude, Jules, Codex, human, or whatever does the work |
| GDDP evaluator | Semantic verifier against canonical docs and DAG neighborhood |
| Human | Final authority who moves node state |

## The evaluator's actual question

The evaluator does not ask "does the code pass tests?" It asks:

> Does this change preserve the intended role of this node inside the project graph?

A node can satisfy its acceptance criteria and still be wrong because it may:

- Solve the wrong layer
- Collapse a future abstraction
- Violate an upstream design decision
- Duplicate responsibility owned by another node
- Change the project's direction without authorization
- Make a local fix that creates graph-level drift
- Pass tests while weakening the project contract

That is why the evaluator reads the DAG neighborhood. A node can pass its local tests and still damage the project's shape. The graph neighborhood is how you catch that.

## Canon documents and their audiences

Four documents are canon (human-owned, small, and authoritative when prose and code disagree), in order:

1. The project's **foundational node** (first node in `project.yaml`, node order is semantically meaningful)
2. `README.md`
3. `PROJECT-BRIEF.md`
4. `AGENTS.md`

Canon wins over any other prose when they disagree. Generated artifacts (wikis, receipts, handoffs) capture canon but are never canon themselves.

### Audiences matter

`AGENTS.md` is executor-canon. It tells the worker how to behave in the repo. The evaluator is deliberately excluded from reading it. The evaluator should not inherit the executor's framing. The evaluator needs the project's source of truth, not the executor's operating instructions.

The evaluator's context is:

- README
- PROJECT-BRIEF
- Foundational node
- Current node
- DAG neighbors (upstream, downstream, related)
- Deterministic evidence

This separation of concerns is the drift-prevention boundary:

- **Executor asks:** "What do I need to do?"
- **Evaluator asks:** "Does what was done still preserve the project's intended meaning?"

## The safety valve

The "only the human moves a node to complete" rule is not just a control preference. It is the architectural safety valve. It prevents the system from becoming self-certifying. The executor cannot complete itself. The evaluator cannot complete it either. The evaluator can only produce a structured verdict and evidence. No node becomes complete without human acceptance.

This is simple, enforceable, and hard to accidentally overcomplicate.

## Source documents

- `docs/Tests-can-fail-nodes-can-pass.md` — the core invariant and the evidence-vs-truth doctrine.
- `docs/GDDP-becomes-small-and-real.md` — the architectural boundary: GDDP constrains, interprets, and verifies the loop. It does not rebuild it.
- `PROJECT-BRIEF.md` — canon list, vocabulary doctrine, and the system narrative.
- `AGENTS.md` — executor-canon, session contracts, mutation boundaries.

## Related pages

- [Design decisions](design-decisions.md)
- [Architecture](../overview/architecture.md)
- [Glossary](../overview/glossary.md)
- [Patterns and conventions](../how-to-contribute/patterns-and-conventions.md)
