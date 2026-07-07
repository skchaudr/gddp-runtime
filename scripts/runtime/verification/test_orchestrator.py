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


class CapturingRunner:
    def __init__(self) -> None:
        self.calls = 0
        self.message_count = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]):
        self.calls += 1
        self.message_count = len(messages)
        from scripts.runtime.verification.semantic.agent import LLMResponse, ToolCall

        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="verdict-1",
                    name="submit_verdict",
                    args={
                        "judgments": [
                            {
                                "criterion_id": "c1",
                                "judgment": "judged_pass",
                                "confidence": 0.7,
                                "evidence": ["module.py:1"],
                                "reasoning": "Mock semantic evidence matched the criterion.",
                            }
                        ],
                        "overall_reasoning": "Semantic mock passed.",
                        "risks": None,
                        "followup_candidates": None,
                        "budget_exhausted": False,
                    },
                )
            ],
            finish_reason="tool_use",
        )


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


def test_orchestrator_passes_semantic_agent_budget_kwargs(monkeypatch, tmp_path: Path) -> None:
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
    runner = CapturingRunner()

    receipt = orchestrator.verify(
        node_yaml={"node_id": "node-semantic"},
        project_yaml={"project_id": "project-semantic"},
        repo=tmp_path,
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        semantic_agent_kwargs={"max_turns": 1, "max_tool_calls": 3, "max_tokens": 50_000},
        now=lambda: "2026-06-30T00:00:00+00:00",
    )

    assert receipt.semantic is not None
    assert receipt.semantic.budget_trace is not None
    assert receipt.semantic.budget_trace["max_turns"] == 1
    assert receipt.semantic.budget_trace["max_tool_calls"] == 3
    assert receipt.semantic.budget_trace["max_tokens"] == 50_000


# ---------------------------------------------------------------------------
# Lane 2 integrity tests — fresh-eyes drift review
# ---------------------------------------------------------------------------

from scripts.runtime.verification.schemas import (
    IntegrityFinding,
    IntegrityOutput,
)


class MockIntegrityHarness:
    """Mock integrity harness that returns a canned IntegrityOutput (no live pi)."""

    def __init__(self, output: IntegrityOutput) -> None:
        self.output = output
        self.calls = 0
        self.last_node: dict[str, Any] = {}
        self.last_graph: dict[str, Any] = {}

    def __call__(
        self,
        *,
        node: dict[str, Any],
        graph: dict[str, Any],
        deterministic_result: Any,
        repo: Path,
    ) -> IntegrityOutput:
        self.calls += 1
        self.last_node = node
        self.last_graph = graph
        return self.output


