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
- [ ] `project.yaml` SHA-256 baseline snapshot taken.
- [ ] Fresh-state reset procedure defined (delete canary job/session/result
  rows, remove `gddp/result-*` refs, prune worktrees).
- [ ] `GDDP_LOCAL_SUBPROCESS_ARGV` configured for a trivial script.

## Checklist

- [ ] **Phase 1 - snapshot + config:** hash `project.yaml`; define reset
  procedure; configure `LocalSubprocessAdapter`; pick the bounded node
  (`canary-retry-proof` or a new trivial node).
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
