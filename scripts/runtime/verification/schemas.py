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


class VerdictReceipt(BaseModel):
    project_id: str
    node_id: str
    verdict: Verdict
    # Compatibility alias for criteria_confidence. New readers should prefer
    # criteria_confidence; both fields are emitted so old receipt consumers keep
    # working while completeness is tracked separately.
    confidence: float = Field(ge=0.0, le=1.0)
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
        if "criteria_confidence" not in values and "confidence" in values:
            values["criteria_confidence"] = values["confidence"]
        if "confidence" not in values and "criteria_confidence" in values:
            values["confidence"] = values["criteria_confidence"]
        if "completeness_status" not in values:
            values["completeness_status"] = cls._infer_completeness_status(values.get("semantic"))
        return values

    @model_validator(mode="after")
    def _confidence_alias_must_match(self):
        if self.confidence != self.criteria_confidence:
            raise ValueError("confidence is a compatibility alias for criteria_confidence and must match")
        return self

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
