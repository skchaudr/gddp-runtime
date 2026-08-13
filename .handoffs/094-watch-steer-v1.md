# 094 — gddp watch/steer v1 + MWP remap

------------------------------------------------ Agent Section START

Date: 2026-08-13
Worktree: main checkout (sab-mini), both repos
Branch: main, clean and synced with origin (both repos)

## What landed

1. `MWP-REMAP.md` (runtime `bbfdf63`) — post-demolition map of every top-level
   surface: core loop / justified support / freeze / archive. Ruling on record:
   keep this repo, do not start fresh. Follow-ups Sab has NOT yet approved:
   `LOOP.md`, archive sweep, freeze line in AGENTS.md.
2. Operator steer channel (runtime `57ca4ec`) — `pi_rpc_adapter.run_attempt`
   drains `attempt_dir/steer.jsonl` on its single reader thread (via new
   `on_poll` hook on `wait_agent_end`), delivers each line as an RPC
   `[operator steer]` prompt, and keeps collecting follow-up turns until a
   full agent_end passes with no operator input (bounded `_MAX_STEER_FOLLOWUPS=10`).
   Pure parser `_read_steer_messages` tested in
   `scripts/adapters/test_pi_rpc_steer.py` (5 tests). Full suite: 631 passed.
3. `gddp watch` / `gddp steer` (gddp-config `9c3166e`) — fleet view (node,
   state, age, live worktree diff `Nf +X/-Y`, last-write age, >3min quiet flag)
   and single-target view (header, live `git diff --stat` vs HEAD, untracked
   files, recent RPC events, completion banner). `steer` appends one JSON line
   to the attempt's `steer.jsonl`. Spool discovery: `GDDP_PI_RPC_SPOOL_DIR` →
   `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` → `runtime/jobs/local-subprocess-spool`.
   Smoke-tested against a fabricated attempt dir (fleet, single, steer append).

## Known limits (v1)

- Steer only lands on attempts launched by the NEW supervisor (running
  attempts from before `57ca4ec` never drain steer.jsonl; the file just sits).
- Follow-up wait assumes a steered prompt produces another agent_end; if a
  build consumes the steer in-turn, the follow-up wait burns until timeout —
  delayed collection, never lost work (first agent_end result persists after).
- watch is read-only except the single steer append; it cannot gate anything.

## Resume point

Sab to describe his actual workflows (per MWP-REMAP.md). When he does:
write `LOOP.md`, do the archive sweep, add the freeze line to AGENTS.md.
First live exercise of `gddp watch`/`steer` on a real armed run is still
unverified against production — smoke test only so far.

------------------------------------------------ Agent Section END
