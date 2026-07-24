# Surviving Canary Evidence — Node 2 Real Round Trip (053)

Archived 2026-07-23. Read-only snapshot of the intact evaluated run Sab preserved
for review. Source rows/refs left untouched in place; these are copies.

## Job

- **job_id:** `job_20260724T010811130dd14802e579`
- **node_id:** `job-state-consistency`
- **DB state (verified via `sqlite3 db/queue.db`):**
  - `jobs`: status=`awaiting_review`, attempt=`0`
  - `executor_sessions`: `job_20260724T010811130dd14802e579:attempt:0` state=`evaluated`
  - `results`: `res_job_20260724T010`, outcome=`fail`, status=`awaiting_review`, acceptance_check length=6899

## Result commit / git ref

- **commit:** `cd7bc2daa902c2d87e511984301f39956cf0dfa0`
- **parent:** `876646ebb5393143420821b09658a118ff8a17f5` (main line)
- **ref (NOTE — branch under `refs/heads/gddp/...`, not `refs/gddp/...`):**
  `refs/heads/gddp/result-job_20260724T010811130dd14802e579-job_20260724T010811130dd14802e579-job-state-consistency-attempt-0-2e4b31c7c0b142bfa3e70f723747bcee`
- **patch** (`surviving-canary-patch.diff`): a 3-line new file `docs/canary-stabilization-marker.md`.
  This is the *synthetic* canary patch — it deliberately does not address
  job-state-consistency's real criteria, which is why the evaluator correctly
  returned `fail`. The value is proving transport + genuine judgment, not a pass.

## Receipts — duplicate-evaluation pair (input to concurrent-node-flow / Node 4)

Two receipts exist for this one job/attempt, both archived here:
- `job_20260724T010811130dd14802e579-attempt0.json` (50 KB)
- `job_20260724T010811130dd14802e579-attempt0-rerun1.json` (73 KB)

Both are genuine judgments (`lane_status: completed`, verdict `fail`, criteria
`fail`, integrity `contradicted`) — NOT harness crashes. The pair exists because
the launchd 5-minute heartbeat raced a manual runner over the same `collected`
session on 2026-07-23; both reconcilers ran evaluation. Benign here (identical
verdicts, single results row, doubled DeepSeek call), but it is direct evidence
that evaluation has no per-session claim/lock. Flagged as acceptance input for
`concurrent-node-flow`.

## Pre-flight gate finding (suite-green may spuriously fail)

At commit `cd7bc2d` in a clean detached worktree, `python3 -m pytest -q scripts/`
= **364 passed, 0 failed**. The evaluator's own receipt recorded
**"4 failed, 360 passed"** for the same `suite-green` criterion. The 4 failures
are therefore **environmental to the evaluator harness** (which also improvised
`python3` because the criterion's literal `.venv/bin/python` does not exist inside
worktrees), not defects in the tree under test. Consequence for the upcoming real
dispatch: `suite-green` can fail for reasons unrelated to the executor's fix, so
the A/B "expected pass" may be unreachable on that one criterion regardless of fix
quality. Executor agents should include their own pytest transcript in `decision.md`.
