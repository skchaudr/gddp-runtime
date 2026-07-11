# Result Summary: Verdict Confidence Split

Implemented the split of the verdict confidence into criteria-confidence and completeness axes to improve the trustability of the loop.

### Key Changes
- **Schemas**: `VerdictReceipt` now exposes `criteria_confidence`, `completeness`, and `graph_readiness`.
- **Decision Engine**:
    - `decide` returns all three signals + verdict and action.
    - Semantic confidence is no longer suppressed by an indeterminate deterministic floor.
    - Artifact missingness is decoupled from criteria confidence.
- **Orchestrator**: Populates the new fields and handles graph readiness updates after integrity checks.

### Verification Results
- **test_decision_engine.py**: All 17 tests passed, including new calibration checks.
- **test_schemas.py**: Legacy compatibility and alias enforcement verified.
- **Calibration Check**: Verified that semantic-pass + artifacts-missing yields high confidence (>= 0.85) but `needs-more-evidence` verdict.
