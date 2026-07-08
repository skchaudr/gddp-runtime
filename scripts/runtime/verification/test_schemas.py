from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.runtime.verification.schemas import (
    DeterministicResult,
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
        "criteria_confidence": 0.8,
        "completeness_status": "not-run",
        "deterministic": _deterministic(),
        "semantic": None,
        "decision_reasoning": "ok",
        "required_next_action": "review",
        "generated_at": "2026-07-02T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def test_verdict_receipt_has_no_confidence_alias_field() -> None:
    receipt = VerdictReceipt.model_validate(_receipt_payload())

    assert receipt.criteria_confidence == 0.8
    assert "confidence" not in receipt.model_dump()


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
