# Result Summary — node `job-state-consistency`

## Actions taken

- Fixed `scripts/runtime/decision_loop/engine.py:_clean_stale_state`
  to write both `status='expired'` and `queue_state='expired'` in one
  UPDATE; previously the cleaner only wrote `status` and left
  `queue_state` untouched, which is the origin of the inconsistent
  canary row.
- Added `"expired"` to `JOB_STATUSES` and `QUEUE_STATES` in
  `scripts/jobs_status.py` so the manual `set` CLI can drive a job
  to `expired` and the consistency check recognizes the (expired,
  expired) pair as valid.
- Introduced `scripts/jobs_status.INTENTIONAL_DIVERGENT_PAIRS` and
  `find_inconsistent_jobs()`; the new `python3 -m scripts.jobs_status
  check` subcommand exits 0 on a clean DB and 1 on any divergent
  row, printing the offending `job_id` and column values.
- Documented the intentional `(failed, cancelled)` split produced by
  `scripts/rollback.py` in code (cross-referencing
  `INTENTIONAL_DIVERGENT_PAIRS`) so the divergence is treated as
  designed, not as a write-path bug.
- Added a 5a section to `deploy/mini-heartbeat/bin/baseline.sh` that
  runs the new check on the production DB; a mismatch becomes a
  `[CRIT]` and forces `exit 2`.
- Added six tests:
  - `test_jobs_status.py::JobsStatusConsistencyTests` (5 tests) —
    covers matching, divergent, the intentional rollback pair, and
    the `check` subcommand's exit codes.
  - `runtime/decision_loop/test_decision_loop.py::
    test_clean_stale_state_writes_both_status_and_queue_state` —
    regression test for the engine fix.
- Verified the new probe against the live production DB at
  `/Users/sab-mini/repos/gddp-runtime/db/queue.db`:
  `python3 -m scripts.jobs_status check` reports
  `job_20260711T16542651  status=failed  queue_state=running` and
  exits 1.

## Validation

- `.venv/bin/python -m pytest -q scripts` → **390 passed** in 5.11s
  (was 384 at the base commit; the +6 are the new tests).
- `python3 scripts/dry_run.py` → exit 0 (the existing happy path
  still works end-to-end).
- `bash -n deploy/mini-heartbeat/bin/baseline.sh` → syntax OK.
- `python3 -m scripts.jobs_status check` against the production DB →
  exit 1, prints exactly the canary row from the goal.

## Reconciliation (deferred)

The inconsistent row `job_20260711T16542651` is left untouched in
the production DB. The full SQL — audit row, UPDATE, post-flight
verify — is recorded in `decision.md` and is reversible. The runtime
is not currently dispatching the row, so the dashboard is lying but
the loop is not running away. A human operator must run the SQL
after reviewing the evidence in this node.

## Files touched

- `scripts/runtime/decision_loop/engine.py` — stale cleaner writes
  both columns.
- `scripts/jobs_status.py` — `expired` in both state sets, divergent
  pair registry, `find_inconsistent_jobs`, `check` subcommand.
- `scripts/rollback.py` — comment on the intentional (failed,
  cancelled) split.
- `scripts/test_jobs_status.py` — new consistency test class.
- `scripts/runtime/decision_loop/test_decision_loop.py` — regression
  test + `queue_state` column in the existing test's schema.
- `deploy/mini-heartbeat/bin/baseline.sh` — section 5a consistency
  probe.
