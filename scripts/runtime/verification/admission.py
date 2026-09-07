from __future__ import annotations

import json
from pathlib import Path

from .schemas import LaneExecutionStatus, Verdict, VerdictReceipt


class ReceiptAdmissionError(ValueError):
    """Raised when a receipt is missing, malformed, or fails subject binding."""
    pass


def receipt_is_complete(receipt: VerdictReceipt) -> bool:
    """True when both evaluator lanes completed and completeness_status is complete."""
    if receipt.completeness_status != "complete":
        return False
    if receipt.semantic is None:
        return False
    if receipt.semantic.lane_status not in (LaneExecutionStatus.COMPLETED, "completed"):
        return False
    if receipt.integrity is None:
        return False
    if receipt.integrity.lane_status not in (LaneExecutionStatus.COMPLETED, "completed"):
        return False
    return True


def receipt_admits(receipt: VerdictReceipt) -> bool:
    """True when the receipt passes all lane, completeness, and integrity gates.

    A pass requires combined verdict pass, criteria_verdict pass, completeness_status
    complete, completed semantic lane, completed integrity lane, preserved intent and
    graph integrity, and required_human_review false.
    """
    if not receipt_is_complete(receipt):
        return False
    if receipt.verdict not in (Verdict.PASS, "pass"):
        return False
    if receipt.criteria_verdict not in (Verdict.PASS, "pass"):
        return False
    if receipt.integrity is None:
        return False
    if receipt.integrity.verdict not in (Verdict.PASS, "pass"):
        return False
    if receipt.integrity.intent_preserved is not True:
        return False
    if receipt.integrity.graph_integrity_preserved is not True:
        return False
    if receipt.integrity.required_human_review is not False:
        return False
    return True


def read_validated_receipt(
    path: str | Path,
    *,
    project_id: str,
    node_id: str,
    job_id: str,
    execution_attempt_id: str,
    result_commit_sha: str,
    expected_base_commit_sha: str | None = None,
) -> VerdictReceipt:
    """Read and validate a persisted receipt against the durable job/session subject.

    Raises ReceiptAdmissionError for missing, malformed, invalid, or mismatched evidence.
    Validates subject binding for both positive and negative receipts.
    """
    p = Path(path)
    if not p.is_file():
        raise ReceiptAdmissionError(f"receipt file missing: {p}")
    try:
        content = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReceiptAdmissionError(f"failed to read receipt file {p}: {exc}") from exc

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ReceiptAdmissionError(f"malformed receipt JSON in {p}: {exc}") from exc

    if not isinstance(data, dict):
        raise ReceiptAdmissionError(f"receipt payload in {p} must be a JSON object")

    try:
        receipt = VerdictReceipt.model_validate(data)
    except Exception as exc:
        raise ReceiptAdmissionError(f"invalid receipt schema in {p}: {exc}") from exc

    if receipt.project_id != project_id:
        raise ReceiptAdmissionError(
            f"receipt project_id mismatch: {receipt.project_id!r} != {project_id!r}"
        )
    if receipt.node_id != node_id:
        raise ReceiptAdmissionError(
            f"receipt node_id mismatch: {receipt.node_id!r} != {node_id!r}"
        )
    if receipt.job_id != job_id:
        raise ReceiptAdmissionError(
            f"receipt job_id mismatch: {receipt.job_id!r} != {job_id!r}"
        )
    if receipt.execution_attempt_id != execution_attempt_id:
        raise ReceiptAdmissionError(
            f"receipt execution_attempt_id mismatch: {receipt.execution_attempt_id!r} != {execution_attempt_id!r}"
        )
    if receipt.merge_commit_sha != result_commit_sha:
        raise ReceiptAdmissionError(
            f"receipt merge_commit_sha mismatch: {receipt.merge_commit_sha!r} != {result_commit_sha!r}"
        )
    if receipt.evaluated_commit_sha != result_commit_sha:
        raise ReceiptAdmissionError(
            f"receipt evaluated_commit_sha mismatch: {receipt.evaluated_commit_sha!r} != {result_commit_sha!r}"
        )
    if expected_base_commit_sha is not None:
        if receipt.expected_base_commit_sha != expected_base_commit_sha:
            raise ReceiptAdmissionError(
                f"receipt expected_base_commit_sha mismatch: {receipt.expected_base_commit_sha!r} != {expected_base_commit_sha!r}"
            )

    return receipt
