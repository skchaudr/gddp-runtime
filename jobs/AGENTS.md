```json
{
  "schema_version": "2.0",
  "scope": "jobs",
  "description": "System invariants and current implementation boundaries governing execution workspaces, worktree isolation, and queue state.",
  "invariants": [
    {
      "id": "jobs.worktree-isolation",
      "name": "Worktree Isolation",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#5-execution-isolation--infrastructure-boundaries",
      "rule": "Perform all executor modifications within isolated dedicated worktrees, preserving repository checkouts intact.",
      "current_implementation": "Local subprocess adapters and mission runners provision disposable worktrees under .worktrees/ or dedicated temp directories.",
      "drift_pattern": "Editing the active repository checkout directly during node implementation runs.",
      "source": "docs/invariants/invariants.md#5-execution-isolation--infrastructure-boundaries"
    },
    {
      "id": "jobs.database-as-rebuildable-cache",
      "name": "Database as Rebuildable Cache",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#4-storage--evidence-doctrine",
      "rule": "Treat filesystem receipts and commit artifacts as primary evidence, treating queue.db as an index that can regenerate at will.",
      "current_implementation": "Queue state lives in db/queue.db (ignored by git); evaluation receipts persist under .gddp/receipts/ and git commits.",
      "drift_pattern": "Relying on database tables as the sole authority while omitting durable disk receipts.",
      "source": "docs/invariants/invariants.md#4-storage--evidence-doctrine"
    }
  ],
  "current_implementation": [
    {
      "id": "jobs.ephemeral-runtime-isolation",
      "name": "Ephemeral Runtime Directory Structure",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Exclude all execution directories, run spools, and intermediate outputs under jobs/ from repository commits.",
      "current_implementation": ".gitignore excludes jobs/* except jobs/context.md and jobs/AGENTS.md.",
      "drift_pattern": "Accidentally checking in job workspace folders or local subprocess spools.",
      "source": "jobs/context.md#2-invariants"
    },
    {
      "id": "jobs.runtime-queue-separation-from-graph-truth",
      "name": "Runtime Queue Separation from Graph Truth",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Route job transitions through runtime queue state while preserving graph truth strictly for human modification.",
      "current_implementation": "Runtime scripts (scripts/jobs_status.py, reconciler.py) transition rows in jobs and queue_records tables, leaving graph YAMLs in gddp-config untouched.",
      "drift_pattern": "Attempting to update graph node statuses from executor completion handlers.",
      "source": "jobs/context.md#2-invariants"
    }
  ]
}
```
