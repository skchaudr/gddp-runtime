# Implementation Decision — node `job-state-consistency`

## Root cause of the inconsistent row

`job_20260711T16542651` sits at `status=failed, queue_state=running`. The
cause is the decision-loop stale cleaner at
`scripts/runtime/decision_loop/engine.py:59` (in the base commit
`665465e54b3b60951c9e2931852d36295f1fdfad`):

```sql
UPDATE jobs SET status = 'expired'
WHERE status IN ('dispatched', 'running')
AND created_at < datetime('now', '-6 hours')
```

This UPDATE only writes `status`. `queue_state` is not touched. The
sequence that produced the observed row:

1. The job was in `status=running, queue_state=running` while a remote
   executor was working.
2. The executor silently failed; no result came back, so neither
   `heartbeat.py` nor `reconciler.py` overwrote the row.
3. The decision-loop stale cleaner ran and rewrote `status` to
   `expired` — but `queue_state` stayed at `running` because the
   cleaner only updates one column.
4. A subsequent dispatch path (or heartbeat) re-touched the row and
   converted the half-applied `expired` to `failed` (a later commit
   in the history, `23c5f80`, renamed `expired` → `failed` in the
   cleaner). The `queue_state=running` half was never corrected.
5. The baseline probe counts one of the two columns; "running=2" in
   the incident readout was the `queue_state` count.

Direct verification: `sqlite3 db/queue.db "SELECT job_id, status,
queue_state FROM jobs WHERE status != queue_state;"` returns exactly
this one row. The canary was a real remote dispatch that the cleaner
expired while the operator was offline; it is not currently in any
dispatchable state.

## Why the fix is small and stays in lockstep

Every other write path in `scripts/` already sets both columns:

| path | status | queue_state | source |
|---|---|---|---|
| `scripts/heartbeat.py:175` | `running` | `running` | dispatch success |
| `scripts/heartbeat.py:185` | `failed` | `failed` | dispatch failure |
| `scripts/rollback.py:66` | `failed` | `cancelled` | operator rollback (INTENTIONAL) |
| `scripts/dry_run.py:300` | `awaiting_review` | `awaiting_review` | simulated result |
| `scripts/jobs_status.py:320–325` | `<state>` | `<state>` | manual `set` |
| `scripts/runtime/heartbeat/reconciler.py:606` | `awaiting_review` | `awaiting_review` | evaluator receipt |
| `scripts/runtime/decision_loop/engine.py:59` | `expired` | `expired` (now) | stale cleaner (was `expired` only — the bug) |

The decision-loop cleaner is the only writer that updated `status`
without also updating `queue_state`. The fix adds `queue_state =
'expired'` to that single UPDATE so the cleaner is consistent with the
rest of the table.

`expired` is also added to `JOB_STATUSES` and `QUEUE_STATES` in
`scripts/jobs_status.py` so:

- `python3 -m scripts.jobs_status set <job> expired --reason "..."`
  is a valid operator action; before the fix, the CLI rejected
  `expired` even though the engine could produce it.
- The consistency check below can recognize the (expired, expired) pair
  as valid instead of as a mismatch.

## The intentional divergence — `rollback.py`

`scripts/rollback.py:66` writes `status='failed', queue_state='cancelled'`.
This is **not** a bug:

- The operator-facing terminal status is `failed` (the rollback
  legitimately ended the attempt without success).
- The dispatcher-side state is `cancelled` so the dispatch loop will
  not re-pick the row.
- The split is audited in `decision_results` and is the only path
  that produces it; no other writer can produce this pair.

To make this explicit and machine-checkable, the pair is registered in
`jobs_status.INTENTIONAL_DIVERGENT_PAIRS` and `rollback.py` carries a
comment cross-referencing it. The consistency check (below) tolerates
exactly this pair and flags any other divergence as a write-path bug.

## Consistency check

A new read-only probe catches a regression on any current or future
writer.

### Python surface — `jobs_status.check`

