# Entity: Receipt

A **receipt** is an immutable, structured evidence artifact produced by an executor return or an evaluator verification run.

---

## Authority & Storage Principles

- **Files are Truth:** Receipts persist as durable files (`GDDP_RECEIPTS_PATH` or `gddp-config/verification/<project>/`). The SQLite database (`db/queue.db`) is a rebuildable index over these files.
- **Evidence vs Truth:** A receipt proves that an execution or evaluation pass occurred and records its artifacts/diffs/findings. A positive receipt does not equate to graph acceptance.
- **Provisional Status Constraint:** A `provisional` node status label without a backing verdict receipt is unevidenced and invalid.

---

## Entity Map

| Aspect | Location / Reference |
|---|---|
| **Operating Loop Step** | Step 3 (Return) & Step 4 (Evaluate) in [`docs/proposals/LOOP.md`](../docs/proposals/LOOP.md) |
| **Receipt CLI & Generator** | [`scripts/gddp_node_receipt.py`](../scripts/gddp_node_receipt.py) · [`scripts/test_gddp_node_receipt.py`](../scripts/test_gddp_node_receipt.py) |
| **Results Store Runtime** | [`scripts/runtime/results_store.py`](../scripts/runtime/results_store.py) |
| **Status History Evidence** | [`node_status_history/`](../node_status_history/) · [`scripts/node_status_history.py`](../scripts/node_status_history.py) |
| **Handoffs & Milestones** | [`.handoffs/018-runtime-receipt-proves-node.md`](../.handoffs/018-runtime-receipt-proves-node.md) · [`.handoffs/071-gddp-node-receipt-cli.md`](../.handoffs/071-gddp-node-receipt-cli.md) |
