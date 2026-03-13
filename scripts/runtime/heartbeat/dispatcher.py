"""
dispatcher.py — Routes a job to the correct adapter.

v1 supports jules only. Adding codex or vertex later means adding
an elif branch and a new adapter file — nothing else changes.
"""

import sys
from pathlib import Path

# Ensure adapters directory is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from adapters.jules_action_adapter import JulesActionAdapter


class DispatchResult:
    def __init__(self, success: bool, issue_url: str = "", error: str = ""):
        self.success = success
        self.issue_url = issue_url
        self.error = error


def dispatch(job: dict, repo: str) -> DispatchResult:
    executor = job.get("executor", "jules")

    if executor == "jules":
        return _dispatch_jules(job, repo)

    return DispatchResult(success=False, error=f"Unknown executor: {executor}")


def _dispatch_jules(job: dict, repo: str) -> DispatchResult:
    # Build the node dict the adapter expects
    node_payload = {
        "node_id":             job["node_id"],
        "title":               job["title"],
        "goal":                job["goal"],
        "why":                 job["why"],
        "job_id":              job["job_id"],
        "constraints":         job["constraints"],          # already JSON string
        "acceptance_criteria": job["acceptance_criteria"],  # already JSON string
        "required_artifacts":  job.get("_required_artifacts", []),
    }

    adapter = JulesActionAdapter(repo=repo)
    result = adapter.dispatch(node_payload)

    return DispatchResult(
        success=result.success,
        issue_url=result.issue_url or "",
        error=result.error or "",
    )
