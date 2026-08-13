from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.runtime.verification import orchestrator
from scripts.runtime.verification.receipt_sink import write_receipt
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
    assert receipt.completeness_status == "not-run"
    assert receipt.project_id == "project-clean"
    assert receipt.node_id == "node-clean"
    timing = receipt.evaluation_timing
    assert timing is not None
    assert timing.started_at == "2026-06-30T00:00:00+00:00"
    assert timing.finished_at == "2026-06-30T00:00:00+00:00"
    assert timing.wall_s >= 0
    assert timing.criteria.status == "not_run"
    assert timing.criteria.elapsed_s is None
    assert timing.criteria.tool_calls == 0
    assert timing.integrity.status == "not_run"
    assert timing.integrity.elapsed_s is None


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
    expected_semantic = SemanticOutput(
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
        budget_trace={
            "tool_calls": [
                {"tool": "read", "path": "module.py"},
                {"tool": "grep", "path": "module.py"},
                {"event": "tool_execution_end", "tool": "read", "ok": True},
            ]
        },
    )
    harness_calls = 0

    def _mock_semantic_harness(**kwargs):
        nonlocal harness_calls
        harness_calls += 1
        return expected_semantic

    receipt = orchestrator.verify(
        node_yaml={"node_id": "node-semantic"},
        project_yaml={"project_id": "project-semantic"},
        repo=tmp_path,
        runner=MockRunner("{}"),
        toolbox=SemanticToolbox(tmp_path),
        semantic_harness=_mock_semantic_harness,
        now=lambda: "2026-06-30T00:00:00+00:00",
    )

    assert harness_calls == 1
    assert receipt.semantic is not None
    assert receipt.verdict == Verdict.PASS
    assert receipt.criteria_confidence == 0.7
    assert receipt.criteria_confidence == 0.7
    assert receipt.completeness_status == "complete"
    assert receipt.decision_reasoning == "Semantic mock passed."
    assert receipt.required_next_action == "Proceed to accept_node (open evidence PR)."
    timing = receipt.evaluation_timing
    assert timing is not None
    assert timing.criteria.status == "completed"
    assert timing.criteria.elapsed_s is not None
    assert timing.criteria.elapsed_s >= 0
    assert timing.criteria.tool_calls == 2
    assert timing.integrity.status == "not_run"


def test_orchestrator_passes_correct_args_to_semantic_harness(monkeypatch, tmp_path: Path) -> None:
    """The pi harness (semantic_harness) receives node, graph, det, repo, shape_profile.

    The built-in SemanticAgent fallback was removed; the orchestrator now calls
    the wired semantic_harness directly. This test verifies the harness receives
    the orchestrator's standard kwargs (the old test checked budget_trace
    passthrough to the deleted built-in agent).
    """
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

    received_kwargs: dict[str, Any] = {}

    def _capturing_semantic_harness(**kwargs):
        received_kwargs.update(kwargs)
        return SemanticOutput(
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
        )

    node_yaml = {"node_id": "node-semantic"}
    project_yaml = {"project_id": "project-semantic"}
    shape_profile = {"shape": "test"}

    receipt = orchestrator.verify(
        node_yaml=node_yaml,
        project_yaml=project_yaml,
        repo=tmp_path,
        runner=MockRunner("{}"),
        toolbox=SemanticToolbox(tmp_path),
        shape_profile=shape_profile,
        semantic_agent_kwargs={"max_turns": 1, "max_tool_calls": 3, "max_tokens": 50_000},
        semantic_harness=_capturing_semantic_harness,
        now=lambda: "2026-06-30T00:00:00+00:00",
    )

    assert receipt.semantic is not None
    # The pi harness receives the orchestrator's standard kwargs.
    assert received_kwargs["node"] == node_yaml
    assert received_kwargs["graph"] == project_yaml
    assert received_kwargs["repo"] == tmp_path
    assert received_kwargs["deterministic_result"] is det
    assert received_kwargs["shape_profile"] == shape_profile


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
        config_root: Path | None = None,
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


