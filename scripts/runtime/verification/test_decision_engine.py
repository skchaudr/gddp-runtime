"""Tests for the pure verdict decision engine."""

from __future__ import annotations

from .decision_engine import decide
from .schemas import (
    ConstraintCheck,
    CriterionCheck,
    CriterionJudgment,
    DeterministicResult,
    SemanticOutput,
    Verdict,
)


def _criterion(
    criterion_id: str,
    status: str,
    confidence: float = 0.8,
) -> CriterionCheck:
    return CriterionCheck(
        id=criterion_id,
        criterion=f"criterion {criterion_id}",
        status=status,
        confidence=confidence,
        method="symbol",
        evidence=[],
        reasoning="",
        mismatch_kind="",
        mismatch_detail="",
        needs_evidence=False,
        human_question="",
    )


def _constraint(status: str, confidence: float = 0.85) -> ConstraintCheck:
    return ConstraintCheck(
        constraint="no forbidden patterns",
        status=status,
        confidence=confidence,
        method="scan",
        evidence=[],
        reasoning="",
    )


def _deterministic(
    *,
    criteria: list[CriterionCheck] | None = None,
    constraints: list[ConstraintCheck] | None = None,
    artifacts_present: dict[str, bool] | None = None,
    deps_status: dict[str, str] | None = None,
) -> DeterministicResult:
    return DeterministicResult(
        criteria=criteria or [],
        constraints=constraints or [],
        artifacts_present=artifacts_present or {},
        deps_status=deps_status or {},
        criteria_mismatches=[],
        missing_evidence=[],
        human_review_questions=[],
    )


def _judgment(
    criterion_id: str,
    judgment: str,
    confidence: float = 0.9,
) -> CriterionJudgment:
    return CriterionJudgment(
        criterion_id=criterion_id,
        judgment=judgment,
        confidence=confidence,
        evidence=["module.py:1"],
        reasoning="investigated",
    )


def _semantic(
    judgments: list[CriterionJudgment] | None = None,
    *,
    budget_exhausted: bool = False,
) -> SemanticOutput:
    return SemanticOutput(
        judgments=judgments or [],
        overall_reasoning="done",
        risks=None,
        followup_candidates=None,
        budget_exhausted=budget_exhausted,
    )


def test_matrix_row_1_blocked_on_incomplete_deps():
    det = _deterministic(
        criteria=[_criterion("a", "pass")],
        deps_status={"dep-a": "pending", "dep-b": "complete"},
    )
    verdict, _, _ = decide(det, None)
    assert verdict == Verdict.BLOCKED


def test_matrix_row_2_out_of_scope_on_constraint_violation():
    det = _deterministic(
        criteria=[_criterion("a", "pass")],
        constraints=[_constraint("violated")],
        deps_status={"dep-a": "complete"},
    )
    verdict, _, _ = decide(det, None)
    assert verdict == Verdict.OUT_OF_SCOPE_CHANGE_DETECTED


def test_matrix_row_3_fail_on_deterministic_hard_fail():
    det = _deterministic(
        criteria=[_criterion("a", "fail", 0.6), _criterion("b", "pass")],
        deps_status={"dep-a": "complete"},
    )
    verdict, _, _ = decide(det, None)
    assert verdict == Verdict.FAIL


def test_matrix_row_4_fail_on_semantic_judged_fail():
    det = _deterministic(
        criteria=[_criterion("a", "indeterminate", 0.5)],
        artifacts_present={"receipt.json": True},
        deps_status={"dep-a": "complete"},
    )
    sem = _semantic([_judgment("a", "judged_fail", 0.85)])
    verdict, _, _ = decide(det, sem)
    assert verdict == Verdict.FAIL


def test_matrix_row_5_needs_more_evidence_all_pass_missing_artifacts():
    det = _deterministic(
        criteria=[_criterion("a", "pass"), _criterion("b", "pass")],
        artifacts_present={"receipt.json": False},
        deps_status={"dep-a": "complete"},
    )
    verdict, _, _ = decide(det, None)
    assert verdict == Verdict.NEEDS_MORE_EVIDENCE


def test_matrix_row_6_needs_more_evidence_semantic_pass_missing_artifacts():
    det = _deterministic(
        criteria=[_criterion("a", "indeterminate", 0.6)],
        artifacts_present={"receipt.json": False},
        deps_status={"dep-a": "complete"},
    )
    sem = _semantic([_judgment("a", "judged_pass", 0.95)])
    verdict, _, _ = decide(det, sem)
    assert verdict == Verdict.NEEDS_MORE_EVIDENCE


