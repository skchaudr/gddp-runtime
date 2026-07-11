# Decision: Verdict Confidence Split

## Problem
A single blended confidence scalar (0.18) was conflating "missing paperwork" with "broken code," backwards. The weakest signal (indeterminate deterministic floor) was overriding strong semantic evidence (0.95+).

## Implementation
1.  **Exposed Three Axes**: `criteria_confidence`, `completeness`, and `graph_readiness` are now distinct fields in the `VerdictReceipt`.
2.  **Calibration Fix**: `_confidence_semantic_blend` now defers to the semantic confidence when judgments exist, rather than `min()`-ing it with the deterministic floor.
3.  **Completeness Signal**: Missing artifacts now drive `completeness` to 0.0 but leave `criteria_confidence` intact.
4.  **Graph Readiness**: Explicit 0/0.5/1.0 signal for whether the node is ready for human acceptance.
5.  **Backward Compatibility**: The `confidence` field remains populated as an alias for `criteria_confidence`.

## Result
A built-but-untrailed node now reads as ~0.95 `criteria_confidence` with a `needs-more-evidence` verdict and 0.0 `completeness`. This is honest and trustable.
