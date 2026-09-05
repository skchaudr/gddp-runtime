"""
dispatcher.py — Routes a job to the correct adapter.

Dispatch stays executor-driven. Runtime routes packets; it does not infer graph
truth from executor choice.
"""

import json
import os
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Ensure adapters directory is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from adapters.executor_protocol import (
    AttemptContext,
    DispatchResult,
    EngagementDispatchResult,
    ExecutorCapabilities,
    NodePacket,
    SessionRef,
    adapter_capabilities,
)
from adapters.cursor_cli_adapter import CursorCliAdapter
from adapters.jules_action_adapter import JulesActionAdapter
from adapters.jules_api_adapter import JulesApiAdapter
from adapters.local_subprocess_adapter import (
    DroidSubprocessAdapter,
    LocalSubprocessAdapter,
)
from adapters.mission_adapter import MissionAdapter
from adapters.pi_rpc_adapter import PiRpcAdapter

from ..verification.semantic.context_builder import build_canonical_pointers
from .continuity_policy import choose_continuity, continuity_request_dir
from .graph_reader import GraphReader




ADAPTERS = {
    "jules_api": JulesApiAdapter,
    "local_subprocess": LocalSubprocessAdapter,
    "droid": DroidSubprocessAdapter,
    "factory_mission": MissionAdapter,
    "pi_rpc": PiRpcAdapter,
    "cursor_cli": CursorCliAdapter,
}

