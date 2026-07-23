# Node 2 Direct-Executor Stabilization — 2026-07-23

Date: 2026-07-23

## Outcome

Prove `direct-executor-round-trip` via a repeatable stabilization loop, not one
canary. GDDP remains the intent and graph-integrity layer; only Sab changes
graph truth.

## Frame

5-node hardening plan, same stabilization discipline per node, in dependency
order: `neutral-executor-contract` -> `direct-executor-round-trip` ->
`immediate-evaluator-round-trip` -> `concurrent-node-flow` ->
`graph-frontier-operations`. Node 1 code merged to main as inherited
infrastructure (`36cd93b`); node itself is `deferred`, not accepted. Node 2 is
the next real work.

## Proof bar (not one clean run)

- [ ] 3 consecutive clean fresh runs: dispatch -> poll -> collect -> worktree
  apply -> commit -> durable git ref -> evaluate -> `awaiting_review`
- [ ] 1 controlled interruption/retry cycle: kill subprocess mid-run -> stale
  recovery -> retry allocation -> retry completes -> both attempts visible
- [ ] No hidden state or manual DB/file repair in any clean run
- [ ] Every run stops at `awaiting_review` (never `complete`, never stuck
  `running`)
- [ ] `gddp-config/graphs/gddp-runtime/project.yaml` SHA-256 unchanged across
  every run

On any failure: inspect -> patch smallest responsible part -> rerun the
failing step, then the full fresh run -> log the patch as a corrective-node
candidate. Clean-run counter resets to 0 on any patch. Capped at 10 iterations
total.

## Setup (base state, already done as of 2026-07-23)

- [x] `feat/capability-spine@1539921` merged into `gddp-runtime` main
  (`36cd93b`) as inherited infra, not node acceptance. 373 tests pass.
- [x] `neutral-executor-contract` set to `deferred` in `gddp-config`
  (`9ea58ee`). Sab's edit, Sab's decision.
- [x] 3 orphaned pre-session-tracking jobs triaged to `failed`
  (pi-evaluator-harness, job-state-consistency, heartbeat-crash-recovery).
- [x] Stray noise removed (`package-lock.json` gitignored).
- [x] `project.yaml` SHA-256 baseline:
  `781c626a8ceee8e7942afcd3b97118be5948157427c5d0e16bb6a49180207b8a`
  (taken 2026-07-23, before any Phase 2 dispatch).
- [x] Fresh-state reset procedure: `scripts/canary_stabilization_reset.py
  <job_id>` — deletes exactly that job's `results`/`executor_sessions`/
  `queue_records`/`jobs`/`events` rows and its `gddp/result-*` ref, prunes
  worktrees. Never touches canary-retry-proof's pre-existing real evidence
  (`job_20260711T16542651`, `job_20260711T17104259` — left alone permanently).
- [x] `GDDP_LOCAL_SUBPROCESS_ARGV` target: `scripts/canary_local_executor.py`
  — emits a fixed, pre-validated unified diff creating
  `docs/canary-stabilization-marker.md` (a new path, not a real deliverable —
  echo.py/echo-usage.md already exist from the 2026-07-11 real attempt, so a
  repeatable "new file" diff must target something that never existed at
  base). Diff verified with `git apply --check` in a scratch worktree.
- [x] Bounded node: `canary-retry-proof` (already `ready`, no gddp-config
  edit needed). Executor forced to the direct path via
  `GDDP_EXECUTOR_OVERRIDE=local_subprocess` (documented override in
  `dispatcher.py`, does not touch graph truth). Spool root:
  `.gddp-canary-spool/` (gitignored).

## Checklist

- [x] **Phase 1 - snapshot + config:** done, see Setup above.
- [x] **Phase 2A - fresh run x3:** done 2026-07-23. Run #1 surfaced a real bug
  (see Bug found below), fixed and committed (`7756a36`), which reset the
  clean-run counter to zero per our own rule. Runs #1-#3 post-fix all
  completed cleanly in exactly 2 ticks each (dispatch, reconcile), reaching
  `awaiting_review` with an unchanged `project.yaml` hash. See
  `.handoffs/052-node2-stabilization-loop-evidence.md` for full per-run
  evidence (job_ids, session_ids, receipts).
- [x] **Phase 2B - interruption x1:** done 2026-07-23. Killed the executor
  subprocess mid-execution (SIGTERM, not the adapter's graceful cancel) on a
  slow variant script. Reconciler detected `failed`, automatically allocated
  and dispatched a retry (attempt 1) in the same tick, preserving attempt 0's
  row (`state=failed`, error recorded) — both attempts visible in
  `executor_sessions` under one `job_id`. Retry completed to `awaiting_review`
  on the next tick. Hash unchanged throughout.
- [x] **Bug found and fixed:** `get_active_executor_sessions` never
  re-polled sessions stuck at `state=collected` (interrupted between
  collect/commit and evaluate), permanently stranding the job in `running`
  with no results row. Fixed in `7756a36`: `collected` is now polled, and
  `_reconcile_one` resumes straight to evaluation using the already-recorded
  `result_commit_sha` instead of wastefully re-collecting. 373/373 tests pass.
- [x] **Phase 3 - forensic evidence:** recorded in
  `.handoffs/052-node2-stabilization-loop-evidence.md`.
- [x] **Corrective nodes:** none needed beyond the fix above — it was small
  enough to land directly, tested, during stabilization rather than deferred.

## Mission Complete

3 consecutive clean fresh runs (post-fix) plus 1 clean interruption/retry
cycle proven, 2026-07-23. No manual DB/file repair in any of the 3 counted
clean runs. Every run stopped at `awaiting_review`. `project.yaml` hash
(`781c626a...80207b8a`) unchanged across all runs, including the one that
surfaced and fixed the `collected`-stranding bug. Full evidence in
`.handoffs/052-node2-stabilization-loop-evidence.md`. Sab reviews and decides
whether this satisfies `direct-executor-round-trip`'s acceptance criteria.
