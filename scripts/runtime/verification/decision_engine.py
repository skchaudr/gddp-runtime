from typing import Any, Optional

from .semantic_schema import SemanticOutput
from .verdict_schema import DecisionOutput

# ---------------------------------------------------------------------------
# Decision matrix: ordered list of (row_number, matcher, verdict, severity).
# The first row whose matcher returns True fires; the function returns
# immediately.  Row 1 (structural failure) is evaluated first so it
# short-circuits regardless of the semantic diagnostic.
# ---------------------------------------------------------------------------

MATRIX = [
    # row 1 — structural failure
    (1, lambda all_passed, diag: not all_passed,
     "FAIL", "blocking"),
    # row 2 — semantic skipped
    (2, lambda all_passed, diag: diag == "skipped",
     "ACCEPT", None),
    # row 3 — preserved
    (3, lambda all_passed, diag: diag == "preserved",
     "ACCEPT", None),
    # row 4 — weakened
    (4, lambda all_passed, diag: diag == "weakened",
     "NEEDS_REVIEW", "warning"),
    # row 5 — drifted
    (5, lambda all_passed, diag: diag == "drifted",
     "NEEDS_REVIEW", "warning"),
    # row 6 — contradicted
    (6, lambda all_passed, diag: diag == "contradicted",
     "INVALID", "blocking"),
    # row 7 — insufficient
    (7, lambda all_passed, diag: diag == "insufficient",
     "INCOMPLETE", "warning"),
    # row 8 — operator review flagged
    (8, lambda all_passed, diag: diag == "operator_review_flagged",
     "NEEDS_REVIEW", "warning"),
]


def decide(structural: Any, semantic: Optional[SemanticOutput] = None) -> DecisionOutput:
    """Pure function — derive a verdict from structural + semantic inputs.

    No I/O, no LLM calls, no randomness, no datetime, no global state.
    """

    # Step 1 — derive diagnostic
    if semantic is None:
        diagnostic = "skipped"
    elif semantic.requires_operator_review is True:
        diagnostic = "operator_review_flagged"
    else:
        diagnostic = semantic.semantic_fidelity

    all_passed = structural.all_passed  # duck-typed

    # Step 2 — walk the matrix, first match wins
    for row_num, matcher, verdict, severity in MATRIX:
        if matcher(all_passed, diagnostic):
            return DecisionOutput(
                verdict=verdict,
                reason=diagnostic,
                severity=severity,
                matrix_row=row_num,
            )

    # Exhaustive matrix guarantees we never reach here, but satisfy mypy.
    raise RuntimeError("Decision matrix exhausted without a match")  # pragma: no cover
