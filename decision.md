# Decision Document - Job State Consistency

## 1. Root Cause Analysis for `job_20260711T16542651` Mismatch

During a baseline check, the dashboard reported `running=2` even though only one job was truly active. Investigation of the SQLite database (`queue.db`) revealed that `job_20260711T16542651` (the failed canary attempt) had a state divergence:
- `status = 'failed'`
- `queue_state = 'running'`

This divergence made operator-facing counts inaccurate, as different dashboard views and scripts read either `status` or `queue_state`.

### Codebase Write Path Inconsistencies (Code Evidence)
We identified several live write paths in the codebase that update one column but neglect the other or introduce mismatching values:
1. **`scripts/runtime/decision_loop/engine.py` (Stale Expiry)**:
   In `_clean_stale_state`, stale running/dispatched jobs older than 6 hours are now canonicalized to terminal failed state using:
   ```sql
   UPDATE jobs SET status = 'failed', queue_state = 'failed'
   WHERE status IN ('dispatched', 'running')
   AND created_at < datetime('now', '-6 hours')
   ```
   This prevents stale cleanup from producing terminal drift.
2. **`scripts/rollback.py` (Rollback reconciliation)**:
   The rollback path now writes both columns as `failed`:
   ```python
   UPDATE jobs SET status='failed', queue_state='failed' WHERE job_id=?
   ```
   This keeps rollback terminal writes coherent.
3. **`scripts/node_status.py` (Manual operator transition)**:
   The interactive tool now updates both lifecycle columns together:
   ```python
   con.execute("UPDATE jobs SET queue_state = ?, status = ? WHERE job_id = ?", (args.state, args.state, job["job_id"]))
   ```
   This avoids operator-driven mismatches.
4. **`scripts/runtime/return_router.py` (Redispatch retry loop)**:
   On successful redispatch, the writer increments attempt and sets both `status` and `queue_state` to `'running'`.

### Most Probable Origin of `job_20260711T16542651`
Given the state of the canary job, the mismatch was produced by one of two sequences:
- **Manual Intervention/Reconciliation**: The operator manually ran `rollback.py` on the canary job (which was stuck/timed out), updating its `status` to `'failed'` and `queue_state` to `'cancelled'`. To attempt a resume or force-mark it back to running without spinning up a new job, a manual SQLite update query was executed:
  ```sql
  UPDATE jobs SET queue_state = 'running' WHERE job_id = 'job_20260711T16542651';
  ```
  This left `status` as `'failed'` while making `queue_state` `'running'`.
- **Direct Manual Status Force**: Alternatively, the operator manually ran a query to fail the job without setting the queue state:
  ```sql
  UPDATE jobs SET status = 'failed' WHERE job_id = 'job_20260711T16542651';
  ```

---

## 2. Reversible State Reconciliation

To reconcile the existing inconsistent row in production (`queue.db`), we use a documented, reversible SQL migration rather than silent or untracked mutation.

### Correction Step
This sets the `queue_state` to match the job's actual `'failed'` status.
```sql
UPDATE jobs SET queue_state = 'failed' WHERE job_id = 'job_20260711T16542651';
```

### Reversion Step
Should we need to restore the state back to its original (diverged) values for auditing:
```sql
UPDATE jobs SET queue_state = 'running' WHERE job_id = 'job_20260711T16542651';
```

---

## 3. Rationale for Redundancy Alignment
To prevent future drift, we align both `status` and `queue_state` to hold matching values on terminal and active write paths. This prevents terminal drift such as `failed/running`.
