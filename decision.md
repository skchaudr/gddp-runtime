# Decision Document - Job State Consistency

## 1. Root Cause Analysis for `job_20260711T16542651` Mismatch

During a baseline check, the dashboard reported `running=2` even though only one job was truly active. Investigation of the SQLite database (`queue.db`) revealed that `job_20260711T16542651` (the failed canary attempt) had a state divergence:
- `status = 'failed'`
- `queue_state = 'running'`

This divergence made operator-facing counts inaccurate, as different dashboard views and scripts read either `status` or `queue_state`.

### Proven Origin

The mismatch was created by a direct status-only SQLite update, not by a runtime
writer. At `2026-07-11T17:10:35.380Z`, Factory/Droid session
`00e978de-f147-4492-88d3-c13dcc5a4f5e` ran:

```sql
UPDATE jobs SET status = 'failed'
WHERE job_id = 'job_20260711T16542651';
```

The session recorded exit code `0` and the follow-up row
`job_20260711T16542651|canary-retry-proof|test-project|failed`. Its stated
purpose was to remove this stale test-project job from the active-job guard so a
new gddp-runtime canary could dispatch. Because the command did not update
`queue_state`, its previous value, `running`, remained.

Primary evidence is local Factory history:

- `~/.factory/sessions/-Users-sab-mini-repos-gddp-runtime/00e978de-f147-4492-88d3-c13dcc5a4f5e.jsonl`, records 695 and 698
- `~/.factory/logs/droid-log-single.log.2026-07-11`, lines 37345 and 37355-37356

### Write Paths Hardened

The patch prevents the same class of divergence in the targeted runtime and
operator update paths:

1. `decision_loop/engine.py` moves stale jobs to canonical `failed/failed`.
   `expired` remains an event state and is not introduced into the job vocabulary.
2. `rollback.py` moves rolled-back jobs to `failed/failed`.
3. `node_status.py` treats the canonical queue-state list as the shared job
   lifecycle vocabulary and writes both job columns together.
4. `return_router.py` moves a successful retry to `running/running` and updates
   its queue record.

---

## 2. Reversible State Reconciliation

The code change does not mutate the live database. The operator can reconcile
the existing row with this documented, reversible SQL step.

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

`jobs.status` and `jobs.queue_state` remain redundant for compatibility, so the
targeted writers update them atomically to the same canonical lifecycle value.
The baseline probe reports any remaining mismatch for operator review. Human
acceptance remains the only source of graph truth.
