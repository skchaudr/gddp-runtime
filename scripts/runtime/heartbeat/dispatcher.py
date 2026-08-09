"""
dispatcher.py — Routes a job to the correct adapter.

Dispatch stays executor-driven. Runtime routes packets; it does not infer graph
truth from executor choice.
"""

import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

# Ensure adapters directory is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from adapters.executor_protocol import (
    DispatchResult,
    EngagementDispatchResult,
    NodePacket,
    SessionRef,
)
from adapters.jules_action_adapter import JulesActionAdapter
from adapters.jules_api_adapter import JulesApiAdapter
from adapters.local_subprocess_adapter import (
    DroidSubprocessAdapter,
    LocalSubprocessAdapter,
)
from adapters.mission_adapter import MissionAdapter




ADAPTERS = {
    "jules_api": JulesApiAdapter,
    "local_subprocess": LocalSubprocessAdapter,
    "droid": DroidSubprocessAdapter,
    "factory_mission": MissionAdapter,
}

# Executors that run inside a local checkout and therefore receive repo_path
# as their cwd. Name-keyed (not class-keyed) so tests can substitute
# duck-typed adapter doubles into ADAPTERS.
_LOCAL_TRANSPORT_EXECUTORS = frozenset(
    {"local_subprocess", "droid", "factory_mission"}
)

MEDIATED_ADAPTERS = {
    "jules": JulesActionAdapter,
}


def executor_preflight_error(
    executor: str, repo: str, repo_path: str | None = None
) -> str | None:
    """Return a configuration error before the runner reserves a job.

    Configuration only. This must never refuse dispatch on the basis of what a
    result might later look like — the executor's output is judged by the
    evaluator, not gated here.
    """
    override = os.environ.get("GDDP_EXECUTOR_OVERRIDE", "")
    selected = override or executor
    adapter_cls = ADAPTERS.get(selected) or MEDIATED_ADAPTERS.get(selected)
    if adapter_cls is None:
        return f"Unknown executor: {selected}"
    try:
        _build_adapter(adapter_cls, selected, repo, repo_path)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return f"Invalid executor configuration: {exc}"
    return None


def executor_supports_engagement(
    executor: str, repo: str, repo_path: str | None = None
) -> bool:
    """Return the adapter's optional multi-node capability."""
    selected = os.environ.get("GDDP_EXECUTOR_OVERRIDE", "") or executor
    adapter_cls = ADAPTERS.get(selected)
    if adapter_cls is None:
        return False
    try:
        adapter = _build_adapter(adapter_cls, selected, repo, repo_path)
        supports_engagement = getattr(
            adapter, "supports_engagement", lambda: False
        )
        return bool(supports_engagement())
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def dispatch(
    job: dict, repo: str, repo_path: str | None = None
) -> DispatchResult:
    executor = job.get("executor")
    if not executor:
        return DispatchResult(success=False, error="Job is missing executor")

    # Allow operator override for canary testing without changing graph truth.
    # Existing graph nodes carry executor: jules; setting
    # GDDP_EXECUTOR_OVERRIDE=jules_api reroutes dispatch through the API
    # adapter without mutating the human-owned graph.
    override = os.environ.get("GDDP_EXECUTOR_OVERRIDE", "")
    if override:
        executor = override

    adapter_cls = ADAPTERS.get(executor) or MEDIATED_ADAPTERS.get(executor)
    if adapter_cls is None:
        return DispatchResult(success=False, error=f"Unknown executor: {executor}")

    try:
        packet = _build_node_packet(job)
        adapter = _build_adapter(adapter_cls, executor, repo, repo_path)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return DispatchResult(success=False, error=f"Invalid dispatch packet: {exc}")
    return adapter.dispatch(packet)


def dispatch_engagement(
    jobs: Sequence[Mapping[str, object]],
    repo: str,
    repo_path: str | None = None,
) -> EngagementDispatchResult:
    """Dispatch ordered jobs through one engagement-capable adapter."""
    if not jobs:
        return EngagementDispatchResult(
            success=False, error="engagement dispatch requires at least one job"
        )
    configured_executor = str(jobs[0].get("executor") or "")
    if not configured_executor:
        return EngagementDispatchResult(
            success=False, error="engagement job is missing executor"
        )
    if any(
        str(job.get("executor") or "") != configured_executor for job in jobs
    ):
        return EngagementDispatchResult(
            success=False, error="engagement jobs must use the same executor"
        )

    executor = os.environ.get("GDDP_EXECUTOR_OVERRIDE", "") or configured_executor
    adapter_cls = ADAPTERS.get(executor)
    if adapter_cls is None:
        return EngagementDispatchResult(
            success=False, error=f"Unknown executor: {executor}"
        )
    try:
        adapter = _build_adapter(adapter_cls, executor, repo, repo_path)
        if not adapter.supports_engagement():
            return EngagementDispatchResult(
                success=False,
                error=f"executor {executor} does not support engagements",
            )
        _validate_engagement_order(jobs)
        packets = [_build_node_packet(job) for job in jobs]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return EngagementDispatchResult(
            success=False, error=f"Invalid engagement dispatch packet: {exc}"
        )
    return adapter.dispatch_engagement(packets)


def _validate_engagement_order(
    jobs: Sequence[Mapping[str, object]],
) -> None:
    """Reject an engagement whose selected dependencies follow dependents."""
    node_ids = tuple(str(job.get("node_id") or "") for job in jobs)
    if any(not node_id for node_id in node_ids):
        raise ValueError("engagement jobs require node ids")
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("engagement jobs contain duplicate node ids")

    selected_ids = set(node_ids)
    preceding_node_ids: set[str] = set()
    for job, node_id in zip(jobs, node_ids, strict=True):
        dependencies = _decode_sequence(
            job.get("dependencies"), "dependencies"
        )
        late_dependencies = [
            str(dependency)
            for dependency in dependencies
            if str(dependency) in selected_ids
            and str(dependency) not in preceding_node_ids
        ]
        if late_dependencies:
            raise ValueError(
                "engagement jobs must be in topological order: "
                f"{node_id} precedes selected dependencies "
                f"{late_dependencies!r}"
            )
        preceding_node_ids.add(node_id)


def _build_adapter(adapter_cls, executor: str, repo: str, repo_path: str | None):
    """Give only local transports the checkout they execute inside."""
    if executor in _LOCAL_TRANSPORT_EXECUTORS and repo_path:
        return adapter_cls(repo=repo, cwd=repo_path)
    return adapter_cls(repo=repo)


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
