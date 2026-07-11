# Decision: Split Verdict Confidence

## Problem
The previous single-scalar confidence value conflated two distinct signals: "Does the code meet the criteria?" and "Are all required artifacts present?". This led to high-quality code receiving a low confidence score (e.g., 0.18) simply because artifacts were missing, even if semantic judgments were overwhelmingly positive. Additionally, the min-blending logic allowed an indeterminate deterministic floor to override a confident semantic decision.

## Implementation Choice
I split the confidence signal into three axes within the `VerdictReceipt`:
1.  `criteria_confidence`: How sure we are that the code satisfies the functional criteria.
2.  `completeness`: Whether the required execution trail (artifacts) is present.
3.  `graph_readiness`: A derived signal indicating if the node has enough evidence to be advanced in the graph (high criteria confidence + high completeness).

I also introduced a `VerificationSignals` dataclass to pass these values cleanly through the decision engine.

## Calibration Fix
In `scripts/runtime/verification/decision_engine.py`, the `_signals_semantic_blend` function was updated. It now defers directly to the semantic confidence when indeterminate deterministic criteria are present, instead of taking the minimum of the floor and semantic confidence. This ensures that the semantic phase, which is specifically invoked to resolve these indeterminacies, is not undermined by the very uncertainty it was meant to solve.

## Artifact Gate Preservation
The decision matrix rows remain unchanged. Missing artifacts still result in a `NEEDS_MORE_EVIDENCE` verdict, but the `criteria_confidence` now accurately reflects the high confidence in the implementation if semantic checks pass.
