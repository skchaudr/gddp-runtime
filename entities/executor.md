# Entity: Executor

The **executor** is the worker environment (e.g. Jules, local subprocess, Claude, Codex, Pi, Droid, even the human operator) tasked with executing a single node packet. Executors are treated as interchangeable transports and workers; they do not own graph truth. 

The lead executor can be an orchrestator, who is largely in a read-only capacity routing workers and is in pursuit of advancing the graph as a whole, not just optimize for the set of visible nodes in front of it. 

---

## Invariants & Execution Boundaries

- **Worktree Isolation:** Every session ideally executes in an isolated git worktree; an orchrestator can take on and dispatch as many nodes as feasible in that session, and may stop and resume that session. Each node having its own worktree was not a viable long-term path that was pivoted from.
- **No Direct Graph Authority:** Passing test suites and successful executor completion are evidence only; they do not mark a node complete in the graph. Forward momentum may be preserved and a provisional acceptance can lead to genuine good work land in the meantime. 
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
