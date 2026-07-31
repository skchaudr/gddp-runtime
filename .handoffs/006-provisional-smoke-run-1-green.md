# Handoff 006 — Provisional flow + base-chaining proven end-to-end (smoke run 1)

Date: 2026-07-31 (00:30 PDT) · Branch: main (both repos, clean + synced)

## Agent Section

### What happened
Smoke run 1 (`gate-continuation-smoke-a` → `gate-continuation-smoke-b`, test-project,
local_subprocess, grok-cli/grok-4.5 executor) completed the full provisional chain:

1. A dispatched via `gddp <node-id>` (positional dispatch, gddp.py — no new CLI needed)
2. A executed (grok-4.5), evaluator passed → reconciler wrote `provisional`
3. B marked ready by human (dep satisfied, but readiness stays human-owned)
4. B dispatched; runner base-chained: `B.expected_base = A.result = 77ba473`
5. B's worktree inherited `a.txt`, added `b.txt`; bounded diff (1 file, +1 line)
6. B evaluated pass → provisional

### Bugs the smoke surfaced (all fixed, pushed)
- `74fe53d` — evaluator dep gate: decision_engine matrix row 1 + orchestrator
  `_should_run_semantic` hard-coded deps to `complete`; widened to
  `SATISFIED_DEP_STATUSES = {complete, provisional}` (3rd gate location;
  frontier.py + scope_checker.py were widened in earlier commits)
- `6bf5a41` — `_active_projects` ignored active executor sessions; an
  awaiting_review job with a collected session made the project invisible to
  `--all-active` ("No active projects" stall). Union now includes sessions in
  dispatched/running/needs_operator/collected.
- Stale cleanup: canary job `job_20260711T16542651` had status=failed but
  queue_state=running, eating test-project capacity (fixed via jobs_status.py);
  old July 11 event `evt_20260711T1654288582` marked ignored (no node tag).
- Deterministic lane keyword-scan can't see `.txt` markers ("(no files)") —
  semantic lane carries the judgment. Pre-existing evaluator weakness, not
  fixed; worth a follow-up node if it bites real work.

### Git state
- gddp-runtime: `6bf5a41` (HEAD == origin/main), 452 tests passing
- gddp-config: `ad017b1` (HEAD == origin/main), 129 tests passing
- test-project: result refs `gddp/attempt-*` for A (77ba473) and B (0deaab2);
  main untouched (human merge is the acceptance act)
- Untracked `.pi-subagents/` in gddp-config is Pi delegation scratch — ignore
  or gitignore.

### Operational notes
- Heartbeat armed via `arm.sh` (plist now sources gddp.env; executor model
  grok-cli/grok-4.5). Codex's inlined-ARGV plist was replaced by the kit render.
- Re-evaluation trick: set session state to `collected` via
  state_recorder.update_executor_session_state; next tick resumes evaluation
  from the durable result commit (no re-execution). Now works because of 6bf5a41.
- `gddp dispatch <node>` as a command does NOT exist; positional `gddp <node-id>`
  is the dispatch path (inserts issue.opened-shaped manual_inject event).
- B-ready was a human graph action; provisional on A only satisfies the dep,
  not B's own readiness. Design is correct.

### Resume point
Run 2 (jules_api executor) is the optional next proof: purge smoke jobs/events,
reset A/B to ready/pending, set `allowed_execution_modes: [jules_api]`,
re-dispatch A. Both nodes currently sit `provisional` awaiting Sab's review —
accept/reject is his call via the interactive UI.
