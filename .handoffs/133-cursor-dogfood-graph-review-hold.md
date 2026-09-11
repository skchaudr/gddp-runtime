# 133 — Cursor dogfood graph drafts under peer review

------------------------------------------------ Agent Section START

Date: 2026-09-11
Worktree: /home/sab-mini/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Sab selected five concrete stages plus an open sixth and required simple capability-level acceptance criteria. Five frontier-invisible node drafts live in gddp-config/proposals/cursor-dogfood; an independent read-only reviewer is examining them, and implementation, dispatch and service changes are held until Sab approves the authored graph.

### Scope touched (One file per line, +/- for only what was changed)

~ docs/proposals/cursor-project-session-restoration.yaml
~ docs/proposals/cursor-session-startup-packets.yaml
+ .handoffs/133-cursor-dogfood-graph-review-hold.md

### Constrained areas touched (none / list + justification)

Planning documents only; active graph, runtime code, jobs and services retain their previous state.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

Started clean and synchronized at d4ff6fb on main. This commit checkpoints drafting work while peer review proceeds; graph materialization and execution remain separate steps.

### Artifacts (Filepath - Description, 1 line max per artifact)

- ../gddp-config/proposals/cursor-dogfood/ — five drafts with one criterion each; stage 6 deliberately remains open.
- docs/proposals/cursor-project-session-restoration.yaml — earlier seven-criterion draft simplified and matched to the new stage-1 node.
- docs/proposals/cursor-session-startup-packets.yaml — current Cursor path bootstraps stages 1–2; hooks precede the stage-3 batch of 2–3 selected nodes.
- reviewer d4e45e33-4115-4e93-8363-edbb11be421e — independent fresh-context read-only review; findings pending at checkpoint.
- Validation — both node validators reserve only human-supplied status; single-criterion shape, DAG, YAML round-trips, mirrored draft, gate and sources pass; git diff --check passes.

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Collect peer findings, apply bounded drafting corrections, and present the simple graph for Sab's review. Keep implementation, dispatch and service changes held until the authored graph is approved; acknowledge findings separately from resolving them or accepting nodes.

------------------------------------------------ Agent Section END
