# 046 — Evaluator Hardening Merged + P2 Cleanup

------------------------------------------------ Agent Section START

Date: 2026-07-17
Worktree: /Users/sab-mini/repos/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Evaluator hardening branch merged to main at `39ad57c` (merge) / `08fbf2a` (branch tip). Five P2 issues found through two-agent review (Codex found+fixed, Factory verified): provenance tree-vs-commit SHA mismatch, failed reads inflating coverage, TIMED_OUT unreachable, lane status missing from summary, receipt overwrite on rerun. Two regressions caught in Codex self-review (timeout orphan, legacy receipt collision) and fixed before merge. Post-merge: fetch-before-worktree fix (`6bb931e`), built-in agent fallback removed (`0ac5067`), pi log cleanup + subprocess dedup (`e35f93c`). 307 tests pass.

### Scope touched (One file per line, +/- for only what was changed)

+ scripts/runtime/verification/bridge.py — provenance pinning, worktree lifecycle, fetch-before-add, timeout budget
+ scripts/runtime/verification/cli.py — provenance/coverage/lane-status in operator summary
+ scripts/runtime/verification/orchestrator.py — provenance capture, coverage computation, built-in agent fallback removed (pi-only)
+ scripts/runtime/verification/receipt_sink.py — per-attempt receipts, collision avoidance scoped to job-attempt only
+ scripts/runtime/verification/schemas.py — LaneExecutionStatus, GraphObservation, ContextCoverage, provenance fields
+ scripts/runtime/verification/semantic/integrity_runner.py — typed liveness, tee subprocess, log cleanup, canonical context
+ scripts/runtime/verification/semantic/pi_runner.py — typed liveness, tee subprocess, log cleanup, timeout/process-group kill
+ scripts/runtime/verification/semantic/subprocess_utils.py — shared helpers extracted from both runners (new)
+ scripts/runtime/verification/semantic/timeouts.py — shared timeout budget constants (new)
+ scripts/runtime/verification/semantic/pi_harness/gddp_integrity.ts — graph_observations schema
+ scripts/runtime/verification/semantic/pi_harness/gddp_verifier_guard.ts — tool trace path logging
+ scripts/runtime/verification/test_bridge.py — provenance passthrough, worktree lifecycle, fetch-ordering tests
+ scripts/runtime/verification/test_graded_cases.py — 5 executable graded cases (new)
+ scripts/runtime/verification/test_receipt_sink.py — per-attempt receipt tests (new)
+ scripts/runtime/verification/test_orchestrator.py — coverage computation, pi-only harness tests
+ scripts/runtime/verification/test_integrity_runner.py — typed liveness, log cleanup tests
+ scripts/runtime/verification/test_schemas.py — provenance field round-trip tests
+ scripts/runtime/verification/test_cli.py — receipt contract fields with mock harness
+ scripts/runtime/return_router.py — merge_commit_sha passthrough to evaluator
+ scripts/runtime/test_return_router.py — provenance+attempt passthrough assertion
+ scripts/node_status.py — provenance display (commit-to-commit match), coverage display, graph observations
+ scripts/test_node_status_evaluator.py — evaluator provenance display test (new)
+ docs/current-mission-definition-of-done.md — crash recovery and evaluator hardening marked complete

### Constrained areas touched (none / list + justification)

Live launchd drill on sab-mini (PR #107): intake plist armed with KeepAlive=true, PID killed, launchd respawn verified, events unchanged, restored to dormant. No DB writes, no graph changes, no heartbeat tick. Evaluator hardening: no graph truth changed, no node status modified by any agent.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

Main is clean and synced with origin/main at `0ac5067`. 307 tests pass. PR #107 and #108 remain on their branches, unmerged. `.agent/` and `WARP.md` are pre-existing untracked files, not task artifacts.

### Artifacts (Filepath - Description, 1 line max per artifact)

/Users/sab-mini/.factory/specs/2026-07-16-gddp-evaluator-hardening-specification-v5.md — updated: tree-vs-commit invariant corrected to commit-to-commit
/private/tmp/gddp-pr107-review/.handoffs/045-live-crash-recovery-evidence.md — live drill evidence on PR #107 branch
~/Library/Logs/gddp-intake.log — two /health 200 responses at 22:29:29 and 22:29:49 proving crash recovery

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Evaluator hardening is merged and P2 debt is closed. Next discussion: (1) concurrent evaluation workers so a single evaluator run doesn't block other return events, (2) Jules executor architecture and whether a second remote async executor is worth building, (3) PR #107/#108 merge decisions. No uncommitted work remains.

### Session Detail (for context, not archaeology)

**What was merged:**
- `39ad57c` Merge of evaluator-hardening branch (P1: provenance, coverage, liveness, graph observations)
- `08fbf2a` P2 repair pass (5 issues fixed, 2 regressions caught and fixed)
- `6bb931e` Fetch origin before worktree add (was a merge blocker: evaluator produced no verdict without local commit)
- `e35f93c` Pi log cleanup (delete on success, preserve+link on failure) + subprocess helper dedup (extracted to subprocess_utils.py)
- `0ac5067` Built-in agent fallback removed (pi-only, hard-fail if no harness) + 6 tests fixed to use mock pi harness

**What was the live drill (PR #107):**
- `dfbfc6c` on PR #107 branch: PID 46896 killed, PID 46948 respawned by launchd KeepAlive, /health 200 on both, event hash unchanged (28/6), heartbeat never armed, restored to dormant
- `b934833` on main: mission checklist crash recovery marked complete

**P2 compromises now closed:**
1. Built-in agent fallback — removed, pi is the only path
2. Code duplication (~80 lines) — extracted to subprocess_utils.py
3. v5 spec stale tree-vs-commit wording — corrected to commit-to-commit invariant
4. Pi log accumulation — cleaned up on success, preserved with paths on failure

**Accepted tradeoffs (not debt):**
- 42-minute timeout ceiling (2 * 1200s lanes + 120s cleanup)
- -rerunN receipts discovered through returned receipt_path (legacy node-only callers overwrite normally)
- Historical traces remain incomplete (unrepairable, only affects old receipts)
- 20-minute per-lane ceiling

**Deferred scaling work (from Codex's final review):**
- Concurrent evaluation workers (current: sequential, one slow eval blocks later return events)
- Latest-receipt index/comparison tool
- Dynamic time budgets based on graph size and node risk
- One real Pi/DeepSeek canary (pre-merge gate, not yet run)
- One missing-local-commit test through complete return path

**Concurrency insight from Codex:**
The DAG does not prevent concurrent evaluation. The current implementation does. The heartbeat loops through returned events and calls the evaluator synchronously. Separate processes could evaluate independent jobs concurrently, tied to job_id + attempt + commit, independently stoppable, safe to complete out of order.

------------------------------------------------ Agent Section END

------------------------ Do NOT edit this file past this point

## Narrative / Trajectory (SAB ONLY)

### Intent going into/at start of session

### Interpretation of how the session went

### Friction experienced or anticipated

### What's Next (Momentum or Lack Thereof)
