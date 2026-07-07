# Walkthrough: integrity-lane-draft branch

How to review: `git checkout integrity-lane-draft`, then walk the 4 commits in
order (`git log --oneline main..integrity-lane-draft`). Each commit is ONE
design decision at its real location. Review in Zed with the diff view, or
`git diff main -- <file>` per file. All 149 tests pass on the branch — every
skeleton is inert until wired, so checking this out risks nothing.

## Finding you should see first

The graph already owns the vocabulary. The node
`gddp-config/graphs/gddp-runtime/nodes/evaluator-intent-integrity-verdict.yaml`
(pending, depends on pi-evaluator-guard) defines: verdict
`pass|block|drift|insufficient|contradicted|unknown`, `intent_preserved`,
`graph_integrity_preserved`, `required_human_review`. The spec draft's
`clear|concerns|breach-suspected` was invented language — exactly the
reconciliation problem. The skeletons follow the NODE's vocabulary.
Decision for you: is that node YAML's language canon? If yes, the spec doc
gets corrected to match; if no, amend the node first.

## Commit 1 — schemas.py (the receipt contract)

Look at: `IntegrityOutput` (new), and two new optional fields on
`VerdictReceipt`: `criteria_verdict`, `integrity`.
- `verdict` stays THE field everything reads; it becomes the combined value.
- `criteria_verdict` preserves the matrix's own answer so nothing is hidden.
- Both optional with None default = every existing receipt still validates
  (same trick as the confidence/criteria_confidence alias above it).
Decide: field names, and whether findings need more than
severity/summary/affected_node_ids.

## Commit 2 — integrity_combiner.py (the authority boundary)

New file, ~30 lines of real code. This IS the co-equal-authority rule:
combined verdict = worse of the two lanes; drift/contradicted/block floor at
needs-human-review (per the node's own acceptance criterion:
"drift/contradicted routes to needs-human-review, not pass, preserving the
human gate"); insufficient floors at needs-more-evidence. Any non-pass halts
the cascade because only pass lets dependents move.
Decide: the `_INTEGRITY_FLOOR` mapping — this table is the whole doctrine.
Should `block` floor at BLOCKED instead of needs-human-review?

## Commit 3 — orchestrator.py (where lane 2 runs)

Look at the block after `decision_engine.decide(...)`: integrity runs AFTER
criteria adjudication, ALWAYS (once the harness is wired), including on a
row-12 deterministic clean pass — the case that used to bypass semantic
entirely. `integrity_harness=None` today = behavior unchanged; the live
bridge will default it ON.
Decide: comfortable with sequential (criteria then integrity) vs parallel?
Sequential is simpler; costs ~1-2 min extra per return.

## Commit 4 — gddp_integrity.ts (the model's only output channel)

Skeleton tool signature `submit_integrity_verdict`, separate extension file,
same guard + read-only contract as gddp_verifier.ts. Note the TODO: non-pass
verdicts force `required_human_review=true` (node constraint line 58).
Decide: nothing structural here; naming only.

## Not in this branch (deliberately)

- No node YAML edits — graph truth is yours; the existing node already covers
  most of this. Gap to note: the node doesn't yet say "lane 2 ALWAYS runs";
  its criteria are about schema/engine consumption. If you accept the
  always-on doctrine, that belongs in the node's acceptance as a new criterion.
- No wiring of the harness/bridge/CLI — that's the implementation job
  (offloadable to a herdr lane) once you approve the skeleton shapes.
- Receipt-consumer impact scan (your Pi's job): bridge._parse_cli_summary keys,
  cli.py summary printing, receipt_sink, anything reading verification-runtime-live/.
