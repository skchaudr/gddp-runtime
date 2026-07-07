# Task: implement the integrity lane (fresh-eyes drift review)

You are on branch integrity-lane-draft in /home/sab/gddp-runtime-integrity (a git
worktree). The skeletons are already committed — read them first, in this order:

1. .handoffs/artifacts/integrity-lane-walkthrough.md (the map)
2. scripts/runtime/verification/schemas.py (IntegrityOutput, receipt fields)
3. scripts/runtime/verification/integrity_combiner.py (the combine rule — do not change it)
4. scripts/runtime/verification/orchestrator.py (integrity_harness hook)
5. scripts/runtime/verification/semantic/pi_harness/gddp_integrity.ts (tool skeleton)

Reference implementations to mirror (same repo, proven live):
- gddp_verifier.ts — how to register a terminal tool, validate, write $..._OUT, terminate
- scripts/runtime/verification/semantic/pi_runner.py — how to spawn pi --print with an
  extension, HOME tempdir sandbox, guard, trace, read the verdict file back

## Deliverables (commit each as its own conventional commit on this branch)

1. Complete gddp_integrity.ts: register submit_integrity_verdict per the skeleton
   schema; force required_human_review=true for any non-pass verdict; write payload
   to $GDDP_INTEGRITY_OUT; terminate:true. Guard contract identical to gddp_verifier.ts.
2. scripts/runtime/verification/semantic/integrity_runner.py: sibling of pi_runner.py.
   Spawns pi with gddp_integrity.ts loaded and an integrity-specific system prompt.
   The prompt's mandate: fresh-eyes review — given the node's why, constraints,
   depends_on/unlocks neighbor YAML, and the work under review, does the change
   preserve the node's intended role in the project? It is NOT re-adjudicating
   acceptance criteria (that is lane 1's job). Returns IntegrityOutput.
3. Wire-through: cli.py gains --integrity {on,off} (default off for now; the bridge
   flips it on later — do NOT touch bridge.py in this task). When on, cli builds an
   integrity_harness from integrity_runner and passes it to orchestrator.verify.
4. Tests: unit tests for the combiner floors; an orchestrator test proving integrity
   runs even when all deterministic criteria pass (row-12 case); the node-mandated
   fixture: criteria all pass but intent violated -> receipt verdict is non-pass with
   required_human_review true. Mock pi (no live calls). Full suite green:
   /home/sab/gddp-runtime/.venv/bin/python -m pytest -q scripts/

## Constraints

- Do not modify: integrity_combiner.py rules, decision_engine.py, the 12-row matrix,
  bridge.py, anything under /home/sab/gddp-config.
- Vocabulary is fixed by the evaluator-intent-integrity-verdict node YAML — invent no
  new terms, states, or fields.
- Match existing style. No speculative features.
- Never print secret values. No pushes — commit locally only; review happens before push.
