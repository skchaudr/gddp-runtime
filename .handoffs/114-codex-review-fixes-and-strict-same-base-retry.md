# 114 — Codex review fixes (4 findings) + strict same-base retry contract

Date: 2026-08-30
Worktree: /Users/sab-mini/repos/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Three lanes executed against the Codex review of the three-lane integration plus the confirmed retry base-commit bug (handoff 113). All four review findings are fixed and the strict same-base retry contract is now enforced in code. main = `a5926b6`, 870 passed (864 pre-wave + 6 new), pushed; gddp-config = `e07987c` (steer gating), pushed.

## What landed

**Lane B (grok-4.6-worker, merged `e72f389`)** — blocker: failed Cursor turns reported success.
- Classification is stream-shaped, not `is_error`-blunt, per operator doctrine ("agent crashed at the end, no big deal"): `result`/`subtype=success` = completed work; a later crash or nonzero exit after it = `completed` + `warning` on `turn_ended`; any other `result` (e.g. `subtype=error`) = failure; no `result` = synthesized failed/cancelled (unchanged).
- Executor-neutral backstop in `local_attempt.py`: last canonical `turn_ended status=failed` ⇒ failure `exit.json`, no persist, regardless of `TurnOutcome.returncode`.
- `executor_events.py`: `turn_ended` gained a `warning` field.
- Open risk recorded: a real provider-failure `result` event remains unobserved (spike `open_risks`); classification of that shape rests on the `{subtype:"error", is_error:true}` test fixture.

**Lane C (composer-2.5-worker, `e55df05` runtime + `e07987c` config)** — three smalls.
- `continuity_policy.py`: `consume_resume_request()` — one marker = exactly one resumed attempt; negative paths unchanged.
- `dispatcher.py`: legacy `dispatch(packet)` bypass deleted; ALL adapters get `_reserve_attempt` + `(packet, *, attempt, continuity)`; `attempt_root()` added to legacy adapters (local_subprocess, jules_api, mission, jules_action).
- gddp-config `gddp.py cmd_steer`: reads attempt `capabilities.json`; refuses when `midturn_steering` isn't true (names executor); missing file = honest unknown-capability message; steer-capable unchanged.

**Lane A (opus-5-worker, merged `fd5699c`)** — strict same-base retry.
- `init_db.py`: `jobs.expected_base_commit_sha` via existing `_ensure_column` pattern (additive, nullable, no backfill).
- `state_recorder.py`: `recorded_base_commit_sha(con, job_id)` is the single choke point (jobs row → attempt-0 session row, swallows `OperationalError` for pre-column databases); both retry allocation paths fall back to it — no path reaches HEAD while a base is recorded.
- `reconciler.py` + `return_router.py`: evaluator/human retry paths no longer stack on `evaluated_commit_sha`/`result_commit_sha`; retry = same node, same base. Stacking is continuation-proposal territory.
- 6 new pinning tests, each verified to fail against the old behavior (not tautologies).
- Path corrections vs the investigation brief: `init_db.py` = `scripts/init_db.py`; `return_router.py` = `scripts/runtime/return_router.py`.

## Scope touched

gddp-runtime: `scripts/init_db.py`, `scripts/runtime/heartbeat/{state_recorder,reconciler,adoption,continuity_policy,dispatcher}.py`, `scripts/runtime/{return_router,local_attempt}.py`, `scripts/adapters/{cursor_cli_adapter,events_cursor_cli,executor_events,local_subprocess_adapter,jules_api_adapter,mission_adapter,jules_action_adapter}.py`, `docs/proposals/continuity-boundary.md`, + test files. gddp-config: `scripts/gddp.py` (cmd_steer only).

## Constrained areas touched

None. No frozen surfaces.

## Current Git state

- gddp-runtime: main = origin/main = `a5926b6` (C direct on main + B merge + A merge). Wave worktrees/branches removed. Untracked locals unchanged (`.atuin/`, `.factory/`, `.local/`, `node_status_history/aa-cli-tui-pass/`).
- gddp-config: main = origin/main = `e07987c`. Inherited dirt remains as found: `M verification/vault-doctor/auth-node.json`, `?? verification/aa-cli-tui-pass/evaluations.yaml`.

## Residuals / resume point

- Codex review item 5 (Pi/local_subprocess not adopted onto `local_attempt`) deliberately deferred — architectural, needs the session-scoped seam care noted in handoff 112.
- `docs/proposals/continuity-boundary.md` rows 4/5/14 cite `state_recorder.py` line numbers now stale by ~50 lines (Lane A corrected only the row-13 sentence per spec).
- Still open from 113: `previous_findings` overwrite-not-append (`state_recorder.py:327`); engagement eval base via `_parent_commit(result_sha)` (`reconciler.py:779-782`).
- Provider-failure cursor stream shape unobserved — next live provider error should be captured as a fixture to confirm Lane B's classification.
- Operator decisions still open from 113: pi-hub milestone-01 landing route; agentos materialization (A/B/decline); verify `session_id`→`gate_results` join before hub milestone-03.
