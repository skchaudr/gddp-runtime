# 032 — Retry loop hardening + live dispatch

------------------------------------------------ Agent Section START

Date: 2026-07-11
Worktree: /Users/sab-mini/repos/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Hardened the retry loop in both directions (forward dispatch + return path) and completed a full live round trip: issue #90 → heartbeat dispatch → Jules executor → PR #92 (metadata block bridged, all artifacts present) → merge → return path fired → evaluator PASS (criteria 0.967, integrity 0.92) → job awaiting_review. The return path (merged PR → evaluator → retry) was wired into the heartbeat for the first time and is now proven live end-to-end.

### Scope touched (One file per line, +/- for only what was changed)

gddp-config/graphs/gddp-runtime/project.yaml — added retry_budget: 3 + allowed_repos
scripts/runtime/return_router.py — fixed attempt increment ordering, configurable repos, criteria_findings
scripts/runtime/verification/retry_budget.py — removed dead import, enhanced evidence checks, criteria lane
scripts/runtime/verification/cli.py — surface criteria_findings in CLI summary
scripts/adapters/jules_action_adapter.py — render Required Artifacts section, strengthen metadata block
scripts/runtime/heartbeat/runner.py — wire return path for merged PR events → handle_merged_pr
.github/workflows/jules.yml — new, Jules action (needs update to google-labs-code/jules-invoke@v1)
scripts/runtime/heartbeat/test_runner.py — new, return path wiring tests
scripts/runtime/test_return_router.py — redispatch + attempt ordering + repos tests
scripts/runtime/verification/test_retry_budget.py — criteria evidence + affected_node_ids tests
scripts/adapters/test_jules_action_adapter.py — artifacts rendering + metadata tests
scripts/runtime/test_full_cycle_e2e.py — updated patch target for ALLOWED_REPOS rename

### Constrained areas touched (none / list + justification)

docs/operator-practice/learn-split-axis-verdict.rs — pre-existing untracked file, not touched, not committed

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

gddp-runtime: main, synced with origin (HEAD 54a0196, includes PR #92 merge + Fable's e51e702 reconciliation). 250 tests pass. One pre-existing untracked file (docs/operator-practice/learn-split-axis-verdict.rs) left alone. gddp-config: main, synced with origin (HEAD d2e88cb). verification-runtime-live/ added to .gitignore (runtime state, not graph truth).

### Artifacts (Filepath - Description, 1 line max per artifact)

gddp-config/verification-runtime-live/gddp-runtime/verdict-confidence-split.json — live verdict receipt (PASS, criteria 0.967, integrity 0.92, all 7 criteria judged_pass)
GitHub issue #90 — trigger issue with node: verdict-confidence-split tag (closed)
GitHub issue #91 — executor dispatch issue, closed by PR #92 merge
GitHub PR #92 — Jules implementation, merged, metadata block + all 3 artifacts present
db/queue.db — job_20260711T16020485 status=awaiting_review, attempt=0, result res_20260711T1631577924
Cloudflared tunnel — https://alberta-states-risks-micro.trycloudflare.com → localhost:5050 (may have expired)
GitHub webhook 651704334 — on skchaudr/gddp-runtime, events: issues + pull_request

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Live round trip complete: verdict was PASS so retry loop was not exercised (correctly). To observe a live retry, dispatch a node likely to fail first attempt (e.g. a complex multi-file node). jules.yml workflow still references dead google/jules (404) — needs update to google-labs-code/jules-invoke@v1 with JULES_API_KEY secret, but Jules is running via CLI/App so not blocking. Intake server (PID 76956) and cloudflared tunnel (PID 77792) may need restart if session ended.

------------------------------------------------ Agent Section END