def test_matrix_row_7_needs_more_evidence_semantic_indeterminate_missing_artifacts():
    det = _deterministic(
        criteria=[_criterion("a", "indeterminate", 0.6)],
        artifacts_present={"receipt.json": False},
        deps_status={"dep-a": "complete"},
    )
    sem = _semantic([_judgment("a", "indeterminate", 0.65)])
    verdict, _, action = decide(det, sem)
    assert verdict == Verdict.NEEDS_MORE_EVIDENCE
    assert action == "Provide missing required artifacts and re-run semantic investigation."


def test_matrix_row_8_needs_more_evidence_budget_exhausted():
    det = _deterministic(
        criteria=[_criterion("a", "indeterminate", 0.55)],
        artifacts_present={"receipt.json": True},
        deps_status={"dep-a": "complete"},
    )
    sem = _semantic(
        [_judgment("a", "indeterminate", 0.7)],
        budget_exhausted=True,
    )
    verdict, confidence, _ = decide(det, sem)
    assert verdict == Verdict.NEEDS_MORE_EVIDENCE
    assert confidence <= 0.5


def test_budget_exhausted_keeps_precedence_over_missing_artifacts():
    det = _deterministic(
        criteria=[_criterion("a", "indeterminate", 0.55)],
        artifacts_present={"receipt.json": False},
        deps_status={"dep-a": "complete"},
    )
    sem = _semantic(
        [_judgment("a", "indeterminate", 0.7)],
        budget_exhausted=True,
    )
    verdict, confidence, action = decide(det, sem)
    assert verdict == Verdict.NEEDS_MORE_EVIDENCE
    assert confidence <= 0.5
    assert action == "Re-run semantic investigation with sufficient budget."


def test_matrix_row_9_needs_more_evidence_empty_semantic_judgments():
    det = _deterministic(
        criteria=[_criterion("a", "indeterminate", 0.4)],
        artifacts_present={"receipt.json": True},
        deps_status={"dep-a": "complete"},
    )
    verdict, _, _ = decide(det, _semantic([]))
    assert verdict == Verdict.NEEDS_MORE_EVIDENCE


def test_matrix_row_10_needs_human_review_semantic_indeterminate():
    det = _deterministic(
        criteria=[_criterion("a", "indeterminate", 0.5)],
        artifacts_present={"receipt.json": True},
        deps_status={"dep-a": "complete"},
    )
    sem = _semantic([_judgment("a", "indeterminate", 0.65)])
    verdict, _, _ = decide(det, sem)
    assert verdict == Verdict.NEEDS_HUMAN_REVIEW


def test_matrix_row_11_pass_semantic_resolves_indeterminate():
    det = _deterministic(
        criteria=[
            _criterion("a", "indeterminate", 0.7),
            _criterion("b", "pass"),
        ],
        artifacts_present={"receipt.json": True},
        deps_status={"dep-a": "complete"},
    )
    sem = _semantic(
        [
            _judgment("a", "judged_pass", 0.92),
            _judgment("b", "judged_pass", 0.88),
        ]
    )
    verdict, _, _ = decide(det, sem)
    assert verdict == Verdict.PASS


def test_matrix_row_12_pass_deterministic_clean():
    det = _deterministic(
        criteria=[_criterion("a", "pass", 0.9), _criterion("b", "pass", 0.85)],
        artifacts_present={"receipt.json": True},
        deps_status={"dep-a": "complete"},
    )
    verdict, _, _ = decide(det, None)
    assert verdict == Verdict.PASS


def test_row_4_precedence_over_budget_exhausted():
    """Semantic judged_fail outranks budget exhaustion (row 4 before row 7)."""
    det = _deterministic(
        criteria=[_criterion("a", "indeterminate", 0.5)],
        artifacts_present={"receipt.json": True},
        deps_status={"dep-a": "complete"},
    )
    sem = _semantic(
        [_judgment("a", "judged_fail", 0.8)],
        budget_exhausted=True,
    )
    verdict, _, _ = decide(det, sem)
    assert verdict == Verdict.FAIL


def test_semantic_confidence_blend_uses_weaker_layer():
    det = _deterministic(
        criteria=[_criterion("a", "indeterminate", 0.4)],
        artifacts_present={"receipt.json": True},
        deps_status={"dep-a": "complete"},
    )
    sem = _semantic([_judgment("a", "judged_pass", 0.95)])
    _, confidence, _ = decide(det, sem)
    assert confidence == 0.4
