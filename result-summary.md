# Result Summary - Job State Consistency

We closed PR #108’s job state drift by restoring the terminal stale-cleanup invariant and re-establishing focused regression checks for state coherence.

### Key Changes
1. **Root Cause Documentation (`decision.md`)**:
   - Updated `scripts/runtime/decision_loop/engine.py` to canonicalize stale running/dispatched jobs to `failed/failed`.
   - Kept `scripts/rollback.py`, `scripts/node_status.py`, and `scripts/runtime/return_router.py` aligned so terminal/active transitions write coherent job lifecycle states.
2. **Write Path Alignment**:
   - Ensured stale cleanup now produces `status='failed'` and `queue_state='failed'`, preventing terminal `failed/running`.
   - Restored `scripts/test_node_status.py` regression coverage for manual operator transitions.
   - Restored stale job regression in `scripts/runtime/decision_loop/test_decision_loop.py`.
3. **Consistency Check & Test Safety**:
   - Kept baseline stale/queue mismatch checks and write-path coherence.
   - Restored focused tests that directly cover the repaired behavior.
