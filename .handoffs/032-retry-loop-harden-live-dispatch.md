# 032 — Retry loop hardening + live dispatch

------------------------------------------------ Agent Section START

Date: 2026-07-11
Worktree: /Users/sab-mini/repos/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Hardened the retry loop in both directions (forward dispatch + return path) and kicked off a live dispatch against the gddp-runtime graph. Jules is currently working on dispatched issue #91. The return path (merged PR → evaluator → retry) is wired into the heartbeat for the first time. Infrastructure (intake server, cloudflared tunnel, GitHub webhook) is live on sab-mini.

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

gddp-runtime: main, pushed to origin (commit f60e6de). 242 tests pass. One pre-existing untracked file (docs/operator-practice/learn-split-axis-verdict.rs) left alone. gddp-config: main, pushed to origin (commit d2e88cb). Pre-existing graphify-out staged files left unstaged.

### Artifacts (Filepath - Description, 1 line max per artifact)

db/queue.db — live SQLite DB with job_20260711T16020485 (status=running, attempt=0, node=verdict-confidence-split)
GitHub issue #90 — trigger issue with node: verdict-confidence-split tag
GitHub issue #91 — executor dispatch issue with jules label, Required Artifacts section, metadata block
Cloudflared tunnel — https://alberta-states-risks-micro.trycloudflare.com → localhost:5050 (intake server)
GitHub webhook 651704334 — on skchaudr/gddp-runtime, events: issues + pull_request, pointing to tunnel

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Jules is working on issue #91. When it opens a PR: verify the PR body includes the node:/job: metadata block (the trust gap). When the PR merges: the webhook fires → intake server → SQLite event → next heartbeat run processes the return path (handle_merged_pr → evaluator with integrity ON → should_retry → redispatch or awaiting_review). The jules.yml workflow needs updating from google/jules (dead 404) to google-labs-code/jules-invoke@v1 with a JULES_API_KEY secret — but Jules is running via a different mechanism (CLI/GitHub App) so this is not blocking the current live loop.

------------------------------------------------ Agent Section END
