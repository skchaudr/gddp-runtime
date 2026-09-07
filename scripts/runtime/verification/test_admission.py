from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.runtime.verification.admission import (
    ReceiptAdmissionError,
    read_validated_receipt,
    receipt_admits,
    receipt_is_complete,
)
from scripts.runtime.verification.schemas import (
    DeterministicResult,
    IntegrityFinding,
    IntegrityOutput,
    LaneExecutionStatus,
    SemanticOutput,
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


def make_receipt_fixture(
    path: Path,
    *,
    project_id: str = "proj-1",
    node_id: str = "node-1",
    job_id: str = "job-1",
    execution_attempt_id: str = "job-1:attempt:0",
    result_commit_sha: str = "b" * 40,
    expected_base_commit_sha: str | None = "a" * 40,
    verdict: Verdict | str = Verdict.PASS,
    criteria_verdict: Verdict | str | None = Verdict.PASS,
    completeness_status: str = "complete",
    semantic_status: LaneExecutionStatus | str = LaneExecutionStatus.COMPLETED,
    integrity_status: LaneExecutionStatus | str = LaneExecutionStatus.COMPLETED,
    intent_preserved: bool = True,
    graph_integrity_preserved: bool = True,
    required_human_review: bool = False,
    integrity_verdict: str = "pass",
    findings: list[IntegrityFinding] | None = None,
    reasoning: str = "evaluation succeeded",
) -> VerdictReceipt:
    semantic = SemanticOutput(
        judgments=[],
        overall_reasoning="semantic ok",
        risks=None,
        followup_candidates=None,
        budget_exhausted=False,
        lane_status=(
            semantic_status
            if isinstance(semantic_status, LaneExecutionStatus)
            else LaneExecutionStatus(semantic_status)
        ),
    )
    integrity = IntegrityOutput(
        verdict=integrity_verdict,
        intent_preserved=intent_preserved,
        graph_integrity_preserved=graph_integrity_preserved,
        required_human_review=required_human_review,
        confidence=0.95,
        findings=findings or [],
        reasoning=reasoning,
        lane_status=(
            integrity_status
            if isinstance(integrity_status, LaneExecutionStatus)
            else LaneExecutionStatus(integrity_status)
        ),
    )
    receipt = VerdictReceipt(
        project_id=project_id,
        node_id=node_id,
        verdict=verdict if isinstance(verdict, Verdict) else Verdict(verdict),
        criteria_verdict=(
            criteria_verdict
            if isinstance(criteria_verdict, Verdict) or criteria_verdict is None
            else Verdict(criteria_verdict)
        ),
        integrity=integrity,
        confidence=0.95,
        criteria_confidence=0.95,
        completeness=1.0,
        graph_readiness=1.0,
        completeness_status=completeness_status,
        deterministic=_deterministic(),
        semantic=semantic,
        decision_reasoning=reasoning,
        required_next_action="proceed",
        generated_at="2026-09-07T00:00:00+00:00",
        evaluated_commit_sha=result_commit_sha,
        merge_commit_sha=result_commit_sha,
        expected_base_commit_sha=expected_base_commit_sha,
        job_id=job_id,
        execution_attempt_id=execution_attempt_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    return receipt


def test_read_validated_receipt_success(tmp_path: Path) -> None:
    receipt_file = tmp_path / "receipt.json"
    created = make_receipt_fixture(receipt_file)

    loaded = read_validated_receipt(
        receipt_file,
        project_id="proj-1",
        node_id="node-1",
        job_id="job-1",
        execution_attempt_id="job-1:attempt:0",
        result_commit_sha="b" * 40,
        expected_base_commit_sha="a" * 40,
    )

    assert loaded.project_id == "proj-1"
    assert loaded.verdict == Verdict.PASS
    assert receipt_is_complete(loaded) is True
    assert receipt_admits(loaded) is True


def test_read_validated_receipt_negative_receipt_validates_subject(tmp_path: Path) -> None:
    receipt_file = tmp_path / "negative_receipt.json"
    created = make_receipt_fixture(
        receipt_file,
        verdict=Verdict.FAIL,
        criteria_verdict=Verdict.FAIL,
        intent_preserved=False,
    )

    loaded = read_validated_receipt(
        receipt_file,
        project_id="proj-1",
        node_id="node-1",
        job_id="job-1",
        execution_attempt_id="job-1:attempt:0",
        result_commit_sha="b" * 40,
        expected_base_commit_sha="a" * 40,
    )

    assert loaded.verdict == Verdict.FAIL
    assert receipt_is_complete(loaded) is True
    assert receipt_admits(loaded) is False


def test_read_validated_receipt_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ReceiptAdmissionError, match="receipt file missing"):
        read_validated_receipt(
            tmp_path / "nonexistent.json",
            project_id="proj-1",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
        )


def test_read_validated_receipt_malformed_json(tmp_path: Path) -> None:
    bad_file = tmp_path / "broken.json"
    bad_file.write_text("{broken json content", encoding="utf-8")

    with pytest.raises(ReceiptAdmissionError, match="malformed receipt JSON"):
        read_validated_receipt(
            bad_file,
            project_id="proj-1",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
        )


def test_read_validated_receipt_malformed_encoding(tmp_path: Path) -> None:
    bad_file = tmp_path / "broken_encoding.json"
    bad_file.write_bytes(b"\xff")

    with pytest.raises(ReceiptAdmissionError, match="failed to read receipt file"):
        read_validated_receipt(
            bad_file,
            project_id="proj-1",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
        )


def test_read_validated_receipt_invalid_schema(tmp_path: Path) -> None:
    bad_file = tmp_path / "invalid_schema.json"
    bad_file.write_text(json.dumps({"project_id": "proj-1"}), encoding="utf-8")

    with pytest.raises(ReceiptAdmissionError, match="invalid receipt schema"):
        read_validated_receipt(
            bad_file,
            project_id="proj-1",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
        )


def test_read_validated_receipt_identity_mismatches(tmp_path: Path) -> None:
    receipt_file = tmp_path / "receipt.json"
    make_receipt_fixture(receipt_file)

    # project_id mismatch
    with pytest.raises(ReceiptAdmissionError, match="project_id mismatch"):
        read_validated_receipt(
            receipt_file,
            project_id="other-proj",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
        )

    # node_id mismatch
    with pytest.raises(ReceiptAdmissionError, match="node_id mismatch"):
        read_validated_receipt(
            receipt_file,
            project_id="proj-1",
            node_id="other-node",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
        )

    # job_id mismatch
    with pytest.raises(ReceiptAdmissionError, match="job_id mismatch"):
        read_validated_receipt(
            receipt_file,
            project_id="proj-1",
            node_id="node-1",
            job_id="other-job",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
        )

    # execution_attempt_id mismatch
    with pytest.raises(ReceiptAdmissionError, match="execution_attempt_id mismatch"):
        read_validated_receipt(
            receipt_file,
            project_id="proj-1",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:1",
            result_commit_sha="b" * 40,
        )

    # merge_commit_sha mismatch
    with pytest.raises(ReceiptAdmissionError, match="merge_commit_sha mismatch"):
        read_validated_receipt(
            receipt_file,
            project_id="proj-1",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="c" * 40,
        )

    # expected_base_commit_sha mismatch when set on subject
    with pytest.raises(ReceiptAdmissionError, match="expected_base_commit_sha mismatch"):
        read_validated_receipt(
            receipt_file,
            project_id="proj-1",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
            expected_base_commit_sha="z" * 40,
        )


def test_read_validated_receipt_evaluated_commit_sha_mismatch(tmp_path: Path) -> None:
    receipt_file = tmp_path / "sha_mismatch.json"
    receipt = make_receipt_fixture(receipt_file)
    raw = json.loads(receipt_file.read_text())
    raw["evaluated_commit_sha"] = "e" * 40
    receipt_file.write_text(json.dumps(raw))

    with pytest.raises(ReceiptAdmissionError, match="evaluated_commit_sha mismatch"):
        read_validated_receipt(
            receipt_file,
            project_id="proj-1",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
        )


def test_read_validated_receipt_expected_base_none_on_subject_accepts_any(tmp_path: Path) -> None:
    receipt_file = tmp_path / "receipt.json"
    make_receipt_fixture(receipt_file, expected_base_commit_sha="a" * 40)

    loaded = read_validated_receipt(
        receipt_file,
        project_id="proj-1",
        node_id="node-1",
        job_id="job-1",
        execution_attempt_id="job-1:attempt:0",
        result_commit_sha="b" * 40,
        expected_base_commit_sha=None,
    )
    assert loaded.expected_base_commit_sha == "a" * 40


def test_read_validated_receipt_legacy_missing_identities_rejected(tmp_path: Path) -> None:
    receipt_file = tmp_path / "legacy.json"
    make_receipt_fixture(receipt_file)
    raw = json.loads(receipt_file.read_text())
    raw["job_id"] = None
    raw["execution_attempt_id"] = None
    raw["merge_commit_sha"] = None
    raw["evaluated_commit_sha"] = None
    receipt_file.write_text(json.dumps(raw))

    with pytest.raises(ReceiptAdmissionError):
        read_validated_receipt(
            receipt_file,
            project_id="proj-1",
            node_id="node-1",
            job_id="job-1",
            execution_attempt_id="job-1:attempt:0",
            result_commit_sha="b" * 40,
        )


def test_receipt_admits_gate_conditions(tmp_path: Path) -> None:
    # 1. criteria_verdict is fail
    r1 = make_receipt_fixture(
        tmp_path / "r1.json",
        criteria_verdict=Verdict.FAIL,
    )
    assert receipt_admits(r1) is False

    # 2. completeness_status is partial
    r2 = make_receipt_fixture(
        tmp_path / "r2.json",
        completeness_status="partial",
    )
    assert receipt_admits(r2) is False

    # 3. semantic lane crashed
    r3 = make_receipt_fixture(
        tmp_path / "r3.json",
        semantic_status=LaneExecutionStatus.CRASHED,
    )
    assert receipt_admits(r3) is False
    assert receipt_is_complete(r3) is False

    # 4. integrity lane timed out
    r4 = make_receipt_fixture(
        tmp_path / "r4.json",
        integrity_status=LaneExecutionStatus.TIMED_OUT,
    )
    assert receipt_admits(r4) is False
    assert receipt_is_complete(r4) is False

    # 5. intent not preserved
    r5 = make_receipt_fixture(
        tmp_path / "r5.json",
        intent_preserved=False,
    )
    assert receipt_admits(r5) is False

    # 6. graph integrity not preserved
    r6 = make_receipt_fixture(
        tmp_path / "r6.json",
        graph_integrity_preserved=False,
    )
    assert receipt_admits(r6) is False

    # 7. required_human_review is True
    r7 = make_receipt_fixture(
        tmp_path / "r7.json",
        required_human_review=True,
    )
    assert receipt_admits(r7) is False

    # 8. integrity verdict is drift
    r8 = make_receipt_fixture(
        tmp_path / "r8.json",
        integrity_verdict="drift",
    )
    assert receipt_admits(r8) is False
