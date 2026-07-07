"""Combine the criteria verdict with the integrity verdict into the receipt verdict.

This is the entire authority boundary between the two evaluator lanes, kept
deliberately tiny and deterministic so the trust anchor never moves into model
judgment. The 12-row matrix is untouched; this layer runs AFTER it.

Rules (from the evaluator-intent-integrity-verdict node YAML):
  - integrity not run          -> criteria verdict unchanged
  - integrity pass, both flags -> criteria verdict unchanged
  - drift / contradicted / block -> at least needs-human-review (human gate, cascade halts)
  - insufficient               -> at least needs-more-evidence
  - unknown                    -> at least needs-human-review
  - neither lane can ever UPGRADE the other: the combined verdict is the worse of the two
"""

from __future__ import annotations

from .schemas import IntegrityOutput, Verdict

# Severity order for "worse of the two". Higher = worse.
_SEVERITY = {
    Verdict.PASS: 0,
    Verdict.NEEDS_MORE_EVIDENCE: 1,
    Verdict.NEEDS_HUMAN_REVIEW: 2,
    Verdict.OUT_OF_SCOPE_CHANGE_DETECTED: 3,
    Verdict.FAIL: 4,
    Verdict.BLOCKED: 5,
}

_INTEGRITY_FLOOR = {
    "pass": Verdict.PASS,
    "insufficient": Verdict.NEEDS_MORE_EVIDENCE,
    "unknown": Verdict.NEEDS_HUMAN_REVIEW,
    "drift": Verdict.NEEDS_HUMAN_REVIEW,
    "contradicted": Verdict.NEEDS_HUMAN_REVIEW,
    "block": Verdict.NEEDS_HUMAN_REVIEW,
}


def combine(
    criteria_verdict: Verdict,
    integrity: IntegrityOutput | None,
    required_next_action: str,
) -> tuple[Verdict, str]:
    """Return (combined_verdict, required_next_action)."""
    if integrity is None:
        return criteria_verdict, required_next_action

    floor = _INTEGRITY_FLOOR[integrity.verdict]
    # An integrity "pass" with a violated flag is a malformed submission; the
    # flags are the finding, the verdict word does not get to override them.
    if not integrity.intent_preserved or not integrity.graph_integrity_preserved:
        floor = max(floor, Verdict.NEEDS_HUMAN_REVIEW, key=_SEVERITY.__getitem__)

    combined = max(criteria_verdict, floor, key=_SEVERITY.__getitem__)
    if combined is not criteria_verdict:
        required_next_action = (
            f"Integrity verdict '{integrity.verdict}' halts progression "
            f"(criteria verdict was '{criteria_verdict.value}'). Human review required; "
            "no dependent node may dispatch on this node."
        )
    return combined, required_next_action
