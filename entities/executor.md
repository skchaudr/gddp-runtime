# Entity: Executor

The **executor** is the worker environment (e.g. Jules, local subprocess, Claude, Codex) tasked with executing a single node packet. Executors are treated as replaceable transports and workers; they do not own graph truth.

---

## Invariants & Execution Boundaries

- **Worktree Isolation:** Every session executes in an isolated git worktree rather than performing open-heart surgery on repository checkouts.
- **No Direct Graph Authority:** Passing test suites and successful executor completion are evidence only; they do not mark a node complete in the graph.
- **Durable File Return:** Return data lands as files via `GDDP_RECEIPTS_PATH`. The SQLite queue database is merely an index over return files.

---

## Entity Map

| Aspect | Location / Reference |
|---|---|
| **Operating Loop Step** | Step 3 (Return) in [`docs/proposals/LOOP.md`](../docs/proposals/LOOP.md) |
| **Architectural Decision** | [`docs/decisions/Ending-git-open-surgery-with-worktree-per-session.md`](../docs/decisions/Ending-git-open-surgery-with-worktree-per-session.md) |
| **Local Executor** | [`scripts/local_agent_executor.py`](../scripts/local_agent_executor.py) |
| **Return Router** | [`scripts/runtime/return_router.py`](../scripts/runtime/return_router.py) · [`scripts/runtime/test_return_router.py`](../scripts/runtime/test_return_router.py) |
| **Repo Resolution** | [`scripts/runtime/repo_resolver.py`](../scripts/runtime/repo_resolver.py) |
| **Handoffs & Specs** | [`.handoffs/047-executor-neutral-session-lifecycle.md`](../.handoffs/047-executor-neutral-session-lifecycle.md) · [`.handoffs/101-session-worktree.md`](../.handoffs/101-session-worktree.md) |
