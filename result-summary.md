# Result Summary - Job State Consistency

We have resolved the inconsistency between `jobs.status` and `jobs.queue_state` by harmonizing all database write paths and providing documented, reversible recovery steps for `job_20260711T16542651`.

### Key Changes
1. **Root Cause Documentation (`decision.md`)**:
   - Diagnosed how `job_20260711T16542651` became inconsistent (`status=failed`, `queue_state=running`).
   - Highlighted the mismatched write paths (engine expiry, rollback, manual status commands, return router redispatches).
   - Provided production-safe, reversible SQL queries to correct the record and reverse the change.
2. **Write Paths Alignment**:
   - Updated `scripts/runtime/decision_loop/engine.py` to set both `status` and `queue_state` to `'expired'` during stale job cleanup.
   - Updated `scripts/rollback.py` to set both `status` and `queue_state` to `'failed'`.
   - Updated `scripts/node_status.py` to set both columns to `args.state` during a manual state transition, ensuring they remain identical.
   - Updated `scripts/runtime/return_router.py` to set both columns to `'running'` (and the `queue_records` table `queue` state to `'running'`) when successfully redispatched.
3. **Consistency Check & Test Safety**:
   - Added a critical consistency check probe to the deployment baseline script `deploy/mini-heartbeat/bin/baseline.sh` that detects and fails if any rows have mismatched `status` and `queue_state`.
   - Added a robust python unit test `test_jobs_status_and_queue_state_consistency` inside `scripts/runtime/decision_loop/test_decision_loop.py` to programmatically assert this.
   - Fixed all mock sqlite tables in unit tests to support the new database column logic and keep the entire pytest suite completely green.
