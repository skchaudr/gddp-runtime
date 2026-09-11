# 131 — Persistent logical session and live reuse evidence

------------------------------------------------ Agent Section START

Date: 2026-09-10
Worktree: /home/sab-mini/gddp-runtime
Branch: main

## Empirical Reality

Sab clarified that one logical Cursor orchestrator session owns one worktree across many nodes and across start/stop/resume. Mini's preserved aa-cli-tui-pass artifacts show 12 attempts, five node IDs, and ten distinct recorded result commits referencing one worktree and one Pi session file on August 24–25.

## Scope touched

docs/decisions/Cursor-project-session-boundary.md — explicit process-independent lifetime, Pi cleanup gap, measured reuse evidence.
docs/proposals/cursor-project-session-restoration.yaml — logical-session restart acceptance criterion.
.handoffs/131-persistent-session-and-live-reuse-evidence.md — evidence and resume point.

## Constrained areas touched

Documentation and frontier-invisible proposal only; graph files, runtime code, services, and remote files retain their previous state.

## Current Git state

Started clean and synchronized at fc49b8e on main. Commit and push this documentation slice together; verify the resulting hash with git log -1.

## Artifacts

Mini verified via sab-mini@100.66.99.64: host/user sab-mini, home /Users/sab-mini. Alias mini failed DNS on this Linux host; the verified address succeeded.

Evidence root: /Users/sab-mini/repos/gddp-runtime/jobs/local-subprocess-spool/.
Shared checkout suffix: gddp-agent-wt-mf4i0xvw.
Shared session: _orchestrators/aa-cli-tui-pass/pi-session/2026-08-24T22-15-52-682Z_01a035d8-246a-7fbb-ad49-beec72119baf.jsonl.
Node attempt counts: review-product-coherence 4; tui-methodology-audit 2; milestone-integration 2; design-review 2; tui-inventory-and-keymap-audit 2.

## Resume point

The proposal remains outside graph discovery pending human materialization. Reuse Pi's demonstrated multi-packet behavior while changing its process-exit cleanup assumption for Cursor: prove stop/restart preserves logical session identity, conversation association, workspace path, prior commits, and recoverable edits before the next node's packet.

------------------------------------------------ Agent Section END
