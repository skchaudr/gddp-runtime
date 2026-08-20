"""Phase 0: Baseline executable graded cases.

Five runnable scenarios that exercise the real evaluator pipeline (deterministic
+ semantic + integrity + combiner) with known expected verdicts. These are NOT
static JSON fixtures — they assemble DeterministicResult + SemanticOutput +
IntegrityOutput through the actual orchestrator.verify() and decision_engine.

Cases:
  1. Clear pass — all criteria pass, integrity pass, no findings
  2. Clear criteria failure — a criterion fails semantically
  3. Criteria-pass/intent-drift — criteria all pass, integrity detects drift
  4. Insufficient evidence — criteria indeterminate, semantic can't resolve,
     integrity insufficient
  5. Current pass + future concern — criteria pass, integrity pass, but
     forward-looking graph observation present

Case 5 is expected to FAIL until Phase 3 (graph_observations) lands. That is
the point: it proves the hardening adds capability.

Baseline is recorded by running these cases against the current evaluator.
Phase 5 re-runs them through the hardened evaluator and compares.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.runtime.verification import orchestrator
from scripts.runtime.verification.orchestrator import verify
from scripts.runtime.verification.schemas import (
    ConstraintCheck,
    CriterionCheck,
    DeterministicResult,
    GraphObservation,
    IntegrityFinding,
    IntegrityOutput,
    SemanticOutput,
    Verdict,
    VerdictReceipt,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockSemanticHarness:
    """Returns a canned SemanticOutput (no live pi)."""

    def __init__(self, output: SemanticOutput) -> None:
        self.output = output
        self.calls = 0

    def __call__(
        self,
        *,
        node: dict[str, Any],
        graph: dict[str, Any],
        deterministic_result: Any,
        shape_profile: dict[str, Any] | None = None,
        repo: Path,
    ) -> SemanticOutput:
        self.calls += 1
        return self.output


class MockIntegrityHarness:
    """Returns a canned IntegrityOutput (no live pi)."""

    def __init__(self, output: IntegrityOutput) -> None:
        self.output = output
        self.calls = 0

    def __call__(
        self,
        *,
        node: dict[str, Any],
        graph: dict[str, Any],
        deterministic_result: Any,
        repo: Path,
        config_root: Path | None = None,
    ) -> IntegrityOutput:
        self.calls += 1
        return self.output


def _criterion(cid: str, status: str, confidence: float = 0.9) -> CriterionCheck:
    return CriterionCheck(
        id=cid,
        criterion=f"criterion {cid}",
        status=status,
        confidence=confidence,
        method="probe",
        evidence=["module.py:1"],
        reasoning="deterministic probe result",
        mismatch_kind="",
        mismatch_detail="",
        needs_evidence=False,
        human_question="",
    )


def _constraint(status: str = "clear") -> ConstraintCheck:
    return ConstraintCheck(
        constraint="stay scoped",
        status=status,
        confidence=0.9,
        method="scan",
        evidence=[],
        reasoning="no violations",
    )


def _deterministic(
    *,
    criteria: list[CriterionCheck],
    constraints: list[ConstraintCheck] | None = None,
    artifacts: dict[str, bool] | None = None,
    deps: dict[str, str] | None = None,
) -> DeterministicResult:
    return DeterministicResult(
        criteria=criteria,
        constraints=constraints or [_constraint()],
        artifacts_present=artifacts or {"decision.md": True, "result-summary.md": True, "patch.diff": True},
        deps_status=deps or {},
        criteria_mismatches=[],
        missing_evidence=[],
        human_review_questions=[],
    )


def _integrity(
    verdict: str = "pass",
    intent: bool = True,
    integrity: bool = True,
    review: bool = False,
    findings: list[IntegrityFinding] | None = None,
    reasoning: str = "test",
) -> IntegrityOutput:
    return IntegrityOutput(
        verdict=verdict,
        intent_preserved=intent,
        graph_integrity_preserved=integrity,
        required_human_review=review,
        confidence=0.9,
        findings=findings or [],
        reasoning=reasoning,
    )


def _semantic_pass(cid: str = "c1", confidence: float = 0.9) -> SemanticOutput:
    return SemanticOutput(
        judgments=[
            {
                "criterion_id": cid,
                "judgment": "judged_pass",
                "confidence": confidence,
                "evidence": ["module.py:1"],
                "reasoning": "Mock semantic pass.",
            }
        ],
        overall_reasoning="Semantic mock passed.",
        risks=None,
        followup_candidates=None,
        budget_exhausted=False,
    )


def _semantic_fail(cid: str = "c1", confidence: float = 0.85) -> SemanticOutput:
    return SemanticOutput(
        judgments=[
            {
                "criterion_id": cid,
                "judgment": "judged_fail",
                "confidence": confidence,
                "evidence": ["module.py:1"],
                "reasoning": "Mock semantic fail.",
            }
        ],
        overall_reasoning="Semantic mock failed.",
        risks="Criterion not met.",
        followup_candidates=None,
        budget_exhausted=False,
    )


def _semantic_indeterminate(cid: str = "c1") -> SemanticOutput:
    return SemanticOutput(
        judgments=[
            {
                "criterion_id": cid,
                "judgment": "indeterminate",
                "confidence": 0.3,
                "evidence": ["module.py:1"],
                "reasoning": "Mock semantic could not resolve.",
            }
        ],
        overall_reasoning="Semantic mock indeterminate.",
        risks=None,
        followup_candidates=None,
        budget_exhausted=False,
    )


def _run_case(
    tmp_path: Path,
    det: DeterministicResult,
    semantic: SemanticOutput | None,
    integrity: IntegrityOutput | None,
    *,
    monkeypatch,
) -> VerdictReceipt:
    """Run verify() with mocked deterministic.assemble and optional lanes."""
    monkeypatch.setattr(orchestrator.deterministic, "assemble", lambda **_: det)

    integrity_harness = MockIntegrityHarness(integrity) if integrity else None
    # Wire a mock semantic harness when a canned SemanticOutput is provided.
    # The built-in SemanticAgent fallback was removed; the orchestrator requires
    # a semantic_harness when the semantic lane runs (indeterminate criteria).
    semantic_harness = MockSemanticHarness(semantic) if semantic else None

    return verify(
        node_yaml={"node_id": "graded-case", "acceptance_criteria": [{"id": "c1", "criterion": "test"}]},
        project_yaml={"project_id": "graded-project", "nodes": [{"id": "graded-case"}]},
        repo=tmp_path,
        semantic_harness=semantic_harness,
        integrity_harness=integrity_harness,
        now=lambda: "2026-07-16T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# Case 1: Clear pass — all green
# ---------------------------------------------------------------------------


def test_case_1_clear_pass(monkeypatch, tmp_path: Path) -> None:
    """All criteria pass deterministically, integrity pass, no findings."""
    det = _deterministic(criteria=[_criterion("c1", "pass")])
    integrity = _integrity(verdict="pass")

    receipt = _run_case(tmp_path, det, None, integrity, monkeypatch=monkeypatch)

    assert receipt.verdict == Verdict.PASS
    assert receipt.criteria_verdict == Verdict.PASS
    assert receipt.integrity is not None
    assert receipt.integrity.verdict == "pass"
    assert receipt.integrity.findings == []


# ---------------------------------------------------------------------------
# Case 2: Clear criteria failure
# ---------------------------------------------------------------------------


def test_case_2_clear_criteria_failure(monkeypatch, tmp_path: Path) -> None:
    """A criterion fails semantically (deterministic indeterminate, semantic judged_fail)."""
    det = _deterministic(criteria=[_criterion("c1", "indeterminate")])
    semantic = _semantic_fail()
    integrity = _integrity(verdict="pass")

    receipt = _run_case(tmp_path, det, semantic, integrity, monkeypatch=monkeypatch)

    assert receipt.verdict == Verdict.FAIL
    assert receipt.criteria_verdict == Verdict.FAIL
    assert receipt.integrity is not None
    assert receipt.integrity.verdict == "pass"


# ---------------------------------------------------------------------------
# Case 3: Criteria-pass/intent-drift
# ---------------------------------------------------------------------------


def test_case_3_criteria_pass_intent_drift(monkeypatch, tmp_path: Path) -> None:
    """Criteria all pass, integrity detects drift."""
    det = _deterministic(criteria=[_criterion("c1", "pass")])
    integrity = _integrity(
        verdict="drift",
        intent=False,
        review=True,
        findings=[
            IntegrityFinding(
                severity="high",
                summary="Scope creep: implementation adds a feature not in the node's intent.",
                affected_node_ids=["graded-case"],
            )
        ],
        reasoning="The change implements an extra module outside the node's stated why.",
    )

    receipt = _run_case(tmp_path, det, None, integrity, monkeypatch=monkeypatch)

    assert receipt.criteria_verdict == Verdict.PASS
    assert receipt.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert receipt.integrity is not None
    assert receipt.integrity.verdict == "drift"
    assert receipt.integrity.intent_preserved is False
    assert receipt.integrity.required_human_review is True


# ---------------------------------------------------------------------------
# Case 4: Insufficient evidence
# ---------------------------------------------------------------------------


def test_case_4_insufficient_evidence(monkeypatch, tmp_path: Path) -> None:
    """Criteria indeterminate, semantic can't resolve, integrity insufficient."""
    det = _deterministic(
        criteria=[_criterion("c1", "indeterminate")],
        artifacts={"decision.md": True, "result-summary.md": True, "patch.diff": True},
    )
    semantic = _semantic_indeterminate()
    integrity = _integrity(
        verdict="insufficient",
        review=True,
        reasoning="Not enough evidence to reach a clear verdict.",
    )

    receipt = _run_case(tmp_path, det, semantic, integrity, monkeypatch=monkeypatch)

    # Semantic indeterminate with artifacts present -> row 10 -> needs-human-review
    # Integrity insufficient -> floors at needs-more-evidence
    # Worst-of: needs-human-review > needs-more-evidence, so needs-human-review wins
    # But wait: the combiner takes max(criteria_verdict, floor) by severity
    # needs-human-review (2) > needs-more-evidence (1), so combined = needs-human-review
    assert receipt.verdict in (Verdict.NEEDS_HUMAN_REVIEW, Verdict.NEEDS_MORE_EVIDENCE)
    assert receipt.integrity is not None
    assert receipt.integrity.verdict == "insufficient"


