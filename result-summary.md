# Result Summary - Verdict Confidence Split

## Changes
- **Schemas**: Updated `VerdictReceipt` in `scripts/runtime/verification/schemas.py` to include `criteria_confidence`, `completeness`, and `graph_readiness`. Added backward compatibility for the legacy `confidence` field.
- **Decision Engine**: Modified `scripts/runtime/verification/decision_engine.py` to return multi-axis `VerificationSignals`. Updated blending logic to defer to semantic confidence when the deterministic floor is indeterminate.
- **Orchestrator**: Updated `scripts/runtime/verification/orchestrator.py` to populate the new receipt fields from the decision engine output.
- **Testing**: Updated the test suite to match the new `decide` signature and added scenarios verifying that:
    - Semantic pass with missing artifacts yields high `criteria_confidence` but low `completeness`.
    - Indeterminate deterministic floor does not suppress a confident semantic result.
    - Semantic fail correctly results in low `criteria_confidence`.

## Verification Results
- All 143 tests in the `scripts/runtime/verification/` directory passed successfully.
- Manual verification of the `VerdictReceipt` schema showed correct handling of both new and legacy data formats.
- Confirmed that `criteria_confidence` for a semantically-passing node with missing artifacts is now correctly reported as >= 0.85 instead of being collapsed by the deterministic floor.
