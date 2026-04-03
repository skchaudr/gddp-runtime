"""
dispatcher.py — Routes a job to the correct adapter.

Dispatch stays executor-driven. Runtime routes packets; it does not infer graph
truth from executor choice.
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


ADAPTERS = {
    "jules": JulesActionAdapter,
}


def dispatch(job: dict, repo: str) -> DispatchResult:
    executor = job.get("executor")
    if not executor:
        return DispatchResult(success=False, error="Job is missing executor")

    adapter_cls = ADAPTERS.get(executor)
    if adapter_cls is None:
        return DispatchResult(success=False, error=f"Unknown executor: {executor}")

    adapter = adapter_cls(repo=repo)
    result = adapter.dispatch(_build_adapter_payload(job))
    return DispatchResult(
        success=result.success,
        issue_url=result.issue_url or "",
        error=result.error or "",
    )


def _build_adapter_payload(job: dict) -> dict:
    """Build the executor packet from the persisted job payload."""
    return {
        "node_id":             job["node_id"],
        "title":               job["title"],
        "goal":                job["goal"],
        "why":                 job["why"],
        "job_id":              job["job_id"],
        "constraints":         job["constraints"],          # already JSON string
        "acceptance_criteria": job["acceptance_criteria"],  # already JSON string
        "required_artifacts":  job.get("_required_artifacts", []),
    }
