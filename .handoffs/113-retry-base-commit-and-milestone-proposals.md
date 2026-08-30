# 113 — Retry base-commit bug confirmed; two milestone-graph proposals landed in gddp-config

Date: 2026-08-29
Worktree: /Users/sab-mini/repos/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Three read-only/planning agents ran: a retry-bug investigation (gddp-runtime, no code changes) and two opus-5-planner milestone-graph proposals (gddp-config, pushed: `fffcbca` agentos-dashboard + `3ebda99` pi-hub-projection). The retry bug is **confirmed** with two distinct divergence points; both proposal sets are frontier-invisible under `graphs/<project>/proposals/` awaiting operator review.

## Retry base-commit bug — investigation findings (no files changed; this is the only durable copy)

Verdict: confirmed. Worktree creation is faithful (`local_attempt.py:150-153` → `local_agent_executor.py:68-84`, `git worktree add --detach <sha>`); the base is wrong before it reaches git.

- Attempt-0 base is resolved at plan time (`runner.py:459`, chained `:465-468`), stored in-memory (`:526`) and durably only on the attempt-0 session row (`:538`). The `jobs` table has **no** `expected_base_commit_sha` column — the schema gap enables failure mode A.
- **Failure mode A (base captured too late):** `_handle_failed` computes retry base as `_get_head_sha(repo_path) or session[...]` — HEAD-first (`reconciler.py:1074`). Any HEAD movement since attempt 0 silently re-bases the retry. Present since `d396430` (2026-07-18).
- **Failure mode B (intentional stacking):** `_maybe_retry_evaluation` sets `retry_base = evaluated_commit_sha or result_commit_sha or HEAD or expected_base` (`reconciler.py:1422-1427`); human-reject retry same (`return_router.py:135`, `:285`). Docstring says deliberate — but it is the entanglement reported.
- `allocate_retry_attempt` overwrites job base with caller's value (`state_recorder.py:288`, `:297`); packet inherits (`dispatcher.py:429-432`). No branch-naming collision (per-attempt refs, guarded at `local_agent_executor.py:224-241`).
- Fix class: make original base authoritative — persist B0 on the `jobs` row (or read attempt-0 session row); `_handle_failed` should use recorded-base-first, never HEAD-first. For the evaluator/human path the contract is an **operator decision**: strict "same node, same base" (drop evaluated/result from retry_base) vs. intentional stacking renamed so it is not conflated with retry.
- Pinning test: extend `test_executor_sessions.py:1110` pattern — move HEAD after attempt 0, fail it, assert redispatched job + replacement session row carry base_sha. Fails today; existing "preserves_original" test can't catch it (fixture HEAD never leaves base).
- Adjacent risks: `previous_findings` overwritten not appended (`state_recorder.py:275`); `docs/proposals/continuity-boundary.md:65` claims plumbing retries redispatch from same base SHA — false under HEAD movement; engagement evaluation base uses `_parent_commit(result_sha)` fallback (`reconciler.py:779-782`) — multi-commit features shift eval base.

## Milestone proposals (gddp-config, pushed to origin/main)

- `graphs/pi-hub-projection/proposals/` (`3ebda99`): 6 milestones, extends existing graph. Key findings: "agent-observability" = the `agent/observability/` data plane in `~/.pi` (not a repo); **all 4 existing nodes passed evaluation but none of their code is on `main`** — six unmerged `gddp/result-*` refs, code force-added into gitignored `agent/observability/`, `pi-hub.db` stale since 2026-08-06. Milestone-02 (project canonical `ExecutorEvent` spool into hub db) is the highest-value new work. Open questions for operator: land milestone-01 by hand vs through graph; verify executor `session_id`→`gate_results` join before milestone-03.
- `graphs/agentos-dashboard/proposals/` (`fffcbca`): 7 milestones, **restructure** (not extension) of the 12-node chart. Existing chart not executable as written: no test runner in product repo, reality contact deferred to node 10, graph text already drifted (3 spec-vs-vault contradictions). Proposal front-loads live data at M2 = cheap kill point. Executor decision (`claude -p` vs pi vs dsh) is an explicit human gate at M5. Materialization is all-or-nothing per option (A replace / B overlay; planner recommends A).

## Scope touched

- gddp-runtime: `.handoffs/113-*.md` only (this file). Investigation was read-only.
- gddp-config: two new `proposals/` dirs (14 files total), committed by planners, pushed by integrator.
- Inherited gddp-config dirt left untouched (predates session): `M verification/vault-doctor/auth-node.json`, `?? verification/aa-cli-tui-pass/evaluations.yaml`.

## Constrained areas touched

None. No frozen surfaces. No `nodes/`, `project.yaml`, or status fields modified anywhere.

## Current Git state

- gddp-runtime: main, only this handoff added; pushed with it.
- gddp-config: main = origin/main at `3ebda99` (two planner commits on top of `e889c82`); two inherited dirty paths remain as found.

## Artifacts

- `graphs/pi-hub-projection/proposals/README.md` — hub cover doc + viability verdict (gddp-config)
- `graphs/agentos-dashboard/proposals/README.md` — dashboard cover doc + coverage map vs existing 12 nodes (gddp-config)
- `~/.cursor/agents/opus-5-planner.md` — reusable generic planner profile created this session

## Resume point

Operator reviews the two proposal READMEs and makes three decisions: (1) retry contract — strict same-base vs renamed stacking, then dispatch the fix + pinning test; (2) pi-hub milestone-01 — land by hand (planner's recommendation: probably faster) or dispatch through graph; (3) agentos materialization — option A (replace) vs B (overlay) vs decline. Before dispatching hub milestone-03, verify the `session_id`→`gate_results` join exists.
