# 129 — Pull integration and WIP preservation

------------------------------------------------ Agent Section START

Date: 2026-09-10
Worktree: /home/sab-mini/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

`main` fast-forwarded from `eb86b98` to `5af2d63`, then `ffdfd10` added the awaiting-result duplicate-dispatch guard in both scoped and legacy SQL branches. The active, enabled `gddp-heartbeat.timer` was held at 02:15:24 UTC; the installed unit still skips migration and live `db/queue.db` lacks `jobs.expected_base_commit_sha`, so a human decision is required before timer restart.

### Scope touched (One file per line, +/- for only what was changed)

+ scripts/runtime/heartbeat/scope_checker.py
+ scripts/runtime/heartbeat/test_claiming.py
+ scripts/runtime/heartbeat/test_scope_checker.py
+ .handoffs/129-git-integration-wip-preservation.md

### Constrained areas touched (none / list + justification)

Timer held only: graph YAML, runtime event `nav-input-repair`, and live DB contents remain unchanged. The timer was stopped after confirming the active unit and missing live schema column.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

`main` is pushed through `ffdfd10` (Co-authored-by: Pi + GPT-5). Inherited WIP is pushed at `origin/preservation/pre-pull-20260910` commit `1d63c78`; its export file SHA-256 is `e3d29a7ee094ac4570666e5dddbe86222a62abe98c8444eaa000b2d074915d23`.

### Artifacts (Filepath - Description, 1 line max per artifact)

/home/sab-mini/gddp-runtime-preservation/20260910T021230Z-pre-pull - checksummed tracked patches and archive of all original tracked/untracked paths
origin/preservation/pre-pull-20260910 - pushed WIP: schema/service/init_db/test/handoff and exact inherited export patch
/home/sab-mini/gddp-runtime-wip-preservation - WIP worktree; only generated `.tmp/` remains uncommitted there and is archived externally

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Review `1d63c78` before landing: `ensure_schema()` has zero callers, and WIP service startup changes require a separate schema decision. Before restarting the heartbeat, human chooses migration/stranded-event handling; use only the mini-heartbeat kit for any restart.

### Daily continuity takeaway (≤3 lines)

Preserve peer-owned runtime patches byte-for-byte before checkout integration.
Awaiting-result blocks dispatch in scoped and legacy jobs schemas at `ffdfd10`.
Heartbeat timer is deliberately held pending live schema and stranded-event operator decisions.

------------------------------------------------ Agent Section END
