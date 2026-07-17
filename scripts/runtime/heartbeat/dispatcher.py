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
from adapters.jules_cli_adapter import JulesCliAdapter
from adapters.executor_protocol import SessionRef


class DispatchResult:
    def __init__(
        self,
        success: bool,
        issue_url: str = "",
        error: str = "",
        session_ref: SessionRef | None = None,
    ):
        self.success = success
        self.issue_url = issue_url
        self.error = error
        self.session_ref = session_ref


ADAPTERS = {
    "jules": JulesActionAdapter,
    "jules_cli": JulesCliAdapter,
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
    # Adapters return their own result types:
    #   - JulesActionAdapter returns its own DispatchResult (issue_url-based)
    #   - JulesCliAdapter returns executor_protocol.DispatchResult (session_ref-based)
    # Normalize into this module's DispatchResult, passing session_ref through
    # when the adapter produced one.
    session_ref = getattr(result, "session_ref", None)
    return DispatchResult(
        success=result.success,
        issue_url=getattr(result, "issue_url", "") or "",
        error=getattr(result, "error", "") or "",
        session_ref=session_ref,
    )


def _build_adapter_payload(job: dict) -> dict:
    """Build the executor packet from the persisted job payload."""
    payload = {
        "node_id":             job["node_id"],
        "title":               job["title"],
        "goal":                job["goal"],
        "why":                 job["why"],
        "job_id":              job["job_id"],
        "constraints":         job["constraints"],          # already JSON string
        "acceptance_criteria": job["acceptance_criteria"],  # already JSON string
        "required_artifacts":  job.get("_required_artifacts", []),
    }
    # Pass through retry-loop fields so the adapter can inject findings into
    # the issue body on re-dispatch. Absent on first dispatch.
    if "_previous_findings" in job:
        payload["_previous_findings"] = job["_previous_findings"]
    if "attempt" in job:
        payload["attempt"] = job["attempt"]
    return payload
