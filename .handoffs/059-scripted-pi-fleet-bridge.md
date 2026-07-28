# 059 — Scripted Pi fleet bridge selected

------------------------------------------------ Agent Section START

Date: 2026-07-28
Worktree: `/Users/sab-mini/repos/gddp-runtime`
Branch: `main`

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

GDDP will govern node selection, the executor-neutral packet, immediate evaluation, and human review; `sab-orchestrate` will run one scripted Pi fleet per node. The fleet is a small Python chain of bounded `pi -p` stages—implement, independent review, and conditional repair—with optional `pi-boss` inside a stage rather than as the outer scheduler.

### Scope touched (One file per line, +/- for only what was changed)

- `.handoffs/059-scripted-pi-fleet-bridge.md` (+ cross-repo execution seam and resume point)

### Constrained areas touched (none / list + justification)

- None; no runtime source, database, job, queue, evaluator, or graph state was mutated in this repo.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

`main` began this handoff at `6475ee6`. Inherited generated changes in `.ua/knowledge-graph.json` and `.ua/meta.json` remain untouched and outside this handoff.

### Artifacts (Filepath - Description, 1 line max per artifact)

- `/Users/sab-mini/repos/sab-orchestrate/.handoffs/003-gddp-scripted-pi-fleet.md` - executor-side boundary and next implementation slice.
- `/Users/sab-mini/repos/gddp-config/graphs/sab-orchestrate/nodes/scripted-pi-fleet-canary.yaml` - ready one-node/one-fleet GDDP canary.

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Launch `scripted-pi-fleet-canary` through GDDP when Sab chooses the run configuration. The attempt must return fleet evidence and an evaluator receipt, then stop awaiting Sab's decision; only Sab changes graph truth.

------------------------------------------------ Agent Section END
