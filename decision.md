# Verdict Confidence Split

## Decision
Modified `decision_engine.py` to stop using `min(floor, semantic)` when the deterministic floor is indeterminate-dominated. Instead, it directly defers to the semantic phase's confidence (`semantic`). The `VerdictReceipt` now properly handles `criteria_confidence`, `completeness`, and `graph_readiness` instead of blending everything into one opaque scalar.

## Rationale
A node whose code fully satisfied all semantic criteria (with line-level evidence) received an overall confidence of 0.18 because the weak indeterminate deterministic floor was masking the strong semantic signal. Furthermore, missing execution artifacts should correctly gate the verdict to `needs-more-evidence` via the `completeness` signal (e.g. 0.5) without artificially lowering `criteria_confidence` for the code logic. This aligns with `docs/verification-receipt-contract.md` by separating the "unsure the code works" dimension from the "paperwork/trail missing" dimension.

## Implementation Notes
- **`decision_engine.py`**: Updated `_signals_semantic_blend` so that `if ctx.indeterminate_criteria:` then `criteria_conf = semantic`, ensuring strong semantic judgments are preserved.
- **`schemas.py`**: Added explicit `criteria_confidence` and `completeness` fields to `VerdictReceipt`, mapping the legacy `confidence` field to/from `criteria_confidence` in a backwards-compatible way.
- **`orchestrator.py`**: Populated the discrete fields `criteria_confidence`, `completeness`, and `graph_readiness` from `VerificationSignals` when constructing the `VerdictReceipt`.
- **Testing**: Test cases like `test_semantic_pass_missing_artifacts_keeps_high_criteria_confidence` assert that `criteria_confidence` is high while `verdict` remains `needs-more-evidence`.