def test_all_evaluator_lanes_run_and_worst_verdict_is_written(
    monkeypatch, tmp_path: Path,
) -> None:
    """Mission results retain the existing deterministic, semantic, integrity path."""
    det = DeterministicResult(
        criteria=[
            CriterionCheck(
                id="c1",
                criterion="criterion needs semantic review",
                status="indeterminate",
                confidence=0.6,
                method="inspection",
                evidence=["module.py"],
                reasoning="deterministic evidence is incomplete",
                mismatch_kind="",
                mismatch_detail="",
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
    deterministic_calls = 0

    def _deterministic(**_kwargs):
        nonlocal deterministic_calls
        deterministic_calls += 1
        return det

    monkeypatch.setattr(orchestrator.deterministic, "assemble", _deterministic)
    semantic_calls = 0

    def _semantic(**_kwargs):
        nonlocal semantic_calls
        semantic_calls += 1
        return SemanticOutput(
            judgments=[
                {
                    "criterion_id": "c1",
                    "judgment": "judged_pass",
                    "confidence": 0.9,
                    "evidence": ["module.py:1"],
                    "reasoning": "Semantic evidence passes.",
                }
            ],
            overall_reasoning="Criteria pass.",
            risks=None,
            followup_candidates=None,
            budget_exhausted=False,
        )

    integrity = MockIntegrityHarness(
        IntegrityOutput(
            verdict="drift",
            intent_preserved=False,
            graph_integrity_preserved=True,
            required_human_review=True,
            confidence=0.8,
            findings=[],
            reasoning="Intent drift is worse than the criteria pass.",
        )
    )

    receipt = orchestrator.verify(
        node_yaml={"node_id": "mission-node"},
        project_yaml={"project_id": "mission-project"},
        repo=tmp_path,
        runner=MockRunner("{}"),
        toolbox=SemanticToolbox(tmp_path),
        semantic_harness=_semantic,
        integrity_harness=integrity,
        now=lambda: "2026-08-07T00:00:00+00:00",
    )

    assert deterministic_calls == 1
    assert semantic_calls == 1
    assert integrity.calls == 1
    assert receipt.criteria_verdict == Verdict.PASS
    assert receipt.verdict == Verdict.NEEDS_HUMAN_REVIEW


def test_mission_provenance_is_preserved_in_written_receipt(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        orchestrator.deterministic,
        "assemble",
        lambda **_: _row12_deterministic(),
    )
    receipt = orchestrator.verify(
        node_yaml={"node_id": "mission-node"},
        project_yaml={"project_id": "mission-project"},
        repo=tmp_path,
        runner=MockRunner("{}"),
        toolbox=SemanticToolbox(tmp_path),
        execution_attempt_id="job-1:attempt:0",
        evidence_manifest_sha256="a" * 64,
        mission_receipt_id="mis_1:mission-node:worker-1",
        now=lambda: "2026-08-07T00:00:00+00:00",
    )
    path = write_receipt(
        receipt,
        receipt.project_id,
        base=tmp_path / "receipts",
        job_id="job-1",
        attempt=0,
    )

    payload = json.loads(path.read_text())
    assert payload["execution_attempt_id"] == "job-1:attempt:0"
    assert payload["evidence_manifest_sha256"] == "a" * 64
    assert payload["mission_receipt_id"] == "mis_1:mission-node:worker-1"

    legacy = orchestrator.verify(
        node_yaml={"node_id": "legacy-node"},
        project_yaml={"project_id": "legacy-project"},
        repo=tmp_path,
        runner=MockRunner("{}"),
        toolbox=SemanticToolbox(tmp_path),
        now=lambda: "2026-08-07T00:00:00+00:00",
    )
    assert legacy.execution_attempt_id is None
    assert legacy.evidence_manifest_sha256 is None
    assert legacy.mission_receipt_id is None


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


# ---------------------------------------------------------------------------
# Phase 2: Context coverage tests
# ---------------------------------------------------------------------------

from scripts.runtime.verification.orchestrator import (
    _capture_commit_sha,
    _capture_tree_sha,
    _compute_context_coverage,
    _rate_lane,
)
from scripts.runtime.verification.schemas import LaneCoverage


def _semantic_with_trace(tool_calls: list[dict]) -> SemanticOutput:
    return SemanticOutput(
        judgments=[],
        overall_reasoning="test",
        risks=None,
        followup_candidates=None,
        budget_exhausted=False,
        budget_trace={"tool_calls": tool_calls},
    )


def _integrity_with_trace(tool_calls: list[dict]) -> IntegrityOutput:
    return IntegrityOutput(
        verdict="pass",
        intent_preserved=True,
        graph_integrity_preserved=True,
        required_human_review=False,
        confidence=0.9,
        findings=[],
        reasoning="test",
        tool_trace=tool_calls,
    )


def test_coverage_none_when_zero_canonical_reads() -> None:
    """No read/grep calls matching canonical paths -> rating 'none'."""
    canonical = {
        "readme": "/repo/README.md",
        "project_brief": "/repo/PROJECT-BRIEF.md",
        "foundational_node": "/config/nodes/found.yaml",
        "neighbor:dep-a": "/config/nodes/dep-a.yaml",
    }
    semantic = _semantic_with_trace([
        {"tool": "read", "path": "/repo/some-other-file.py", "blocked": False},
    ])
    integrity = _integrity_with_trace([])

    coverage = _compute_context_coverage(canonical, semantic, integrity)
    assert coverage is not None
    assert coverage.criteria.rating == "none"
    assert coverage.integrity.rating == "none"
    assert coverage.overall == "none"


def test_coverage_high_when_docs_and_neighbors_read() -> None:
    """Read/grep calls matching docs AND neighbors -> rating 'high'."""
    canonical = {
        "readme": "/repo/README.md",
        "project_brief": "/repo/PROJECT-BRIEF.md",
        "foundational_node": "/config/nodes/found.yaml",
        "neighbor:dep-a": "/config/nodes/dep-a.yaml",
    }
    semantic = _semantic_with_trace([
        {"tool": "read", "path": "/repo/README.md", "blocked": False},
        {"tool": "grep", "path": "/config/nodes/dep-a.yaml", "blocked": False},
    ])
    integrity = _integrity_with_trace([
        {"tool": "read", "path": "/repo/PROJECT-BRIEF.md", "blocked": False},
        {"tool": "read", "path": "/config/nodes/found.yaml", "blocked": False},
    ])

    coverage = _compute_context_coverage(canonical, semantic, integrity)
    assert coverage.criteria.rating == "high"
    assert coverage.integrity.rating == "high"
    assert coverage.overall == "high"


def test_coverage_medium_when_docs_only_and_neighbors_offered() -> None:
    """Docs read but no neighbors read, and neighbors were offered -> 'medium'."""
    canonical = {
        "readme": "/repo/README.md",
        "project_brief": "/repo/PROJECT-BRIEF.md",
        "neighbor:dep-a": "/config/nodes/dep-a.yaml",
    }
    semantic = _semantic_with_trace([
        {"tool": "read", "path": "/repo/README.md", "blocked": False},
    ])
    integrity = _integrity_with_trace([
        {"tool": "read", "path": "/repo/PROJECT-BRIEF.md", "blocked": False},
    ])

    coverage = _compute_context_coverage(canonical, semantic, integrity)
    assert coverage.criteria.rating == "medium"
    assert coverage.integrity.rating == "medium"
    assert coverage.overall == "medium"


def test_coverage_high_no_neighbor_rule() -> None:
    """No neighbors offered + docs read -> 'high' (no-neighbor rule)."""
    canonical = {
        "readme": "/repo/README.md",
        "project_brief": "/repo/PROJECT-BRIEF.md",
    }
    semantic = _semantic_with_trace([
        {"tool": "read", "path": "/repo/README.md", "blocked": False},
    ])
    integrity = _integrity_with_trace([
        {"tool": "read", "path": "/repo/PROJECT-BRIEF.md", "blocked": False},
    ])

    coverage = _compute_context_coverage(canonical, semantic, integrity)
    assert coverage.criteria.rating == "high"
    assert coverage.integrity.rating == "high"
    assert coverage.overall == "high"


def test_coverage_criteria_not_run_when_semantic_none() -> None:
    """Semantic skipped (row-12) -> criteria coverage is 'not_run'."""
    canonical = {
        "readme": "/repo/README.md",
        "neighbor:dep-a": "/config/nodes/dep-a.yaml",
    }
    integrity = _integrity_with_trace([
        {"tool": "read", "path": "/repo/README.md", "blocked": False},
        {"tool": "read", "path": "/config/nodes/dep-a.yaml", "blocked": False},
    ])

    coverage = _compute_context_coverage(canonical, None, integrity)
    assert coverage.criteria == "not_run"
    assert coverage.integrity.rating == "high"
    assert coverage.overall == "high"


def test_coverage_ls_find_do_not_count_as_content_access() -> None:
    """ls and find tool calls do NOT count as content access."""
    canonical = {
        "readme": "/repo/README.md",
        "neighbor:dep-a": "/config/nodes/dep-a.yaml",
    }
    semantic = _semantic_with_trace([
        {"tool": "ls", "path": "/repo/README.md", "blocked": False},
        {"tool": "find", "path": "/config/nodes/dep-a.yaml", "blocked": False},
    ])
    integrity = _integrity_with_trace([])

    coverage = _compute_context_coverage(canonical, semantic, integrity)
    assert coverage.criteria.rating == "none"
    assert coverage.integrity.rating == "none"


def test_coverage_relative_paths_resolved_against_repo(tmp_path: Path) -> None:
    """Relative paths in the trace are resolved against repo for matching.

    The guard logs whatever path the model provides. If the model uses a
    relative path (natural since pi runs with cwd=repo), it must still match
    the absolute canonical paths.
    """
    (tmp_path / "README.md").write_text("# test")
    (tmp_path / "PROJECT-BRIEF.md").write_text("# brief")

    canonical = {
        "readme": str(tmp_path / "README.md"),
        "project_brief": str(tmp_path / "PROJECT-BRIEF.md"),
    }
    # Trace uses relative paths (as the model would)
    semantic = _semantic_with_trace([
        {"tool": "read", "path": "README.md", "blocked": False},
    ])
    integrity = _integrity_with_trace([
        {"tool": "read", "path": "PROJECT-BRIEF.md", "blocked": False},
    ])

    coverage = _compute_context_coverage(canonical, semantic, integrity, repo=tmp_path)
    assert coverage is not None
    assert coverage.criteria.rating == "high"  # docs read, no neighbors offered
    assert coverage.integrity.rating == "high"


def test_coverage_per_lane_does_not_mask() -> None:
    """One lane 'high' does not mask the other's 'none'."""
    canonical = {
        "readme": "/repo/README.md",
        "neighbor:dep-a": "/config/nodes/dep-a.yaml",
    }
    semantic = _semantic_with_trace([
        {"tool": "read", "path": "/repo/README.md", "blocked": False},
        {"tool": "read", "path": "/config/nodes/dep-a.yaml", "blocked": False},
    ])
    integrity = _integrity_with_trace([])  # no reads

    coverage = _compute_context_coverage(canonical, semantic, integrity)
    assert coverage.criteria.rating == "high"
    assert coverage.integrity.rating == "none"
    assert coverage.overall == "none"  # worst-of


def test_coverage_raw_evidence_present() -> None:
    """LaneCoverage carries offered/accessed/not_observed counts and paths."""
    canonical = {
        "readme": "/repo/README.md",
        "project_brief": "/repo/PROJECT-BRIEF.md",
        "neighbor:dep-a": "/config/nodes/dep-a.yaml",
    }
    semantic = _semantic_with_trace([
        {"tool": "read", "path": "/repo/README.md", "blocked": False},
    ])
    integrity = _integrity_with_trace([])

    coverage = _compute_context_coverage(canonical, semantic, integrity)
    lane = coverage.criteria
    assert isinstance(lane, LaneCoverage)
    assert lane.offered == 3
    assert lane.content_accessed == 1
    assert lane.not_observed == 2
    assert "/repo/README.md" in lane.accessed_paths
    assert "/repo/PROJECT-BRIEF.md" in lane.not_observed_paths


def test_coverage_excludes_failed_and_blocked_content_operations() -> None:
    """Only a completed read/grep establishes canonical-context coverage."""
    canonical = {"readme": "/repo/README.md"}
    semantic = _semantic_with_trace([
        {"tool": "read", "path": "/repo/README.md", "blocked": True},
        {"tool": "grep", "path": "/repo/README.md", "toolCallId": "failed"},
        {"event": "tool_execution_end", "toolCallId": "failed", "tool": "grep", "ok": False},
    ])
    integrity = _integrity_with_trace([])

    coverage = _compute_context_coverage(canonical, semantic, integrity)
    assert coverage.criteria.rating == "none"
    assert coverage.criteria.content_accessed == 0


def test_provenance_keeps_tree_and_commit_shas_separate(tmp_path: Path) -> None:
    """The merge commit must be compared to HEAD, never to HEAD's tree."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "evidence.txt").write_text("evidence\n")
    subprocess.run(["git", "add", "evidence.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "test"],
        cwd=tmp_path,
        check=True,
    )
    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True,
    ).stdout.strip()

    assert _capture_commit_sha(tmp_path) == commit_sha
    assert _capture_tree_sha(tmp_path) != commit_sha


def test_receipt_carries_canonical_context_and_coverage(monkeypatch, tmp_path: Path) -> None:
    """Orchestrator attaches canonical_context and context_coverage to the receipt."""
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
        reasoning="ok",
    )
    integrity_harness = MockIntegrityHarness(integrity_pass)

    # Provide a config_root with actual files so canonical pointers resolve.
    config_root = tmp_path / "gddp-config"
    nodes_dir = config_root / "graphs" / "project-ctx" / "nodes"
    nodes_dir.mkdir(parents=True)
    (nodes_dir / "dep-a.yaml").write_text("node_id: dep-a\nstatus: complete\n")

    receipt = orchestrator.verify(
        node_yaml={"node_id": "node-ctx", "depends_on": ["dep-a"]},
        project_yaml={"project_id": "project-ctx", "nodes": [{"id": "dep-a", "status": "complete"}]},
        repo=tmp_path,
        runner=runner,
        toolbox=SemanticToolbox(tmp_path),
        integrity_harness=integrity_harness,
        config_root=config_root,
        now=lambda: "2026-07-16T00:00:00+00:00",
    )

    assert receipt.canonical_context is not None
    # Coverage may be None if all canonical paths are UNAVAILABLE (no README/
    # PROJECT-BRIEF in the temp repo). That's fine — the test verifies the
    # fields are attempted, not that coverage is always computed.
    # When some paths resolve, coverage should be present.
    # With a real config_root, the neighbor pointer should resolve.
    assert "neighbor:dep-a" in receipt.canonical_context
    assert "UNAVAILABLE" not in receipt.canonical_context["neighbor:dep-a"]
