from typing import Literal
from pydantic import BaseModel


class DecisionOutput(BaseModel):
    verdict: Literal["ACCEPT", "FAIL", "NEEDS_REVIEW", "INVALID", "INCOMPLETE"]
    reason: str               # diagnostic: "preserved", "weakened", "drifted", etc.
    severity: Literal["warning", "blocking"] | None   # None only for ACCEPT
    matrix_row: int           # which rule fired, for auditability
