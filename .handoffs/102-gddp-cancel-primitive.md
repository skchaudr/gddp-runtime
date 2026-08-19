# 102 — GDDP cancellation primitive: unsafe lifecycle gap traced

------------------------------------------------ Agent Section START

Date: 2026-08-18
Worktree: none (investigation session)
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Traced the exact lifecycle of `gddp jobs set <job> failed` followed by `gddp jobs retry` while the original executor process is still alive. The proposed orchestrator behavior (mark failed, redispatch) is not safe: `jobs set failed` is a DB-only operation that does not stop the executor, and the reconciler has no job-state guard before collecting late results.

### Scope touched (One file per line, +/- for only what was changed)

No files changed. Investigation only — read reconciler.py, jobs_status.py, state_recorder.py, pi_rpc_adapter.py, return_router.py, executor_protocol.py.

### Constrained areas touched (none / list + justification)

none

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

Clean. `## main...origin/main`, untracked `.factory/` and `.local/` only. No changes made.

### Artifacts (Filepath - Description, 1 line max per artifact)

This handoff file — the only artifact.

### Resume point (2-3 sentences max, anything more must be critically justifiable)

The next session should design `gddp jobs cancel` as a standalone runtime task. The contract is already traced below — it needs to be one coherent action that writes `cancel.requested` (prevents late persist), marks the job `cancelled` (prevents reconciler retry), and is the only path the Pi orchestrator gets when it graduates to active termination.

------------------------------------------------ Agent Section END

## Discovery: why `jobs set failed` is not cancellation

### What `jobs set <job> failed` actually does

`_apply_resolved_state_change` in `scripts/jobs_status.py`:
- `UPDATE jobs SET queue_state='failed', status='failed'`
- `UPDATE queue_records SET queue='failed'`
- Inserts audit row in `decision_results`

It does NOT:
- Update `executor_sessions` table (session stays `dispatched`/`running`)
- Write `cancel.requested` to the spool (only `adapter.cancel()` does)
- Signal or kill the process

### Why the reconciler keeps polling

`get_active_executor_sessions` in `state_recorder.py` queries:
`executor_sessions WHERE state IN ('dispatched','running','awaiting_reply','needs_operator','collected')`
It does NOT filter on `jobs.status` or `jobs.queue_state`. The old session stays "active."

`_reconcile_one` in `reconciler.py` fetches `job_row` but does NOT check `job_row["status"]` or `job_row["queue_state"]` before polling or collecting. The only job-state check in the entire reconciler is in `_handle_failed` (line ~1010), which checks for `cancelled` — and that path is only reached when the adapter reports the session as `failed`/`crashed`/`missing`, not while it's `running`.

### Late-result resurrection path

1. Orchestrator marks job `failed` via `gddp jobs set <job> failed`
2. Old executor process keeps running (nothing stopped it)
3. Old executor completes: `pi_rpc_adapter._run_one_turn` persists result, writes `exit.json` (returncode=0), writes `result.json` (commit SHA)
4. Next heartbeat tick: reconciler polls → `read_pi_rpc_status` sees `exit.json` returncode=0 → `SessionStatus(state="completed")`
5. `_reconcile_one` calls `_handle_completed` — does NOT check `job_row["status"]`
6. `_handle_completed` collects result, verifies ancestry, queues evaluation
7. `_finalize_evaluation` calls `mark_jobs_awaiting_review(con, (pending.job_id,))` → `UPDATE jobs SET status='awaiting_review', queue_state='awaiting_review'`
8. **The `failed` state is overwritten to `awaiting_review`.** The old executor's late result resurrects the job.

### Why `jobs retry` doesn't help

`apply_retry` in `jobs_status.py` requires `job["status"] == "awaiting_review"`. It calls `retry_reviewed_job` in `return_router.py`, which is the human review rejection path. There is no CLI path to redispatch a `failed` job.

### Why `cancelled` doesn't fully protect

`_handle_failed` checks for `cancelled` and skips retry. But `_handle_completed` does NOT check for `cancelled` — a late successful result still gets collected and overwrites to `awaiting_review`. And `jobs set cancelled` still doesn't write `cancel.requested`, so the old process keeps running.

### The one mechanism that works: `cancel.requested`

In `pi_rpc_adapter._run_one_turn`, after `agent_end`:
```python
cancel_path = attempt_dir / "cancel.requested"
if cancel_path.exists():
    _write_exit(attempt_dir, returncode=130, cancelled=True, ...)
    continue  # skips persist_result
```
If `cancel.requested` exists, the turn writes `exit.json` with returncode=130 and skips `persist_result`. So `read_pi_rpc_status` returns `failed`, and `_handle_failed` is called. With `job_state == "cancelled"`, it marks the session failed and does NOT retry.

But no `gddp` CLI command writes this marker. Only `adapter.cancel()` does, and it's not exposed through the CLI. The `gddp jobs` subcommands are: `list`, `show`, `live`, `results`, `set`, `retry`. No `cancel`.

## Proposed contract for `gddp jobs cancel <job>`

One coherent lifecycle action that:

1. Calls `adapter.cancel(session_ref)` — writes `cancel.requested` to the spool, which prevents the late result from being persisted (the `_run_one_turn` check skips `persist_result` and writes `exit.json` with returncode=130)
2. Marks the job `cancelled` in the DB — so `_handle_failed` sees `job_state == "cancelled"` and does NOT retry
3. Updates `executor_sessions` state to reflect the cancellation
4. Is idempotent — calling it on an already-terminal job is a no-op
5. Is the ONLY lifecycle termination command the Pi orchestrator gets when it graduates to active termination authority

This is NOT part of Pi Orchestrator v1. The orchestrator v1 has observational lifecycle authority only: it detects stuck/hung attempts and reports them to the human operator. Active termination is a separate runtime task with this contract as its starting point.

------------------------ Do NOT edit this file past this point

## Narrative / Trajectory (SAB ONLY)

### Intent going into/at start of session

### Interpretation of how the session went

### Friction experienced or anticipated

### What's Next (Momentum or Lack Thereof)
