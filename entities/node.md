# Entity: Node

The **node** is the fundamental atomic unit of project intent. It defines the discrete goal, constraints, and deterministic/semantic acceptance criteria for a single unit of work.

---

## Lifecycle & Invariants

- **State Progression:** `proposed` → `ready` → `running` → `evaluated` → `accepted` / `rejected` / `deferred` / `superseded`.
- **Proposal Semantics:** Every node is a human-owned proposal, not a commitment. Acceptance is never assumed.
- **Retry Semantics:** Retries re-attempt the identical node unchanged. Verified evaluator findings are injected strictly as the retry's fix-list; what is attempted does not change.
- **Out-of-Scope Work:** Discovered work beyond node scope becomes a *continuation proposal* (YAML in proposals ledger), invisible to the frontier until human-promoted.

---

## Entity Map

| Aspect | Location / Reference |
|---|---|
| **Core Doctrine** | [`AGENTS.md`](../AGENTS.md) · [`docs/Tests-can-fail-nodes-can-pass.md`](../docs/Tests-can-fail-nodes-can-pass.md) |
| **Operating Loop Step** | Step 1 (Packet), Step 2 (Dispatch), Step 5 (Human Review) in [`docs/proposals/LOOP.md`](../docs/proposals/LOOP.md) |
| **Status History Records** | [`node_status_history/`](../node_status_history/) · [`scripts/node_status_history.py`](../scripts/node_status_history.py) |
| **Receipt Generation** | [`scripts/gddp_node_receipt.py`](../scripts/gddp_node_receipt.py) |
| **Decision Records** | [`docs/decisions/Thin-Graph-Rich-Project.md`](../docs/decisions/Thin-Graph-Rich-Project.md) |
| **Active Watch/Steer** | `gddp watch <node>`, `gddp steer <node> <msg>` |
