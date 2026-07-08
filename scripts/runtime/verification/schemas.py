from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    NEEDS_HUMAN_REVIEW = "needs-human-review"
    NEEDS_MORE_EVIDENCE = "needs-more-evidence"
    OUT_OF_SCOPE_CHANGE_DETECTED = "out-of-scope-change-detected"


@dataclass
class CriterionCheck:
    id: str
    criterion: str
    status: str
    confidence: float
    method: str
    evidence: list[str]
    reasoning: str
    mismatch_kind: str
    mismatch_detail: str
    needs_evidence: bool
    human_question: str


@dataclass
class ConstraintCheck:
    constraint: str
    status: str
    confidence: float
    method: str
    evidence: list[str]
    reasoning: str


@dataclass
class CriterionMismatch:
    criterion_id: str
    kind: str
    detail: str


@dataclass
class MissingEvidence:
    criterion_id: str
    what_is_missing: str
    what_exists: str


@dataclass
class HumanReviewQuestion:
    criterion_id: str
    question: str


@dataclass
class DeterministicResult:
    criteria: list[CriterionCheck]
    constraints: list[ConstraintCheck]
    artifacts_present: dict[str, bool]
    deps_status: dict[str, str]
    criteria_mismatches: list[CriterionMismatch]
    missing_evidence: list[MissingEvidence]
    human_review_questions: list[HumanReviewQuestion]


class CriterionJudgment(BaseModel):
    criterion_id: str
    judgment: Literal["judged_pass", "judged_fail", "indeterminate"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]
    reasoning: str


class SemanticOutput(BaseModel):
    judgments: list[CriterionJudgment]
    overall_reasoning: str
    risks: str | None
    followup_candidates: str | None
    budget_exhausted: bool
    budget_trace: dict[str, Any] | None = None


class IntegrityFinding(BaseModel):
    severity: Literal["low", "medium", "high"]
    summary: str
    affected_node_ids: list[str]


class IntegrityOutput(BaseModel):
    # Vocabulary comes from the evaluator-intent-integrity-verdict node YAML in
    # gddp-config, not from this repo — the graph is the source of the language.
    verdict: Literal["pass", "block", "drift", "insufficient", "contradicted", "unknown"]
    intent_preserved: bool
    graph_integrity_preserved: bool
    required_human_review: bool
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[IntegrityFinding]
    reasoning: str


class VerdictReceipt(BaseModel):
    project_id: str
    node_id: str
    verdict: Verdict
    # Two-lane evaluation (evaluator-intent-integrity-verdict node): verdict above
    # is the combined value; criteria_verdict preserves the matrix's own answer.
    # Both optional so every existing receipt stays valid.
    criteria_verdict: Verdict | None = None
    integrity: IntegrityOutput | None = None
    criteria_confidence: float = Field(ge=0.0, le=1.0)
    completeness_status: Literal["complete", "partial", "not-run"]
    deterministic: DeterministicResult
    semantic: SemanticOutput | None
    decision_reasoning: str
    required_next_action: str
    generated_at: str

    @model_validator(mode="before")
    @classmethod
    def _fill_compatibility_fields(cls, data):
        if not isinstance(data, dict):
            return data
        values = dict(data)
        # Legacy receipts (pre criteria_confidence) carried the value under
        # "confidence"; map it forward so old receipt JSON still loads.
        if "criteria_confidence" not in values and "confidence" in values:
            values["criteria_confidence"] = values["confidence"]
        if "completeness_status" not in values:
            values["completeness_status"] = cls._infer_completeness_status(values.get("semantic"))
        return values

    @staticmethod
    def _infer_completeness_status(semantic) -> Literal["complete", "partial", "not-run"]:
        if semantic is None:
            return "not-run"
        if isinstance(semantic, dict):
            if semantic.get("budget_exhausted") or not semantic.get("judgments"):
                return "partial"
            return "complete"
        if getattr(semantic, "budget_exhausted", False) or not getattr(semantic, "judgments", []):
            return "partial"
        return "complete"
