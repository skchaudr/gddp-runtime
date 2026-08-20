# System Invariants — GDDP Runtime

These invariants represent inviolable system rules. No implementation, proposal, or agent execution may violate them.

---

## 1. Human Authority on Graph Truth
- **Sole Acceptance Authority:** Only a human operator modifying graph truth (`gddp node browse`) can transition a node to `accepted`.
- **Automated Gates are Second-to-Last:** Passing unit tests, clean linter outputs, executor success, and passing evaluator verdicts are evidence for human review, never graph truth.
- **Node Status != Implementation State:** Node acceptance reflects project intent satisfaction as judged by human review, not temporary implementation perfection.

## 2. Intent Preservation & Node Integrity
- **Unit of Intent:** A node is the atomic unit of project intent. It defines the goal, constraints, and acceptance criteria.
- **Node Immutability During Retries:** A retry re-attempts the exact same node definition unchanged. Evaluator findings are injected strictly as the retry's fix-list; the scope of the node is never altered during retries.
- **Continuation Proposals for Discovered Scope:** Work discovered beyond a node's declared scope is never silently implemented or grafted onto the node. It is recorded as a continuation proposal (YAML in proposals ledger), invisible to the execution frontier until explicitly materialized into the graph by a human operator.

## 3. Evaluator & Verification Integrity
- **Graph-Directed Evidence Horizon:** The evaluator's evidence horizon is graph-directed: it may inspect as little or as much canonical project context as necessary to judge the current work's criteria and graph integrity, including adjacent or downstream nodes when their assumptions may be affected.

## 4. Storage & Evidence Doctrine
- **Files are Truth:** Durable files (`GDDP_RECEIPTS_PATH`, verdict YAMLs, git worktrees) constitute primary truth. The SQLite database (`db/queue.db`) is a rebuildable cache and index; nothing of architectural value is lost if `queue.db` is purged.
- **Receipts Prove Execution:** A `provisional` node status is invalid without a concrete verdict receipt file backing it.
- **Citations Required for Automated Action:** Evaluator-triggered retries require cited, concrete evidence (repo path, line number, or canonical node ID). Uncited findings route to human review.

## 5. Execution Isolation & Infrastructure Boundaries
- **Worktree Isolation:** Every agent execution session operates in a dedicated, isolated git worktree (`.worktrees/` or session temporary directory). Open-heart surgery on repository checkouts is forbidden.
- **Frozen Infrastructure Discipline:** Components marked as frozen (`scripts/intake_server.py`, `scripts/adapters/jules_*`, `deploy/rig1-heartbeat/`, `deploy/deploy.sh`, `scripts/rollback.py`, `scripts/export_evaluations.py`) receive zero speculative investment and may only be modified when explicitly targeted by a named node.

## 6. Development & Agent Workflow Invariants
- **No Direct Main Commits:** All changes must originate on a dedicated branch (`feat/`, `fix/`, `docs/`, `refactor/`, `chore/`).
- **Atomic Logical Commits:** Every logical change is committed immediately with conventional commit syntax and co-authorship metadata.
- **Clean Handoff Contract:** Every agent session leaves a clean git working tree, verified test execution, and an updated numbered handoff in `.handoffs/`.
