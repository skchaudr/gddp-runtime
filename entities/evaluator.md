# Entity: Evaluator

The **evaluator** is the semi-automated (always on ideally, runs as soon a node's job is completed) *verification system* designed to protect user intent and project integrity. It executes a two-lane verification pass on returned work and emits a structured verdict receipt.

---

## Authority & Epistemic Boundaries

- **Evidence Only:** Evaluator verdicts are strictly **evidence** for human review. Evaluator output is never graph truth.
- **Worst-of Combination:** The evaluator runs deterministic + semantic criteria checks alongside intent/integrity checks, combining results using worst-of logic.
- **Retry Triggering:** Evaluator findings route to the node retry fix-list ONLY if backed by cited, concrete repo paths or canonical node IDs. Findings without evidence route to human review.
- **Graph Modification Prohibited:** The evaluator never modifies the graph DAG or marks nodes accepted. Only human operators modify graph truth.

---

## Entity Map

| Aspect | Location / Reference |
|---|---|
| **Core Invariants** | [`AGENTS.md`](../AGENTS.md) · [`docs/invariants/invariants.md`](../docs/invariants/invariants.md) · [`docs/decisions/Tests-can-fail-nodes-can-pass.md`](../docs/decisions/Tests-can-fail-nodes-can-pass.md) |
| **Operating Loop Step** | Step 4 (Evaluate) in [`docs/proposals/LOOP.md`](../docs/proposals/LOOP.md) |
| **Verification Engine** | [`scripts/runtime/verification/`](../scripts/runtime/verification/) · [`scripts/runtime/decision_loop/`](../scripts/runtime/decision_loop/) |
| **CLI & Export Tools** | [`scripts/export_evaluations.py`](../scripts/export_evaluations.py) · [`scripts/test_jobs_status_evaluator.py`](../scripts/test_jobs_status_evaluator.py) |
| **Receipt Output Target** | `gddp-config/verification/<project>/` · [`node_status_history/`](../node_status_history/) |
| **Decisions & Evolution** | [`docs/decisions/`](../docs/decisions/) · [`.handoffs/012-semantic-verifier-typed-verdict.md`](../.handoffs/012-semantic-verifier-typed-verdict.md) |
