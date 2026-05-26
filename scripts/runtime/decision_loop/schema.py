"""
schema.py - Pydantic models enforcing the decision loop output contract.

Every decision loop result passes through one of these models.
If the shape is wrong, Pydantic raises immediately — no bad data reaches
SQLite or the graph.
"""

from typing import Literal, Optional
from pydantic import BaseModel


class DispatchResult(BaseModel):
    action: Literal["dispatch_next"]
    node_id: str
    project_id: str
    issue_number: int
    issue_url: str
    ok: Literal[True]


class EscalateResult(BaseModel):
    action: Literal["escalate"]
    node_id: Optional[str] = None
    project_id: Optional[str] = None
    reason: str
    ok: Literal[True]


class ReviewResult(BaseModel):
    """v0 placeholder - review_pr ships in the review-gate node."""
    action: Literal["review_pr"]
    node_id: str
    pr_number: int
    verdict: Literal["pass", "fail"]
    reason: Optional[str] = None
    ok: Literal[True]


class AcceptResult(BaseModel):
    """v0 placeholder - accept_node ships in the review-gate node."""
    action: Literal["accept_node"]
    node_id: str
    commit_sha: str
    ok: Literal[True]


class NoOpResult(BaseModel):
    """Nothing to do — all nodes complete or blocked, no stale state."""
    action: Literal["no_op"]
    reason: str
    ok: Literal[True]


# Union of all valid decision loop outputs
DecisionResult = DispatchResult | EscalateResult | ReviewResult | AcceptResult | NoOpResult
