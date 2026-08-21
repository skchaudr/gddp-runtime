# Entity: Graph

The **graph** is the directed acyclic graph (DAG) of nodes representing the complete project intent, stored in `gddp-config/graphs/<project>/`.

---

## Authority & Integrity Invariants

- **Human-Only Acceptance:** Only a human operator modifies graph truth (accept, revise, split, supersede, rewire, defer, or abandon). No automated agent or runner can mark a node accepted.
- **DAG Integrity:** Dependency edges strictly govern frontier eligibility. Ready nodes with satisfied dependencies enter the dispatch frontier.
- **Distinction of Edges:** Dependency edges govern execution order; evidence links tie runs, receipts, and verdicts to nodes without mutating graph topology.
- **Separation of Concerns:** Runtime job tracking (`jobs_status.py`, `db/queue.db`) tracks executor state and queue lifecycle, but is strictly prohibited from modifying graph node status.

---

## Entity Map

| Aspect | Location / Reference |
|---|---|
| **Core Doctrine** | [`AGENTS.md`](../AGENTS.md) · [`docs/decisions/Tests-can-fail-nodes-can-pass.md`](../docs/decisions/Tests-can-fail-nodes-can-pass.md) · [`docs/decisions/GDDP-becomes-small-and-real.md`](../docs/decisions/GDDP-becomes-small-and-real.md) |
| **Operating Loop Step** | Step 1 (Packet) & Step 5 (Human Review) in [`docs/proposals/LOOP.md`](../docs/proposals/LOOP.md) |
| **Graph Delivery & Updating** | [`scripts/runtime/graph_delivery.py`](../scripts/runtime/graph_delivery.py) · [`scripts/runtime/graph_updater.py`](../scripts/runtime/graph_updater.py) |
| **Operator Browse CLI** | `gddp node browse --project <p>` in `gddp-config` |
| **Node Status Tracking** | [`scripts/node_status_history.py`](../scripts/node_status_history.py) · [`node_status_history/`](../node_status_history/) |
| **Proposals Ledger** | `gddp-config/proposals/` |
