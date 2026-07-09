# Replay

Replay is the recovery tool for when a runtime step recorded partial or wrong state and you want to re-run just that step from what is already in SQLite, without re-receiving the original webhook or re-classifying from scratch. `scripts/runtime/replay.py` is a CLI with two modes: re-run the return router for a recorded result, or re-dispatch a specific job.

The defining constraint is that replay operates on persisted DB state. There is no DB surgery, no manual row editing, no re-ingestion. You point replay at a `result_id` or a `job_id`, and it reads the existing row, re-runs the appropriate stage, and writes the new outcome back through the normal state recorder.

## What is replayed

### replay_result (--result-id)

Re-runs the return router logic (`return_router.handle_merged_pr`) for the event associated with a recorded result. Use this when the return router ran but produced a wrong or incomplete receipt, or when the receipt needs to be recreated after a verification bridge change.

The flow:

1. Take the `result_id` (must start with `res_`).
2. Derive the `event_id` by swapping the prefix: `res_...` becomes `evt_...`. This is a convention, not a join; the IDs are paired at intake time.
3. Load the event row from `events`.
4. Call `return_router.handle_merged_pr(event)` and print the outcome.

If the derived `event_id` does not exist in the database, replay prints an error and returns. No rows are touched until `handle_merged_pr` runs, and whatever that function writes is what gets persisted.

### replay_job (--job-id)

Re-dispatches a specific job to its assigned executor (e.g. Jules). Use this when a dispatch failed, timed out, or produced a result you want to throw away and try again.

The flow:

1. Load the job row from `jobs`.
2. Print the job details: id, node, project, executor, goal, status.
3. Prompt for explicit operator confirmation: `Re-dispatch this job? (yes/no):`. Anything other than literal `yes` aborts.
4. Call `dispatcher.dispatch(job, job['repo'])` through the same adapter the heartbeat uses.
5. On success, mark the event mapped and the job running through `state_recorder`, commit, and print the issue URL.
6. On failure, mark the job failed through `state_recorder`, commit, and print the error.

The confirmation gate is the safeguard. Re-dispatching a job creates a new GitHub issue (or whatever the adapter's dispatch side effect is), and that is not something the runtime should do silently on a stale read. The `input()` call is the human-in-the-loop checkpoint.

## What is NOT replayed

- **Initial webhook intake.** Events are read from the `events` table, not re-received from GitHub. The intake server is not involved.
- **Classification and scoping.** The persisted `classification` and `scope_status` on the event row are used as-is. Replay does not re-run the classifier or the scope checker.

This keeps replay surgical. If the original classification was wrong, fix the event row (or re-ingest), do not use replay. Replay is for re-running downstream stages on top of the classification that already happened.

## Database access

`connect()` opens `db/queue.db` under the runtime root (resolved from `GDDP_RUNTIME_ROOT`, with `OPCLAW_ROOT` as legacy fallback), sets `row_factory = sqlite3.Row` so rows can be addressed by column name, and turns `foreign_keys=ON`. Every replay function uses this helper and closes the connection in a `finally` block.

## Import fallbacks

The module tries `from scripts.runtime import return_router` and `from scripts.runtime.heartbeat import dispatcher, state_recorder`, and falls back to `from runtime import ...` on `ImportError`. This lets the same file work whether it is run as `python3 -m runtime.replay` from inside `scripts/` or as `python3 -m scripts.runtime.replay` from the repo root.

## CLI

```
python3 -m runtime.replay --result-id res_20260312T21053737
python3 -m runtime.replay --job-id   job_20260312T21053737
```

The two flags are mutually exclusive and one is required. There is no `--all` or batch mode; replay is intentionally one-item-at-a-time so the operator sees exactly what each re-run does.

## Key source files

| File | Role |
|---|---|
| `scripts/runtime/replay.py` | `replay_result`, `replay_job`, CLI entry point |

## Related pages

- [overview/architecture.md](../overview/architecture.md) for where return routing and dispatch sit in the flow
- [systems/return-router.md](return-router.md) for what `handle_merged_pr` actually does
- [systems/state-persistence.md](state-persistence.md) for the tables replay reads from
- [systems/executor-adapters.md](executor-adapters.md) for the dispatch path replay_job re-enters
