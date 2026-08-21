# 104 — Job adoption primitive shipped; four myapi-part2 nodes adopted and evaluated

------------------------------------------------ Agent Section START

Date: 2026-08-21
Worktree: none (main)
Branch: main @ db38481 (pushed, clean; untracked `.factory/`/`.local/` only)

## Empirical Reality (2-3 sentences max)

`gddp jobs adopt` is implemented, merged, and pushed — a bake-off of two grok-4.6 workers (adopt-b/e0c6953 won; adopt-a/8acae96 was the contender), gddp-config forwarder already on origin. The four hand-built myapi-part2 commits were adopted and evaluated by the heartbeat: node-03 **pass**, node-07 **pass** (both provisional-flipped, committed `0d747dd` in gddp-config), node-05 **fail**, node-06 **fail**. All four adopted jobs sit `awaiting_review` with receipts in `gddp-config/verification/myapi-part2/`.

## Scope touched (One file per line, +/- for only what was changed)

- `scripts/runtime/heartbeat/adoption.py` (new, writer: 6 guards + 3 rows, one transaction)
- `scripts/runtime/heartbeat/test_adoption.py` (new, 11 tests incl. runner-activation e2e)
- `scripts/jobs_status.py` (`adopt` subparser + cmd_adopt)
- `.handoffs/103-job-adoption-primitive.md` (already corrected by Claude: repo constraint)

## Constrained areas touched (none / list + justification)

Runtime DB `db/queue.db`: cancelled 4 stale pi_rpc jobs + inserted 4 adopted jobs/sessions (operator-approved, handoff 103 application). Graph: node-03/node-07 `ready→provisional` — runtime-written frontier flips (designed mechanism), committed.

## Current Git state (2-3 sentences max)

gddp-runtime main db38481 pushed, 712 tests pass. gddp-config 0d747dd pushed. Merge of origin's docs-reorg/sweep work (31e9630) landed on top of the adoption merge; no conflicts.

## Artifacts (Filepath - Description, 1 line max per artifact)

- `gddp-config/verification/myapi-part2/node-05-inventory-handoffs/job_20260821T0932282911d48a6ff944-attempt0.json` — fail: manifest missing classification axes + 2 factual defects (would propagate to node-08)
- `gddp-config/verification/myapi-part2/node-06-git-evidence/job_20260821T093228438f68b4ace762-attempt0.json` — fail: reproducible criterion, `diff.algorithm=histogram` pinned nowhere (blocks node-09 R-2 gate)
- `gddp-config/verification/myapi-part2/node-03|node-07/*attempt0.json` — pass

## Resume point (2-3 sentences max)

Sab reviews the four `awaiting_review` verdicts (his call; verdicts are evidence, not graph truth). node-05/node-06 rework paths are concrete: pin `diff.algorithm=histogram` + refresh sha256 (node-06); add classification axes + fix census claims + template classification (node-05) — re-adopt the fix commits or re-run. Accepting node-03/node-07 unblocks node-08-build-source-layers + treatments 13/15/16 via the provisional frontier.

------------------------------------------------ Agent Section END