# Executors that run inside a local checkout and therefore receive repo_path
# as their cwd. Name-keyed (not class-keyed) so tests can substitute
# duck-typed adapter doubles into ADAPTERS.
_LOCAL_TRANSPORT_EXECUTORS = frozenset(
    {"local_subprocess", "droid", "factory_mission", "pi_rpc", "cursor_cli"}
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
    return executor_capabilities(executor, repo, repo_path).engagement


def executor_capabilities(
    executor: str, repo: str, repo_path: str | None = None
) -> ExecutorCapabilities:
    """Return the selected adapter's authoritative runtime declaration."""
    selected = os.environ.get("GDDP_EXECUTOR_OVERRIDE", "") or executor
    adapter_cls = ADAPTERS.get(selected) or MEDIATED_ADAPTERS.get(selected)
    if adapter_cls is None:
        return ExecutorCapabilities(executor=selected)
    try:
        adapter = _build_adapter(adapter_cls, selected, repo, repo_path)
        return adapter_capabilities(adapter, selected)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ExecutorCapabilities(executor=selected)


def dispatch(
    job: dict,
    repo: str,
    repo_path: str | None = None,
    *,
    role: str | None = None,
    execution_policy: Mapping[str, object] | None = None,
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
        packet = _build_node_packet(job, repo_path=repo_path)
        adapter = _build_adapter(
            adapter_cls,
            executor,
            repo,
            repo_path,
            role=role,
            execution_policy=execution_policy,
        )
        capabilities = adapter_capabilities(adapter, executor)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return DispatchResult(success=False, error=f"Invalid dispatch packet: {exc}")
    try:
        attempt = _reserve_attempt(adapter, packet, capabilities)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        return DispatchResult(success=False, error=f"Attempt reservation failed: {exc}")
    continuity = choose_continuity(
        request_dir=continuity_request_dir(
            attempt.attempt_dir.parent, packet.job_id
        ),
        capabilities=capabilities,
        cwd=repo_path,
    )
    return adapter.dispatch(packet, attempt=attempt, continuity=continuity)


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
        capabilities = adapter_capabilities(adapter, executor)
        if not capabilities.engagement:
            return EngagementDispatchResult(
                success=False,
                error=f"executor {executor} does not support engagements",
            )
        _validate_engagement_order(jobs)
        packets = [_build_node_packet(job, repo_path=repo_path) for job in jobs]
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


def _build_adapter(
    adapter_cls,
    executor: str,
    repo: str,
    repo_path: str | None,
    *,
    role: str | None = None,
    execution_policy: Mapping[str, object] | None = None,
):
    """Give only local transports the checkout they execute inside."""
    kwargs: dict[str, object] = {"repo": repo}
    if executor in _LOCAL_TRANSPORT_EXECUTORS and repo_path:
        kwargs["cwd"] = repo_path
    if executor == "pi_rpc":
        # Named here so the orchestrator model is visible at the call site
        # rather than resolved by a default inside the adapter. Unset env
        # means the adapter raises, which surfaces as a configuration error.
        kwargs["model"] = os.environ.get("GDDP_PI_RPC_MODEL")
    if executor == "cursor_cli":
        # Role-scoped model resolution (GDDP_CURSOR_CLI_MODEL_<ROLE>, then
        # execution_policy "models") happens inside the adapter. Passed only
        # when set, so a None role reproduces the old constructor call
        # exactly — test doubles and reconstructors keep working unchanged.
        if role is not None:
            kwargs["role"] = role
        if execution_policy is not None:
            kwargs["execution_policy"] = execution_policy
    return adapter_cls(**kwargs)


def _reserve_attempt(
    adapter: object,
    packet: NodePacket,
    capabilities: ExecutorCapabilities,
) -> AttemptContext:
    """Mint and persist attempt identity before transport dispatch."""
    attempt_root = Path(adapter.attempt_root())
    attempt_id = (
        f"{_safe_component(packet.execution_attempt_id)}-"
        f"{uuid.uuid4().hex}"
    )
    attempt_dir = attempt_root / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=False)
    (attempt_dir / "packet.json").write_text(packet.to_json())
    (attempt_dir / "capabilities.json").write_text(
        json.dumps(asdict(capabilities), sort_keys=True, separators=(",", ":"))
    )
    return AttemptContext(attempt_id=attempt_id, attempt_dir=attempt_dir)


def _safe_component(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in value
    )
    return safe.strip("._-") or "attempt"


def queue_operator_steer(attempt_dir: Path, message: str) -> tuple[bool, str]:
    """Queue a steer only when the reserved attempt declares delivery support."""
    capabilities_path = Path(attempt_dir) / "capabilities.json"
    try:
        payload = json.loads(capabilities_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False, "steer refused: executor capabilities are unavailable"
    executor = str(payload.get("executor") or "executor")
    if payload.get("midturn_steering") is not True:
        return (
            False,
            f"steer refused: executor {executor} does not support mid-turn steering",
        )
    text = message.strip()
    if not text:
        return False, "steer refused: message is empty"
    line = json.dumps(
        {"ts": datetime.now(timezone.utc).isoformat(), "message": text}
    )
    try:
        with (Path(attempt_dir) / "steer.jsonl").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write(line + "\n")
    except OSError as exc:
        return False, f"steer refused: {exc}"
    return True, f"steer queued for {executor}"


def cancel_remote_session(session_ref: SessionRef, repo: str) -> tuple[bool, str]:
    """Best-effort cancel a known remote session with truthful outcome text."""
    adapter_cls = ADAPTERS.get(session_ref.executor)
    if adapter_cls is None:
        return False, f"unknown executor {session_ref.executor!r}; remote may continue"
    capabilities: ExecutorCapabilities | None = None
    try:
        adapter = _build_adapter(adapter_cls, session_ref.executor, repo, None)
        capabilities = adapter_capabilities(adapter, session_ref.executor)
        accepted = adapter.cancel(session_ref)
    except Exception as exc:
        if capabilities is not None and capabilities.cancellation == "preemptive":
            return False, f"preemptive session cancellation failed: {exc}"
        return False, f"late session cancellation failed: {exc}; remote may continue"
    assert capabilities is not None
    if capabilities.cancellation == "preemptive":
        if accepted:
            return True, "late session termination accepted"
        return False, "late session termination was not accepted; session may be terminal"
    if capabilities.cancellation == "cooperative":
        if accepted:
            return True, "cancellation queued; in-flight turn continues to its boundary"
        return False, "cooperative cancellation was not accepted"
    if accepted:
        return True, "late session cancellation accepted"
    return (
        False,
        "late session cancellation was not accepted; "
        "executor declares no cancellation support; remote may continue",
    )


def _config_root() -> Path | None:
    """Resolve the gddp-config checkout, or None when it is not on disk."""
    runtime_root = Path(__file__).resolve().parents[3]
    root = Path(
        os.environ.get("GDDP_CONFIG_PATH", str(runtime_root.parent / "gddp-config"))
    ).expanduser()
    return root if root.is_dir() else None


def _node_edges_and_pointers(
    job: Mapping[str, object],
    repo_path: str | None,
    depends_on: tuple[str, ...],
) -> tuple[tuple[str, ...], dict[str, str] | None]:
    """Return (unlocks, context_pointers) for one job.

    Pointers are built exactly once here, at dispatch, so every retry of the
    resulting packet renders a byte-identical project prompt zone. Both graph
    reads are best-effort: without a reachable gddp-config checkout or a local
    checkout there is nothing to point at, and dispatch must still proceed
    with an empty project zone rather than fail the job.
    """
    project_id = str(job.get("project_id") or "")
    node_id = str(job.get("node_id") or "")
    if not repo_path or not project_id or not node_id:
        return (), None

    config_root = _config_root()
    graph: dict[str, object] = {"project_id": project_id}
    unlocks: tuple[str, ...] = ()
    reader: GraphReader | None = None
    if config_root is not None:
        try:
            reader = GraphReader(str(config_root))
        except Exception:
            reader = None
    if reader is not None:
        try:
            project = reader.load_project(project_id)
            graph = {"project_id": project.project_id, "nodes": list(project.nodes)}
        except Exception:
            graph = {"project_id": project_id}
        try:
            unlocks = tuple(
                str(item) for item in reader.load_node(project_id, node_id).unlocks
            )
        except Exception:
            unlocks = ()

    pointers = build_canonical_pointers(
        node={"depends_on": list(depends_on), "unlocks": list(unlocks)},
        graph=graph,
        repo=Path(repo_path),
        config_root=config_root,
    )
    return unlocks, pointers


def _build_node_packet(
    job: Mapping[str, object], *, repo_path: str | None = None
) -> NodePacket:
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

    depends_on = tuple(
        str(item)
        for item in _decode_sequence(job.get("dependencies"), "dependencies")
    )
    unlocks, context_pointers = _node_edges_and_pointers(job, repo_path, depends_on)

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
        project_id=str(job.get("project_id") or ""),
        depends_on=depends_on,
        unlocks=unlocks,
        context_pointers=context_pointers,
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
