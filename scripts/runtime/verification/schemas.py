from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel


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
    confidence: float
    evidence: list[str]
    reasoning: str


class SemanticOutput(BaseModel):
    judgments: list[CriterionJudgment]
    overall_reasoning: str
    risks: str | None
    followup_candidates: str | None
    budget_exhausted: bool


class VerdictReceipt(BaseModel):
    project_id: str
    node_id: str
    verdict: Verdict
    confidence: float
    deterministic: DeterministicResult
    semantic: SemanticOutput | None
    decision_reasoning: str
    required_next_action: str
    generated_at: str