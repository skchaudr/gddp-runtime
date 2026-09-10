# 130 — Cursor session-boundary correction

------------------------------------------------ Agent Section START

Date: 2026-09-10
Worktree: /home/sab-mini/gddp-runtime
Branch: main

## Empirical Reality

Sab reaffirmed one worktree per project session, each packet committed in that tree. Current pi_rpc already implements that lifetime; Cursor's per-attempt workspace, cold-default policy, and solo-only instructions remain implementation gaps.

## Scope touched

AGENTS.md — operator-correction pointer at the failure-pattern section.
docs/decisions/Cursor-project-session-boundary.md — governing direction, evidence, correction scope, graph placement.
docs/proposals/cursor-project-session-restoration.yaml — frontier-invisible implementation proposal; graph status reserved for human materialization.
docs/proposals/continuity-boundary.md — historical-policy banner.
docs/proposals/executor-capability-contract.md — historical-capability banner.
docs/proposals/architecture-review-cursor-cli-thin-driver.md — historical-review banner.
.handoffs/130-cursor-session-correction.md — resume point.

## Constrained areas touched

Documentation and proposal only. Runtime code, graph files, jobs, services, and executor configuration retain their previous state.

## Current Git state

Started clean and synchronized at f99e1b8 on main. This documentation slice is committed and pushed together; verify its hash with git log -1.

## Artifacts

Validation passed: proposal YAML round-trip, unique criterion IDs, human-owned status omission, new local links, cited source symbols, and git diff --check. Runtime validation belongs to the implementation proposal; this slice changes documentation only.

## Resume point

Human materialization of cursor-project-session-restoration supplies graph status before implementation. Start by reusing current pi_rpc session-worktree behavior and proving two packets yield distinct commits in one workspace; preserve work across failure cleanup and verify installed Cursor subagents/skill loading with the selected model and batch.

------------------------------------------------ Agent Section END