```python
# scripts/jobs_status.py
def find_inconsistent_jobs(con=None) -> list[dict]:
    """Return jobs whose (status, queue_state) pair is not a valid match.

    Consistent if status == queue_state, OR if the pair is in
    INTENTIONAL_DIVERGENT_PAIRS (currently only the rollback path:
    status='failed', queue_state='cancelled').
    """
```

CLI:

```
python3 -m scripts.jobs_status check
# exit 0  → all rows consistent
# exit 1  → at least one mismatched row (prints job_id + columns)
```

Validated on the live production DB at
`/Users/sab-mini/repos/gddp-runtime/db/queue.db`:

```
$ GDDP_RUNTIME_ROOT=/Users/sab-mini/repos/gddp-runtime \
    .venv/bin/python -m scripts.jobs_status check
FOUND 1 inconsistent job row(s):
  job_20260711T16542651  status=failed  queue_state=running
exit=1
```

The probe detects the exact incident row.

### Shell probe — `baseline.sh` section 5a

`deploy/mini-heartbeat/bin/baseline.sh` now has a 5a step that
calls the same probe against `$GDDP_RUNTIME_ROOT/db/queue.db`.
A mismatch is a `[CRIT]` and forces `exit 2`. Catches the bug on
the next baseline run without waiting for an operator to notice the
count drift.

### Unit tests

`scripts/test_jobs_status.py` adds `JobsStatusConsistencyTests` (5
tests) covering:

- matching rows are consistent
- divergent row is flagged
- the rollback pair is intentionally tolerated
- `check` subcommand returns exit 1 on mismatch, prints the row
- `check` subcommand returns exit 0 when clean

`scripts/runtime/decision_loop/test_decision_loop.py` adds
`test_clean_stale_state_writes_both_status_and_queue_state` which
inserts two stale rows + one fresh row, calls `_clean_stale_state`,
and asserts every row's `status` and `queue_state` moved together.

`scripts/jobs_status.py:JOB_STATUSES` now contains `"expired"`, so
the `_apply_resolved_state_change` operator path can also drive a
job to `expired` deliberately.

## Reconciling the inconsistent row — NOT applied here

The existing inconsistent row is **left as-is** in the production DB.
The graph-handoff rule says this node produces evidence; only the
human moves graph truth, and only the operator touches runtime
state. The reconciliation is a single SQL statement, recorded here
so a human can run it after reviewing this evidence:

```sql
-- Pre-flight (read-only): show what is about to be changed.
SELECT job_id, status, queue_state
  FROM jobs
 WHERE job_id = 'job_20260711T16542651';

-- One-shot reconcile. status='failed' is preserved (the executor
-- really did fail); queue_state is brought into line.
-- Audit: append a decision_results row first so the human can see
-- who and why.
INSERT INTO decision_results
    (result_id, action, node_id, project_id, reason, created_at)
VALUES
    ('dec_reconcile_20260711T16542651', 'manual_status_change',
     'canary-retry-proof', NULL,
     'reconcile after job-state-consistency: queue_state=stale from expired-cleaner bug',
     datetime('now'));

UPDATE jobs
   SET queue_state = 'failed'
 WHERE job_id = 'job_20260711T16542651';

-- Post-flight verification:
SELECT job_id, status, queue_state FROM jobs
 WHERE job_id = 'job_20260711T16542651';
-- expected: job_20260711T16542651 | failed | failed
```

This is reversible: the `decision_results` row is the audit trail and
re-running it with `queue_state='running'` would restore the prior
state. Do not run this without operator authorization; the canary is
not currently being dispatched, so the dashboard is lying rather than
the runtime being broken.

## What this node does not do

- Does **not** modify the runtime database (no SQL applied here).
- Does **not** change receipt semantics, the human review gate, or
  the evaluator's two-lane verdict.
- Does **not** change `queue.db` schema or column semantics; the
  fix is purely a writer-side invariant.
- Does **not** mark `job-state-consistency` complete. The verdict
  belongs to the human.
