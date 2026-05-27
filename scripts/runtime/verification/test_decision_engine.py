"""pytest tests for the decision engine — one test per matrix row."""

import types

import pytest

from .decision_engine import decide
from .semantic_schema import SemanticOutput
from .verdict_schema import DecisionOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _structural(all_passed: bool) -> types.SimpleNamespace:
    """Minimal duck-typed structural result."""
    return types.SimpleNamespace(all_passed=all_passed, results=[])


def _semantic(semantic_fidelity: str, requires_operator_review: bool = False) -> SemanticOutput:
    return SemanticOutput(
        semantic_fidelity=semantic_fidelity,  # type: ignore[arg-type]
        risk_level="low",
        drift_type="none",
        requires_operator_review=requires_operator_review,
    )


# ---------------------------------------------------------------------------
# Matrix row tests (8 total)
# ---------------------------------------------------------------------------

class TestRow1StructuralFailure:
    """Row 1: structural.all_passed is False → FAIL / blocking (any diagnostic)."""

    def test_structural_fail_with_none_semantic(self):
        structural = _structural(all_passed=False)
        result = decide(structural, semantic=None)
        assert isinstance(result, DecisionOutput)
        assert result.verdict == "FAIL"
        assert result.severity == "blocking"
        assert result.matrix_row == 1

    def test_structural_fail_with_preserved_semantic(self):
        structural = _structural(all_passed=False)
        result = decide(structural, semantic=_semantic("preserved"))
        assert result.verdict == "FAIL"
        assert result.severity == "blocking"
        assert result.matrix_row == 1


class TestRow2Skipped:
    """Row 2: all_passed=True, semantic=None → ACCEPT / None."""

    def test_semantic_none(self):
        result = decide(_structural(True), semantic=None)
        assert isinstance(result, DecisionOutput)
        assert result.verdict == "ACCEPT"
        assert result.reason == "skipped"
        assert result.severity is None
        assert result.matrix_row == 2


class TestRow3Preserved:
    """Row 3: all_passed=True, preserved → ACCEPT / None."""

    def test_preserved(self):
        result = decide(_structural(True), semantic=_semantic("preserved"))
        assert isinstance(result, DecisionOutput)
        assert result.verdict == "ACCEPT"
        assert result.reason == "preserved"
        assert result.severity is None
        assert result.matrix_row == 3


class TestRow4Weakened:
    """Row 4: all_passed=True, weakened → NEEDS_REVIEW / warning."""

    def test_weakened(self):
        result = decide(_structural(True), semantic=_semantic("weakened"))
        assert isinstance(result, DecisionOutput)
        assert result.verdict == "NEEDS_REVIEW"
        assert result.reason == "weakened"
        assert result.severity == "warning"
        assert result.matrix_row == 4


class TestRow5Drifted:
    """Row 5: all_passed=True, drifted → NEEDS_REVIEW / warning."""

    def test_drifted(self):
        result = decide(_structural(True), semantic=_semantic("drifted"))
        assert isinstance(result, DecisionOutput)
        assert result.verdict == "NEEDS_REVIEW"
        assert result.reason == "drifted"
        assert result.severity == "warning"
        assert result.matrix_row == 5


class TestRow6Contradicted:
    """Row 6: all_passed=True, contradicted → INVALID / blocking."""

    def test_contradicted(self):
        result = decide(_structural(True), semantic=_semantic("contradicted"))
        assert isinstance(result, DecisionOutput)
        assert result.verdict == "INVALID"
        assert result.reason == "contradicted"
        assert result.severity == "blocking"
        assert result.matrix_row == 6


class TestRow7Insufficient:
    """Row 7: all_passed=True, insufficient → INCOMPLETE / warning."""

    def test_insufficient(self):
        result = decide(_structural(True), semantic=_semantic("insufficient"))
        assert isinstance(result, DecisionOutput)
        assert result.verdict == "INCOMPLETE"
        assert result.reason == "insufficient"
        assert result.severity == "warning"
        assert result.matrix_row == 7


class TestRow8OperatorReview:
    """Row 8: all_passed=True, requires_operator_review → NEEDS_REVIEW / warning."""

    def test_operator_review_flagged(self):
        semantic = _semantic("preserved", requires_operator_review=True)
        result = decide(_structural(True), semantic=semantic)
        assert isinstance(result, DecisionOutput)
        assert result.verdict == "NEEDS_REVIEW"
        assert result.reason == "operator_review_flagged"
        assert result.severity == "warning"
        assert result.matrix_row == 8
