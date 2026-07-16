# Result Summary - Job State Consistency

This change closes the targeted `jobs.status`/`jobs.queue_state` divergence paths
and documents a reversible operator step for the existing inconsistent row. It
does not mutate the live database or advance graph truth.

### Key Changes
1. **Root Cause Documentation (`decision.md`)**:
   - Traced `job_20260711T16542651` to the exact Factory/Droid session and status-only SQL command that created `status=failed`, `queue_state=running`.
   - Recorded the timestamp, session id, successful exit, command purpose, and primary local evidence paths.
   - Provided reversible operator SQL without silently changing the live row.
2. **Write Paths Alignment**:
   - Updated `scripts/runtime/decision_loop/engine.py` to set stale jobs to canonical `'failed'` in both columns; `'expired'` remains event-only.
   - Updated `scripts/rollback.py` to set both `status` and `queue_state` to `'failed'`.
   - Updated `scripts/node_status.py` to use the queue-state list as the shared job lifecycle vocabulary and set both columns together.
   - Updated `scripts/runtime/return_router.py` to set both columns to `'running'` (and the `queue_records` table `queue` state to `'running'`) when successfully redispatched.
3. **Consistency Check & Test Safety**:
   - Added a critical consistency check probe to the deployment baseline script `deploy/mini-heartbeat/bin/baseline.sh` that detects and fails if any rows have mismatched `status` and `queue_state`.
   - Added focused stale-job and operator-transition regression coverage.
   - Kept the baseline mismatch probe that fails when any job row diverges.
