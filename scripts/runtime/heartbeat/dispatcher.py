"""
dispatcher.py — Routes a job to the correct adapter.

Dispatch stays executor-driven. Runtime routes packets; it does not infer graph
truth from executor choice.
"""

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

# Ensure adapters directory is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from adapters.executor_protocol import DispatchResult, NodePacket, SessionRef
from adapters.jules_action_adapter import JulesActionAdapter
from adapters.jules_api_adapter import JulesApiAdapter
from adapters.jules_cli_adapter import JulesCliAdapter
from adapters.local_subprocess_adapter import LocalSubprocessAdapter




ADAPTERS = {
    "jules_api": JulesApiAdapter,
    "jules_cli": JulesCliAdapter,
    "local_subprocess": LocalSubprocessAdapter,
}

MEDIATED_ADAPTERS = {
    "jules": JulesActionAdapter,
}


# Executors that clone the repo themselves and branch from a fixed remote
# branch. Work returns based on that branch's tip, while the runner binds each
# job to local HEAD — so a checkout sitting on any other branch produces
# patches that fail base-SHA integrity at reconcile, hours after dispatch.
_REMOTE_BRANCHING_EXECUTORS = ("jules_api", "jules_cli", "jules")


def _head_branch(repo_path: str | None) -> str | None:
    """Current branch of the local checkout, or None if it cannot be read."""
    if not repo_path:
        return None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def executor_preflight_error(
    executor: str, repo: str, repo_path: str | None = None
) -> str | None:
    """Return a configuration error before the runner reserves a job."""
    override = os.environ.get("GDDP_EXECUTOR_OVERRIDE", "")
    selected = override or executor
    adapter_cls = ADAPTERS.get(selected) or MEDIATED_ADAPTERS.get(selected)
    if adapter_cls is None:
        return f"Unknown executor: {selected}"
    try:
        adapter_cls(repo=repo)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return f"Invalid executor configuration: {exc}"

    if selected in _REMOTE_BRANCHING_EXECUTORS:
        starting = os.environ.get("GDDP_JULES_STARTING_BRANCH") or "main"
        head = _head_branch(repo_path)
        if head is not None and head != starting:
            return (
                f"local checkout is on '{head}' but {selected} branches from "
                f"'{starting}'; returned patches would fail base-SHA integrity"
            )
    return None


def dispatch(job: dict, repo: str) -> DispatchResult:
    executor = job.get("executor")
    if not executor:
        return DispatchResult(success=False, error="Job is missing executor")

    # Allow operator override for canary testing without changing graph truth.
    # Existing graph nodes carry executor: jules; setting
    # GDDP_EXECUTOR_OVERRIDE=jules_cli reroutes dispatch through the CLI
    # adapter without mutating the human-owned graph.
    override = os.environ.get("GDDP_EXECUTOR_OVERRIDE", "")
    if override:
        executor = override

    adapter_cls = ADAPTERS.get(executor) or MEDIATED_ADAPTERS.get(executor)
    if adapter_cls is None:
        return DispatchResult(success=False, error=f"Unknown executor: {executor}")

    try:
        packet = _build_node_packet(job)
        adapter = adapter_cls(repo=repo)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return DispatchResult(success=False, error=f"Invalid dispatch packet: {exc}")
    return adapter.dispatch(packet)


def cancel_remote_session(session_ref: SessionRef, repo: str) -> tuple[bool, str]:
    """Best-effort cancel a known remote session with truthful outcome text."""
    adapter_cls = ADAPTERS.get(session_ref.executor)
    if adapter_cls is None:
        return False, f"unknown executor {session_ref.executor!r}; remote may continue"
    try:
        accepted = adapter_cls(repo=repo).cancel(session_ref)
    except Exception as exc:
        return False, f"late session cancellation failed: {exc}; remote may continue"
    if accepted:
        return True, "late session cancellation accepted"
    if session_ref.executor == "jules_cli":
        return False, "Jules CLI cancellation is unsupported; remote may continue"
    return False, "late session cancellation was not accepted; remote may continue"


def _build_node_packet(job: Mapping[str, object]) -> NodePacket:
    """Decode persisted fields once into an immutable executor packet."""
    constraints = _decode_sequence(job.get("constraints"), "constraints")
    acceptance_criteria = _decode_sequence(
        job.get("acceptance_criteria"), "acceptance_criteria"
    )
    artifacts_value = job.get(
        "_required_artifacts", job.get("required_artifacts", ())
    )
    required_artifacts = _decode_sequence(
        artifacts_value, "required_artifacts"
    )
    previous_value = job.get(
        "_previous_findings", job.get("previous_findings")
    )
    previous_findings = _decode_optional_mapping(
        previous_value, "previous_findings"
    )
    attempt_index = int(job.get("attempt", 0))
    if attempt_index < 0:
        raise ValueError("attempt must be zero or greater")

    return NodePacket(
        job_id=str(job["job_id"]),
        node_id=str(job["node_id"]),
        execution_attempt_id=f"{job['job_id']}:attempt:{attempt_index}",
        title=str(job["title"]),
        goal=str(job["goal"]),
        why=str(job.get("why") or ""),
        constraints=tuple(constraints),
        acceptance_criteria=tuple(acceptance_criteria),
        required_artifacts=tuple(str(item) for item in required_artifacts),
        attempt_index=attempt_index,
        previous_findings=previous_findings,
        expected_base_commit_sha=(
            str(job["expected_base_commit_sha"])
            if job.get("expected_base_commit_sha")
            else None
        ),
    )


def _decode_sequence(value: object, field_name: str) -> Sequence[object]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if decoded is None:
        return ()
    if not isinstance(decoded, Sequence) or isinstance(
        decoded, str | bytes | bytearray
    ):
        raise TypeError(f"{field_name} must be a JSON array")
    return decoded


def _decode_optional_mapping(
    value: object, field_name: str
) -> Mapping[str, object] | None:
    decoded = json.loads(value) if isinstance(value, str) else value
    if decoded is None:
        return None
    if not isinstance(decoded, Mapping):
        raise TypeError(f"{field_name} must be a JSON object")
    return decoded
