"""
dispatch_next.py — Select the next eligible node and create a GitHub issue for Jules.

Eligible = status pending + all depends_on complete + no active job for this project.
"""

import json
import subprocess
from typing import Optional

from ..context_reader import DecisionContext
from ..schema import DispatchResult, EscalateResult


def _find_eligible_node(ctx: DecisionContext) -> Optional[str]:
    """Find the highest-priority pending node whose dependencies are all complete."""
    complete_ids = {n.node_id for n in ctx.project.complete_nodes}

    eligible = []
    for node in ctx.project.pending_nodes:
        if all(dep in complete_ids for dep in node.depends_on):
            eligible.append(node)

    if not eligible:
        return None

    # Sort by priority: high > normal > low
    priority_order = {"high": 0, "normal": 1, "low": 2}
    eligible.sort(key=lambda n: priority_order.get(n.priority, 1))
    return eligible[0].node_id


def _has_active_job(ctx: DecisionContext) -> bool:
    """Check if there's already a dispatched/running job for this project."""
    return len(ctx.activity.active_jobs) > 0


def _build_issue_body(node, job_id: str) -> str:
    """Format the node spec as a GitHub issue body for Jules."""
    constraints_text = "\n".join(f"- {c}" for c in node.constraints)
    criteria_text = "\n".join(f"- [ ] {c}" for c in node.acceptance_criteria)

    return f"""## Goal
{node.title}

## Why
{node.why}

## Constraints
{constraints_text}

## Acceptance Criteria
{criteria_text}

## Output Requirements
- Implement the change
- Add or update tests
- Open a PR with a clear summary of the implementation choice
- Note any ambiguity or remaining risks
- **Required: include the following metadata block verbatim at the end of the PR description:**

```
node: {node.node_id}
job: {job_id}
```

This block is parsed by the GDDP return router to create a review receipt when the PR merges. If it is missing or malformed, the merge will not be recorded for review.

---
*Dispatched by the GDDP decision loop - job_id: {job_id} - node: {node.node_id}*
"""


def run(ctx: DecisionContext) -> DispatchResult | EscalateResult:
    """
    Decide whether to dispatch and do it.

    Returns DispatchResult on success, EscalateResult if blocked or failed.
    """
    # Guard: no dispatch if a job is already active
    if _has_active_job(ctx):
        return EscalateResult(
            action="escalate",
            reason="dispatch_blocked: active job already exists for this project",
            project_id=ctx.project.project_id,
            ok=True,
        )

    node_id = _find_eligible_node(ctx)
    if not node_id:
        return EscalateResult(
            action="escalate",
            reason="no_eligible_nodes: all pending nodes have unmet dependencies",
            project_id=ctx.project.project_id,
            ok=True,
        )

    # Load the full node data
    node = next(n for n in ctx.project.nodes if n.node_id == node_id)

    # Generate job_id
    import uuid
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    # Build issue body
    body = _build_issue_body(node, job_id)
    title = f"[GDDP] {node.title}"

    # Create GitHub issue via gh CLI
    cmd = [
        "gh", "issue", "create",
        "--repo", ctx.project.repo,
        "--title", title,
        "--body", body,
        "--label", "jules",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return EscalateResult(
                action="escalate",
                node_id=node_id,
                project_id=ctx.project.project_id,
                reason=f"gh_issue_create_failed: {result.stderr.strip()}",
                ok=True,
            )

        issue_url = result.stdout.strip()
        issue_number = int(issue_url.rstrip("/").split("/")[-1])

        return DispatchResult(
            action="dispatch_next",
            node_id=node_id,
            project_id=ctx.project.project_id,
            issue_number=issue_number,
            issue_url=issue_url,
            ok=True,
        )

    except subprocess.TimeoutExpired:
        return EscalateResult(
            action="escalate",
            node_id=node_id,
            project_id=ctx.project.project_id,
            reason="gh_cli_timeout",
            ok=True,
        )
    except Exception as e:
        return EscalateResult(
            action="escalate",
            node_id=node_id,
            project_id=ctx.project.project_id,
            reason=f"dispatch_exception: {e}",
            ok=True,
        )
