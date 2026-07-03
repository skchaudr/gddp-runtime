# 016 — Semantic Loop Budget Trace And Completion Boundary

Date: 2026-07-03

## Summary

The live verifier path now supports higher live-run budgets, emits a semantic
budget trace into receipts, caps individual tool-result payloads, and constrains
finalization turns to the terminal `submit_verdict` tool.

This hardens the verification loop itself rather than treating the semantic
verifier as the whole product.

## What changed

- Added CLI/runtime knobs:
  - `--semantic-max-turns`
  - `--semantic-max-tool-calls`
  - `--semantic-max-tokens`
  - `--semantic-provider-max-tokens`
  - `--semantic-max-tool-result-chars`
- Added `SemanticOutput.budget_trace`.
- Added per-event trace records for model responses, tool results, finalization,
  final reason, remaining budget, message count, and truncation.
- Finalization turns expose only `submit_verdict`, so the harness owns the loop
  boundary instead of merely asking the model to stop searching.
- Large tool results are serialized through a bounded wrapper instead of being
  allowed to consume the transcript.
- Added committed ambiguity receipt fixtures:
  - `semantic-pass-with-missing-artifacts.json`
  - `semantic-fail-with-complete-artifacts.json`
- Added a decision-matrix row for semantic indeterminate + missing artifacts so
  live verification emits a receipt instead of exhausting the matrix.

## Validation

`python -m pytest -q`

Result: 121 passed.

Live verifier command:

```bash
zsh -ic '.venv/bin/python -m scripts.runtime.verification.cli --node-yaml ../gddp-config/graphs/gddp-runtime/nodes/verification-receipt-contract.yaml --project-yaml ../gddp-config/graphs/gddp-runtime/project.yaml --repo . --config-root ../gddp-config --receipt-dir /tmp/gddp-runtime-live-receipts-matrix-covered --semantic-mode live --semantic-max-tokens 96000 --semantic-max-tool-calls 80 --semantic-max-turns 25 --semantic-provider-max-tokens 8192 --semantic-max-tool-result-chars 50000'
```

Result:

- receipt: `/tmp/gddp-runtime-live-receipts-matrix-covered/gddp-runtime/verification-receipt-contract.json`
- verdict: `needs-more-evidence`
- completeness_status: `complete`
- semantic judgments: 10
- semantic budget exhausted: false
- final_reason: `submit_verdict accepted`
- remaining estimated tokens: 29774
- remaining tool calls: 28
- required_next_action: `Provide missing required artifacts and re-run semantic investigation.`

## Interpretation

The harness now completes the live semantic loop and writes a receipt. The
`verification-receipt-contract` graph node still should not be marked complete
from this alone: `runtime-receipt-proves-node` remains indeterminate until the
formal completion artifacts are attached through the expected handoff/result
path.

