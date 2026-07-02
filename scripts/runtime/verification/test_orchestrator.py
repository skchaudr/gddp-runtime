from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.runtime.verification import orchestrator
from scripts.runtime.verification.schemas import (
    ConstraintCheck,
    CriterionCheck,
    DeterministicResult,
    SemanticOutput,
    Verdict,
)
from scripts.runtime.verification.semantic.tools import SemanticToolbox


class MockRunner:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]):
        self.calls += 1
        from scripts.runtime.verification.semantic.agent import LLMResponse

        return LLMResponse(content=self.content, tool_calls=[], finish_reason="stop")


def test_clean_deterministic_pass_skips_semantic(monkeypatch, tmp_path: Path) -> None:
    det = DeterministicResult(
        criteria=[
            CriterionCheck(
                id="c1",
                criterion="criterion passes",
                status="pass",
                confidence=0.95,
                method="test",
                evidence=["evidence"],
                reasoning="passed",
                mismatch_kind="",
                mismatch_detail="",
                needs_evidence=False,
                human_question="",
            )
        ],
        constraints=[
            ConstraintCheck(
                constraint="stay scoped",
                status="clear",
                confidence=1.0,
                method="scan",
                evidence=[],
                reasoning="clear",
            )
        ],
        artifacts_present={"result-summary.md": True},
        deps_status={},
        criteria_mismatches=[],
        missing_evidence=[],
        human_review_questions=[],
    )
    monkeypatch.setattr(orchestrator.deterministic, "assemble", lambda **_: det)
    runner = MockRunner("{}")

    receipt = orchestrator.verify(
        node_yaml={"node_id": "node-clean"},
        project_yaml={"project_id": "project-clean"},
        repo=tmp_path,
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        now=lambda: "2026-06-30T00:00:00+00:00",
    )

    assert runner.calls == 0
    assert receipt.semantic is None
    assert receipt.verdict == Verdict.PASS
    assert receipt.criteria_confidence == receipt.confidence
    assert receipt.completeness_status == "not-run"
    assert receipt.project_id == "project-clean"
    assert receipt.node_id == "node-clean"


def test_indeterminate_criterion_invokes_semantic_and_builds_receipt(monkeypatch, tmp_path: Path) -> None:
    det = DeterministicResult(
        criteria=[
            CriterionCheck(
                id="c1",
                criterion="criterion needs semantic read",
                status="indeterminate",
                confidence=0.8,
                method="regex",
                evidence=["module.py"],
                reasoning="regex could not decide",
                mismatch_kind="wording",
                mismatch_detail="needs meaning check",
                needs_evidence=False,
                human_question="",
            )
        ],
        constraints=[],
        artifacts_present={},
        deps_status={},
        criteria_mismatches=[],
        missing_evidence=[],
        human_review_questions=[],
    )
    monkeypatch.setattr(orchestrator.deterministic, "assemble", lambda **_: det)
    semantic_json = SemanticOutput(
        judgments=[
            {
                "criterion_id": "c1",
                "judgment": "judged_pass",
                "confidence": 0.7,
                "evidence": ["module.py:1"],
                "reasoning": "Mock semantic evidence matched the criterion.",
            }
        ],
        overall_reasoning="Semantic mock passed.",
        risks=None,
        followup_candidates=None,
        budget_exhausted=False,
    ).model_dump_json()
    runner = MockRunner(semantic_json)

    receipt = orchestrator.verify(
        node_yaml={"node_id": "node-semantic"},
        project_yaml={"project_id": "project-semantic"},
        repo=tmp_path,
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        now=lambda: "2026-06-30T00:00:00+00:00",
    )

    assert runner.calls == 1
    assert receipt.semantic is not None
    assert receipt.verdict == Verdict.PASS
    assert receipt.confidence == 0.7
    assert receipt.criteria_confidence == 0.7
    assert receipt.completeness_status == "complete"
    assert receipt.decision_reasoning == "Semantic mock passed."
    assert receipt.required_next_action == "Proceed to accept_node (open evidence PR)."
