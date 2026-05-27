from typing import List
from pydantic import BaseModel


class InvariantResult(BaseModel):
    check: str          # stable check name, e.g. "graph_acyclic"
    passed: bool
    evidence: str       # human-readable explanation of the pass/fail


class StructuralOutput(BaseModel):
    all_passed: bool            # True iff every result.passed is True
    results: List[InvariantResult]
