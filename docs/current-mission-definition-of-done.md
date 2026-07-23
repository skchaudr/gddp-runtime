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
- [ ] **Phase 2A - fresh run x3:** reset -> inject event -> heartbeat plans +
  reserves attempt -> dispatch -> reconcile polls/collects -> worktree
  apply/commit -> durable ref -> evaluate -> `awaiting_review` -> hash check.
  Repeat until 3 consecutive clean.
- [ ] **Phase 2B - interruption x1:** kill subprocess mid-run -> stale-session
  recovery -> retry attempt allocated (original attempt preserved) -> retry
  completes clean.
- [ ] **Phase 3 - forensic evidence:** attempt-identity trace (event -> job ->
  execution_attempt_id -> session -> result -> receipt), per-run receipt +
  patch + git ref, stabilization log (what broke, what was patched).
- [ ] **Corrective nodes:** any patch applied during stabilization becomes a
  named corrective-node candidate, not a silent fix.

## Mission Complete

3 consecutive clean fresh runs plus 1 clean interruption/retry cycle proven;
no manual repair in any of them; every run stopped at `awaiting_review`;
`project.yaml` hash unchanged throughout; stabilization log and corrective-node
candidates (if any) recorded; Sab reviews and decides Node 2's status.
