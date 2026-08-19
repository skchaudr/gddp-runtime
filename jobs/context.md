# jobs/context.md — Runtime Execution State Map

This directory holds local runtime job workspaces, prompt packets, logs, and executor intermediate outputs.

---

## 1. Job Lifecycle & Folder State

When a node is claimed and dispatched, an execution workspace is provisioned under `jobs/<job_id>/`:

- **Active:** Job session is currently executing in its allocated worktree.
- **Completed:** Execution finished, receipt files emitted, queued for evaluation.
- **Failed:** Execution encountered a runtime error, timeout, or crash.
- **Abandoned:** Operator cancelled or replaced the session.

---

## 2. Invariants

1. **Ephemeral Runtime Data:** All subdirectories and job artifacts in `jobs/` are local runtime state and must never be committed to git.
2. **Index vs Truth:** `db/queue.db` indexes active/completed job status, but durable receipts land in designated receipts paths.
3. **No Direct Node Status Mutation:** Job completion in `jobs/` updates job queue records in SQLite, never graph truth in `gddp-config`.
