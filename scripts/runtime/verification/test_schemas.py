from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.runtime.verification.schemas import (
    DeterministicResult,
    GraphRecommendation,
    IntegrityOutput,
    Verdict,
    VerdictReceipt,
)


def _deterministic() -> DeterministicResult:
    return DeterministicResult(
        criteria=[],
        constraints=[],
        artifacts_present={},
        deps_status={},
        criteria_mismatches=[],
        missing_evidence=[],
        human_review_questions=[],
    )


def _receipt_payload(**overrides):
    payload = {
        "project_id": "project-a",
        "node_id": "node-a",
        "verdict": Verdict.PASS,
        "confidence": 0.8,
        "criteria_confidence": 0.8,
        "completeness": 1.0,
        "graph_readiness": 0.8,
        "completeness_status": "not-run",
        "deterministic": _deterministic(),
        "semantic": None,
        "decision_reasoning": "ok",
        "required_next_action": "review",
        "generated_at": "2026-07-02T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def test_verdict_receipt_populates_multiple_axes() -> None:
    payload = _receipt_payload(
        criteria_confidence=0.95,
        completeness=0.5,
        graph_readiness=0.0
    )
    receipt = VerdictReceipt.model_validate(payload)

    assert receipt.criteria_confidence == 0.95
    assert receipt.completeness == 0.5
    assert receipt.graph_readiness == 0.0


def test_verdict_receipt_accepts_legacy_confidence_only_payload() -> None:
    payload = _receipt_payload()
    del payload["criteria_confidence"]
    del payload["completeness_status"]
    payload["confidence"] = 0.8

    receipt = VerdictReceipt.model_validate(payload)

    assert receipt.criteria_confidence == 0.8
    assert receipt.completeness_status == "not-run"


def test_verdict_receipt_requires_some_confidence_value() -> None:
    payload = _receipt_payload()
    del payload["criteria_confidence"]
    del payload["confidence"]

    with pytest.raises(ValidationError):
        VerdictReceipt.model_validate(payload)


def test_ambiguity_receipt_fixtures_validate_contract() -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "verification_receipts"
    fixture_paths = [
        fixture_dir / "semantic-pass-with-missing-artifacts.json",
        fixture_dir / "semantic-fail-with-complete-artifacts.json",
    ]

    receipts = [VerdictReceipt.model_validate(json.loads(path.read_text(encoding="utf-8"))) for path in fixture_paths]

    semantic_pass_missing_artifacts, semantic_fail_complete_artifacts = receipts
    assert semantic_pass_missing_artifacts.semantic is not None
    assert semantic_pass_missing_artifacts.semantic.judgments[0].judgment == "judged_pass"
    assert semantic_pass_missing_artifacts.deterministic.artifacts_present["decision.md"] is False
    assert semantic_pass_missing_artifacts.verdict == Verdict.NEEDS_MORE_EVIDENCE

    assert semantic_fail_complete_artifacts.semantic is not None
    assert semantic_fail_complete_artifacts.semantic.judgments[0].judgment == "judged_fail"
    assert all(semantic_fail_complete_artifacts.deterministic.artifacts_present.values())
    assert semantic_fail_complete_artifacts.verdict == Verdict.FAIL


# ---------------------------------------------------------------------------
# Phase 1: Provenance fields
# ---------------------------------------------------------------------------


def test_receipt_provenance_fields_default_none_for_legacy() -> None:
    """Legacy receipts without provenance fields load with None."""
    payload = _receipt_payload()
    receipt = VerdictReceipt.model_validate(payload)
    assert receipt.evaluated_tree_sha is None
    assert receipt.merge_commit_sha is None
    assert receipt.pr_ref is None
    assert receipt.job_id is None


def test_receipt_provenance_fields_round_trip() -> None:
    """New receipts with provenance fields round-trip correctly."""
    payload = _receipt_payload(
        evaluated_tree_sha="abc123tree",
        merge_commit_sha="abc123commit",
        pr_ref="42",
        job_id="job_20260716",
    )
    receipt = VerdictReceipt.model_validate(payload)
    assert receipt.evaluated_tree_sha == "abc123tree"
    assert receipt.merge_commit_sha == "abc123commit"
    assert receipt.pr_ref == "42"
    assert receipt.job_id == "job_20260716"
    # Round-trip through JSON
    js = receipt.model_dump_json()
    restored = VerdictReceipt.model_validate_json(js)
    assert restored.evaluated_tree_sha == "abc123tree"
    assert restored.merge_commit_sha == "abc123commit"


def test_evaluation_timing_defaults_none_and_round_trips() -> None:
    legacy = VerdictReceipt.model_validate(_receipt_payload())
    assert legacy.evaluation_timing is None

    payload = _receipt_payload(
        evaluation_timing={
            "started_at": "2026-08-13T00:00:00+00:00",
            "finished_at": "2026-08-13T00:01:00+00:00",
            "wall_s": 60.0,
            "criteria": {"status": "completed", "elapsed_s": 40.0, "tool_calls": 3},
            "integrity": {"status": "timed-out", "elapsed_s": 20.0, "tool_calls": 1},
        }
    )
    receipt = VerdictReceipt.model_validate(payload)
    restored = VerdictReceipt.model_validate_json(receipt.model_dump_json())
    assert restored.evaluation_timing is not None
    assert restored.evaluation_timing.wall_s == 60.0
    assert restored.evaluation_timing.criteria.tool_calls == 3
    assert restored.evaluation_timing.integrity.status == "timed-out"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("execution_attempt_id", "job-1:attempt:0"),
        ("evidence_manifest_sha256", "a" * 64),
        ("mission_receipt_id", "mission-receipt-1"),
    ],
)
def test_receipt_mission_provenance_is_optional_and_round_trips(
    field_name: str,
    value: str,
) -> None:
    legacy_receipt = VerdictReceipt.model_validate(_receipt_payload())
    assert getattr(legacy_receipt, field_name) is None

    receipt = VerdictReceipt.model_validate(
        _receipt_payload(**{field_name: value})
    )
    restored = VerdictReceipt.model_validate_json(receipt.model_dump_json())

    assert getattr(restored, field_name) == value


def test_integrity_output_legacy_receipt_parses_without_recommendations() -> None:
    integrity = IntegrityOutput(
        verdict="pass",
        intent_preserved=True,
        graph_integrity_preserved=True,
        required_human_review=False,
        confidence=0.9,
        findings=[],
        reasoning="ok",
    )
    assert integrity.graph_recommendations is None
    restored = IntegrityOutput.model_validate_json(integrity.model_dump_json())
    assert restored.graph_recommendations is None


def test_graph_recommendation_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        GraphRecommendation(
            action="create_node",
            affected_node_ids=["node-x"],
            rationale="missing work",
            evidence=[],
        )


def test_graph_recommendation_round_trips() -> None:
    rec = GraphRecommendation(
        action="create_node",
        affected_node_ids=["node-13"],
        rationale="Missing continuation.",
        evidence=["src/foo.py:12"],
        draft_node_yaml="node_id: node-13\n",
    )
    restored = GraphRecommendation.model_validate(rec.model_dump())
    assert restored.action == "create_node"
    assert restored.draft_node_yaml == "node_id: node-13\n"
