# node_status_history/context.md — Historical Evidence Map

This directory contains durable, append-only JSONL history records of human operator decisions and node status transitions across projects.

---

## 1. Schema & Semantics

Each file in `<project>/<node_id>.jsonl` contains immutable transition records formatted as:

```json
{
  "ts": "2026-08-07T22:41:31.170044+00:00",
  "project_id": "gate-live-test",
  "node_id": "node-01-gate-smoke",
  "from_status": "provisional",
  "to_status": "deferred",
  "reason": "Operator reasoning string",
  "kind": "graph",
  "source": "gddp operator menu"
}
```

---

## 2. Invariants

1. **Append-Only Evidence:** Historical transition entries are durable evidence of past operator decisions. Never overwrite or delete historical lines.
2. **Managed via Tooling:** Transitions are recorded via [`scripts/node_status_history.py`](../scripts/node_status_history.py) during operator actions (`gddp node browse`).
3. **Evidence, Not Live Status:** Current graph status lives in `gddp-config/graphs/<project>/nodes/*.yaml`. This directory provides the audit trail explaining why status changed.
