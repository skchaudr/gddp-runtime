"""
semantic_schema.py — Output contract for the semantic evaluator (Task 4).

This stub defines the class signatures that Task 2's decision engine imports.
Task 4 fills in the evaluator prompt, LLM runner, and JSON extraction logic.
The schema is final — Task 4 must not change these field names or literals.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel


class CriterionVerdict(BaseModel):
    criterion: str
    satisfied: bool
    confidence: float          # 0.0 – 1.0
    reasoning: str


class SemanticOutput(BaseModel):
    semantic_fidelity: Literal[
        "preserved",
        "weakened",
        "drifted",
        "contradicted",
        "insufficient",
    ]
    risk_level: Literal["low", "medium", "high"]
    drift_type: Literal[
        "none",
        "acceptance_weakening",
        "responsibility_loss",
        "shape_change",
    ]
    requires_operator_review: bool
    criteria_verdicts: List[CriterionVerdict] = []
    evidence: dict = {}
    reasoning_summary: str = ""