# ---------------------------------------------------------------------------
# Case 5: Current pass + future concern (expected to FAIL until Phase 3)
# ---------------------------------------------------------------------------


def test_case_5_pass_with_future_concern(monkeypatch, tmp_path: Path) -> None:
    """Criteria pass, integrity pass, but forward-looking graph observation present.

    This case is the critical calibration: the current work passes, but the
    evaluator observes a forward-looking graph concern. The verdict MUST remain
    'pass' — the graph observation is evidence for the operator, not a disguised
    failure.

    Phase 3: graph_observations field is now available on IntegrityOutput.
    The forward-looking concern goes in graph_observations (not findings),
    so the combiner does NOT floor the verdict.
    """
    det = _deterministic(criteria=[_criterion("c1", "pass")])
    integrity = _integrity(
        verdict="pass",
        reasoning="Current node passes. Forward-looking: next three nodes converge on the scheduler.",
    )
    integrity.graph_observations = [
        GraphObservation(
            severity="medium",
            summary="Upcoming nodes converge on shared state; serialize this region.",
            affected_node_ids=["downstream-a", "downstream-b", "downstream-c"],
        )
    ]

    receipt = _run_case(tmp_path, det, None, integrity, monkeypatch=monkeypatch)

    assert receipt.verdict == Verdict.PASS
    assert receipt.criteria_verdict == Verdict.PASS
    assert receipt.integrity is not None
    assert receipt.integrity.verdict == "pass"
    assert receipt.integrity.graph_observations is not None
    assert len(receipt.integrity.graph_observations) == 1
    assert receipt.integrity.graph_observations[0].severity == "medium"
    # The finding is in graph_observations, NOT in findings
    assert receipt.integrity.findings == []
