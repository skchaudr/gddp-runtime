# 098 — myapi-part2 graph authored, orchestrator preamble, loop activated

Date: 2026-08-15/16 · Branch: main (both repos, pushed) · Author: Pi + kimi-k3

## What landed

- **gddp-config `25f79ad` → `ace2b15`**: new graph `graphs/myapi-part2/` — 18 nodes from
  `docs/GDDPvMyAPI-Part2.md` (evidence contract → probe + concurrent source inventory →
  layers → validation → frozen ruler → 6 treatments → CLI gap-fill → convergence).
  `retry_budget: 3`, `max_concurrent_jobs: 5`, `frontier_auto_advance: true`, no human gates
  (Sab: full cascade; evaluator is signal, humans review the actual work at the end).
- **gddp-runtime `f0a6c6d`**: `_PACKET_PREAMBLE` in `scripts/adapters/pi_rpc_adapter.py`
  rewritten from worker framing ("implement its goal") to the orchestrator protocol —
  this is the byte-stable Zone A of every pi_rpc prompt (handoff 097), so orchestration
  is now structural, not per-node suggestion. 135 adapter/runner tests pass.
- **Executor quartet (Sab 2026-08-15)**: main `openai-codex/gpt-5.6-sol` orchestrates ONLY;
  ≤5 workers `xai/grok-4.6`; ONE watcher `deepseek/deepseek-v4-flash` (replaces polling);
  parallel reviewers `deepseek/deepseek-v4-pro`, each a distinct focus.
- **~/.pi/agent/models.json**: `deepseek` provider re-keyed from `pass api/deepseek`
  (old key had trailing newline, auth-failed); models `deepseek-v4-pro` + `deepseek-v4-flash`
  added (1M ctx, pricing from OpenRouter listing).

## Activation mechanics (reusable)

- New graphs are invisible to the heartbeat: `_active_projects()` needs an existing
  event/job/session. Bootstrap = ONE frontier hop, run with kit env:
  `source deploy/mini-heartbeat/env/gddp.env && PYTHONPATH=scripts python3 -c
  "from runtime.heartbeat.runner import connect; from runtime.heartbeat.graph_reader import GraphReader; from runtime.heartbeat.frontier import advance_frontier; import os; advance_frontier(connect(), GraphReader(os.environ['GDDP_CONFIG_PATH']), '<project>')"`
  → flips dep-free pending nodes to ready + injects dispatch events. After that the
  loop is self-sustaining. `gddp <node>` positional dispatch refuses `pending` nodes.
- `human_gate` defaults to FALSE everywhere (code checks `is True`); verified, no toggle needed.

## Resume point

- node-01-evidence-contract dispatched 2026-08-16 07:32 UTC, job `169ef51e46057c`, running.
- Watch: `~/bin/gddp watch` · steer: `~/bin/gddp steer` · receipts: `~/bin/gddp evaluations`.
- Next: evaluator verdict on node-01 → provisional → frontier unlocks node-02..07 layer.

## Open follow-ups

- Handoff 097 zone reorder (volatile keys out of NodePacket JSON head) NOT done — bigger
  refactor, proposed only. Prefix caching works today only on the shared preamble prefix.
- Old deferred events (pi-harness-execution node-04/08) still recycle each tick; pre-existing.

## Update 2026-08-16 ~09:20 UTC — node-01b amendment + reconciler fix

- node-01 passed at 1,179 lines / 39-field mandatory envelope → Sab directed graph
  amendment (NOT retry): new `node-01b-contract-review` (gddp-config `5c5123a`) reviews
  the contract for over-complexity (lens: docs/decisions/Overengineering-and-downstream-
  consequences.md) and revises to <=300 lines / <=12 required fields, rationale preserved.
  02–07 rewired behind 01b, back to pending; auto-dispatch when 01b goes provisional.
- **Runtime bug found + fixed (`dc136dd`)**: reconciler `_handle_failed` resurrected
  operator-cancelled jobs as plumbing retries (never consulted queue_state). Cancelling
  a running job required: `jobs set cancelled` + SIGTERM pid (attempt-dir pid file in
  jobs/local-subprocess-spool/) + `UPDATE executor_sessions SET state='failed'` — else
  next tick redispatches. Patch makes cancelled terminal; 176 tests pass.
- Cancel also raced the tick once: cancel jobs AND flip nodes to pending BEFORE the next
  tick, or the ready-node planner re-dispatches in the gap.
- node-06's cancelled attempt produced an EMPTY result tree (5d714e9) — flagged as a
  consumability data point for 01b's review.
- Watcher: medic fleet runs as 8 sequential 20-min deepseek-v4-flash shifts via
  workflowScript composite (single async runs cap at 30 min regardless of timeoutMs).
- **01b result-review lens (advisor, via Sab)**: <=300 lines / <=12 fields are CEILINGS,
  not targets. Watch for gaming: exactly-300-line compression, overloaded compound
  fields smuggling the 39 back in, mandatory rationale cross-references that keep the
  fat doc load-bearing, renamed compatibility machinery. Success = consumer-backed
  necessity; empirical test is whether resumed 02–09 become materially simpler.

## Final state 2026-08-16 ~11:30 UTC

- Spawn accounting for the run: 22 orchestrator spawns across 8 nodes; 12 of 22
  exited via SIGTERM (exit 143) before agent_end. 8 of the 12 were manual kills
  during the halt, racing the reconciler resurrection bug (fixed in dc136dd).
  Each kill registered as a crash and triggered re-dispatch with a cold
  gpt-5.6-sol session. Codex usage limit hit; lane unavailable ~4 days.
- Facts on record: pi_rpc adapter spawns per attempt and kills the process at
  agent_end (finally block); the RPC protocol supports multi-turn persistence,
  unused by the adapter (same gap noted 2026-08-14, session 01a00212).
  max_concurrent_jobs was 5 on the Codex lane. No dispatch-time visibility of
  session count × model at the time; OBS tagging added in 07f7111/b5fc1a4.
- Minimal persistent-executor change scoped but NOT approved/started: adapter
  drops the end-of-attempt kill and waits on a packet inbox; dispatcher reuses
  an idle live session before spawning.
- Open items: orchestrator model for retries undecided (Codex out ~4 days);
  Khoj answer-path LLM key undecided (blocks node-02 and treatments); node-07
  job row says running but session is dead; 02/03/05/06 failed awaiting_review.
- Graph: node-01/01b provisional, node-04 passed, 08–18 pending. Repos clean,
  pushed. Watcher fleet stopped; nothing running.
