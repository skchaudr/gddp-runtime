from __future__ import annotations

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
        "confidence": 0.8,
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


def test_verdict_receipt_confidence_is_legacy_alias_for_criteria_confidence() -> None:
    receipt = VerdictReceipt.model_validate(_receipt_payload())

    assert receipt.confidence == receipt.criteria_confidence == 0.8


def test_verdict_receipt_accepts_legacy_confidence_only_payload() -> None:
    payload = _receipt_payload()
    del payload["criteria_confidence"]
    del payload["completeness_status"]

    receipt = VerdictReceipt.model_validate(payload)

    assert receipt.confidence == receipt.criteria_confidence == 0.8
    assert receipt.completeness_status == "not-run"


def test_verdict_receipt_rejects_confidence_alias_mismatch() -> None:
    with pytest.raises(ValidationError, match="compatibility alias"):
        VerdictReceipt.model_validate(_receipt_payload(criteria_confidence=0.7))