def _row12_deterministic() -> DeterministicResult:
    return DeterministicResult(
        criteria=[
            CriterionCheck(
                id="c1",
                criterion="all criteria pass",
                status="pass",
                confidence=0.95,
                method="test",
                evidence=["result.md"],
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


def test_integrity_runs_on_row12_clean_pass(monkeypatch, tmp_path: Path) -> None:
    """Integrity lane MUST run even when deterministic criteria all pass (row-12)."""
    det = _row12_deterministic()
    monkeypatch.setattr(orchestrator.deterministic, "assemble", lambda **_: det)
    runner = MockRunner("{}")

    integrity_pass = IntegrityOutput(
        verdict="pass",
        intent_preserved=True,
        graph_integrity_preserved=True,
        required_human_review=False,
        confidence=0.95,
        findings=[],
        reasoning="Everything checks out.",
    )
    integrity_harness = MockIntegrityHarness(integrity_pass)

    receipt = orchestrator.verify(
        node_yaml={"node_id": "node-row12"},
        project_yaml={"project_id": "project-row12"},
        repo=tmp_path,
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        integrity_harness=integrity_harness,
        now=lambda: "2026-06-30T00:00:00+00:00",
    )

    # Integrity harness WAS called — row-12 does NOT bypass it
    assert integrity_harness.calls == 1
    # Semantic skipped (deterministic all-pass), integrity ran
    assert runner.calls == 0
    assert receipt.semantic is None
    # Both lanes pass => combined verdict is PASS
    assert receipt.verdict == Verdict.PASS
    assert receipt.criteria_verdict == Verdict.PASS
    assert receipt.integrity is not None
    assert receipt.integrity.verdict == "pass"


def test_criteria_pass_but_intent_violated_yields_non_pass_verdict(
    monkeypatch, tmp_path: Path,
) -> None:
    """Node-mandated fixture: criteria all pass, integrity detects intent violation.

    Row-12 criteria pass becomes needs-human-review because the integrity lane
    catches a drift that the criteria lane did not (and cannot) see.
    """
    det = _row12_deterministic()
    monkeypatch.setattr(orchestrator.deterministic, "assemble", lambda **_: det)
    runner = MockRunner("{}")

    # Integrity says drift: intent is violated even though criteria pass
    integrity_drift = IntegrityOutput(
        verdict="drift",
        intent_preserved=False,
        graph_integrity_preserved=True,
        required_human_review=True,
        confidence=0.85,
        findings=[
            IntegrityFinding(
                severity="high",
                summary="Scope creep: the implementation adds a feature not in the node's intent.",
                affected_node_ids=["node-drift"],
            )
        ],
        reasoning="The change implements an extra module that was not part of the node's stated why.",
    )
    integrity_harness = MockIntegrityHarness(integrity_drift)

    receipt = orchestrator.verify(
        node_yaml={"node_id": "node-drift"},
        project_yaml={"project_id": "project-drift"},
        repo=tmp_path,
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        integrity_harness=integrity_harness,
        now=lambda: "2026-06-30T00:00:00+00:00",
    )

    # Integrity harness was called
    assert integrity_harness.calls == 1
    # Criteria verdict still PASS (lane 1's answer preserved)
    assert receipt.criteria_verdict == Verdict.PASS
    # Combined verdict is needs-human-review (worse of the two)
    assert receipt.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert receipt.integrity is not None
    assert receipt.integrity.verdict == "drift"
    assert receipt.integrity.required_human_review is True
    assert receipt.integrity.intent_preserved is False
    # Action must mention human review and halt progression
    assert "Human review required" in receipt.required_next_action


def test_integrity_harness_none_does_not_run_integrity(
    monkeypatch, tmp_path: Path,
) -> None:
    """When integrity_harness is None, integrity field is None (skeleton default)."""
    det = _row12_deterministic()
    monkeypatch.setattr(orchestrator.deterministic, "assemble", lambda **_: det)
    runner = MockRunner("{}")

    receipt = orchestrator.verify(
        node_yaml={"node_id": "node-no-integrity"},
        project_yaml={"project_id": "project-no-integrity"},
        repo=tmp_path,
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        integrity_harness=None,
        now=lambda: "2026-06-30T00:00:00+00:00",
    )

    assert receipt.verdict == Verdict.PASS
    assert receipt.criteria_verdict == Verdict.PASS
    assert receipt.integrity is None


def test_integrity_harness_receives_node_and_graph(
    monkeypatch, tmp_path: Path,
) -> None:
    """The integrity harness receives the same node/graph as the orchestrator."""
    det = _row12_deterministic()
    monkeypatch.setattr(orchestrator.deterministic, "assemble", lambda **_: det)
    runner = MockRunner("{}")

    integrity_pass = IntegrityOutput(
        verdict="pass",
        intent_preserved=True,
        graph_integrity_preserved=True,
        required_human_review=False,
        confidence=0.9,
        findings=[],
        reasoning="Looks good.",
    )
    integrity_harness = MockIntegrityHarness(integrity_pass)

    node = {"node_id": "node-target", "why": "deliver auth middleware"}
    graph = {"project_id": "project-target", "nodes": ["node-target"]}

    orchestrator.verify(
        node_yaml=node,
        project_yaml=graph,
        repo=tmp_path,
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        integrity_harness=integrity_harness,
        now=lambda: "2026-06-30T00:00:00+00:00",
    )

    assert integrity_harness.last_node == node
    assert integrity_harness.last_graph == graph
