"""Executor-neutral adapter protocol.

Every executor adapter (Jules CLI, Jules API, Droid, etc.) implements this
interface. The runtime calls dispatch/status/collect/cancel without knowing
which executor is behind it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol, TypeAlias, runtime_checkable


FrozenJSON: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | tuple["FrozenJSON", ...]
    | Mapping[str, "FrozenJSON"]
)


def _freeze_json(value: object) -> FrozenJSON:
    """Deep-freeze a decoded JSON value."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError(f"unsupported packet value: {type(value).__name__}")


def _thaw_json(value: FrozenJSON) -> object:
    """Convert immutable packet values into JSON-serializable values."""
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class NodePacket:
    """Executor-neutral, immutable description of one node execution attempt."""

    job_id: str
    execution_attempt_id: str
    node_id: str
    title: str
    goal: str
    why: str
    constraints: tuple[FrozenJSON, ...]
    acceptance_criteria: tuple[FrozenJSON, ...]
    required_artifacts: tuple[str, ...]
    attempt_index: int
    previous_findings: Mapping[str, FrozenJSON] | None = None
    expected_base_commit_sha: str | None = None
    project_id: str = ""
    depends_on: tuple[str, ...] = ()
    unlocks: tuple[str, ...] = ()
    # Canonical context file POINTERS (paths, never contents) for this node,
    # built once at dispatch. Byte-stable per packet so every retry renders an
    # identical project prompt zone; None means "not resolvable" (old packet,
    # unreachable gddp-config), which callers must tolerate.
    context_pointers: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "constraints", tuple(_freeze_json(item) for item in self.constraints)
        )
        object.__setattr__(
            self,
            "acceptance_criteria",
            tuple(_freeze_json(item) for item in self.acceptance_criteria),
        )
        object.__setattr__(
            self, "required_artifacts", tuple(str(item) for item in self.required_artifacts)
        )
        object.__setattr__(
            self, "depends_on", tuple(str(item) for item in self.depends_on)
        )
        object.__setattr__(self, "unlocks", tuple(str(item) for item in self.unlocks))
        if self.context_pointers is not None:
            object.__setattr__(
                self,
                "context_pointers",
                MappingProxyType(
                    {
                        str(key): str(value)
                        for key, value in self.context_pointers.items()
                    }
                ),
            )
        if self.previous_findings is not None:
            frozen = _freeze_json(self.previous_findings)
            if not isinstance(frozen, Mapping):
                raise TypeError("previous_findings must be a mapping")
            object.__setattr__(self, "previous_findings", frozen)

    def to_json_value(self) -> dict[str, object]:
        """Return the exact transport shape for this packet."""
        return {
            "job_id": self.job_id,
            "execution_attempt_id": self.execution_attempt_id,
            "node_id": self.node_id,
            "title": self.title,
            "goal": self.goal,
            "why": self.why,
            "constraints": [_thaw_json(item) for item in self.constraints],
            "acceptance_criteria": [
                _thaw_json(item) for item in self.acceptance_criteria
            ],
            "required_artifacts": list(self.required_artifacts),
            "attempt_index": self.attempt_index,
            "previous_findings": (
                _thaw_json(self.previous_findings)
                if self.previous_findings is not None
                else None
            ),
            "expected_base_commit_sha": self.expected_base_commit_sha,
            "project_id": self.project_id,
            "depends_on": list(self.depends_on),
            "unlocks": list(self.unlocks),
            "context_pointers": (
                dict(self.context_pointers)
                if self.context_pointers is not None
                else None
            ),
        }

    def to_json(self) -> str:
        """Serialize the transport shape deterministically."""
        return json.dumps(
            self.to_json_value(),
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class SessionRef:
    """Durable reference to an executor session."""
    executor: str           # "jules_cli", "jules_api", "droid", etc.
    session_id: str         # executor-specific ID


@dataclass
class SessionStatus:
    """Result of polling a session."""
    state: Literal[
        "dispatched",
        "running",
        # Executor asked a question and is waiting on an answer. Distinct from
        # needs_operator: this one is answerable by machine via adapter.reply().
        "awaiting_reply",
        "needs_operator",
        "completed",
        "crashed",
        "failed",
        "missing",
        "poll_error",
    ]
    error: str | None = None


CancellationKind = Literal["none", "cooperative", "preemptive"]
ResumeKind = Literal["none", "token", "session_file"]


@dataclass(frozen=True)
class ExecutorCapabilities:
    """Declared executor capabilities. Pure, cheap, callable without a session.

    The runtime feature-detects through this declaration rather than
    provider-detecting by executor name. Every field defaults to the least
    capable value: an adapter that declares nothing gets a correct, degraded
    contract. Declaring a capability is a promise about the NORMALIZED surface
    (canonical ExecutorEvent/TurnUsage records), not about the provider's
    native shape.

    cold_turn is required of every adapter and is therefore not a field: an
    adapter that cannot run one turn from a NodePacket is not an adapter.

    Design doc: docs/proposals/executor-capability-contract.md.
    """

    executor: str

    streaming_events: bool = False
    # Writes canonical ExecutorEvent records (executor_events.py) while the
    # turn runs. False means observability is terminal-only.

    partial_text: bool = False
    # Assistant text observable before the turn boundary. Implies
    # streaming_events.

    cancellation: CancellationKind = "none"
    # "none"        — cancel() is a no-op returning False.
    # "cooperative" — honored at the next packet/turn boundary; in-flight work
    #                 continues (pi_rpc marker file).
    # "preemptive"  — stops the in-flight turn (signal to a subprocess).

    resume: ResumeKind = "none"
    # "token"        — opaque string resumes prior context (cursor --resume).
    # "session_file" — a path on the executor host resumes it (pi --session).
    # Declares only that resume is POSSIBLE. Whether to resume is runtime
    # policy (see Continuity), never the adapter's decision.

    midturn_steering: bool = False
    # Accepts operator messages while status() == "running", delivered into
    # the same turn.

    usage_reporting: bool = False
    # Emits normalized TurnUsage per turn regardless of provider field names.

    native_subagents: bool = False
    # Harness can fan work out to child agents it manages itself.

    structured_tool_calls: bool = False
    # Emits canonical tool_started/tool_completed with (tool, paths, ok) so
    # context coverage computes without provider event names.

    engagement: bool = False
    # Fold of supports_engagement(); that method stays as a shim.

    reply: bool = False
    # Declarative form of the hasattr(adapter, "reply") probe.

    def supports(self, name: str) -> bool:
        """Single predicate for policy call sites: True for bool fields,
        True for graded fields that are not the zero value ("none")."""
        value = getattr(self, name)
        if isinstance(value, bool):
            return value
        return value != "none"


class CapabilityUnsupported(RuntimeError):
    """A call required a capability the adapter did not declare.

    Bug-catcher, not control flow: the runtime's policy layer receives the
    declaration and must not ask. Lifecycle capabilities (resume, engagement)
    hard-error rather than silently degrade, because a quiet resume-to-fresh
    substitution produces a receipt claiming continuity the turn never had.
    """

    def __init__(self, capability: str, executor: str) -> None:
        self.capability = capability
        self.executor = executor
        super().__init__(f"executor {executor} does not support {capability}")


@dataclass(frozen=True)
class Continuity:
    """The runtime's continuity decision for ONE dispatch. Packet-scoped.

    fresh is the structural default: the packet owns continuity, not the chat
    id. resume is an explicit policy decision; the token is opaque to GDDP and
    interpreted by the adapter, with silent cold fallback when the token is
    missing or unusable — resume is a hint, never a requirement.
    """

    mode: Literal["fresh", "resume"]
    token: str | None = None
    reason: str = ""


FRESH = Continuity(mode="fresh")


def adapter_capabilities(adapter: object, executor: str) -> ExecutorCapabilities:
    """Probe an adapter's capability declaration, least-capable by default.

    capabilities() is a convention (like reply()), not a Protocol member:
    adding it to ExecutorAdapter would break runtime_checkable isinstance
    checks for adapters that predate the declaration.
    """
    probe = getattr(adapter, "capabilities", None)
    if callable(probe):
        declared = probe()
        if isinstance(declared, ExecutorCapabilities):
            return declared
    return ExecutorCapabilities(executor=executor)


@dataclass
class PatchResult:
    """Result of collecting a completed session's work.

    Two success shapes:
    - patch handoff (remote/patch-only): patch_text / patch_path set
    - commit-ref handoff (local_subprocess): result_commit_sha / result_ref set
    """
    success: bool
    patch_text: str | None = None       # unified diff text
    patch_path: str | None = None       # path to saved patch file
    base_commit_sha: str | None = None  # remote patch's declared base
    result_commit_sha: str | None = None  # commit-ref transport (local)
    result_ref: str | None = None         # durable per-attempt ref name
    worktree_path: str | None = None      # kept on persist failure
    feature_id: str | None = None         # engagement fan-out join key
    evidence_manifest_path: str | None = None
    completion_id: str | None = None
    completion_digest_sha256: str | None = None
    completion_quarantine_reason: str | None = None
    review_required: bool = False
    error: str | None = None


@dataclass(frozen=True)
class DispatchResult:
    """Common receipt for direct and mediated dispatch."""

    success: bool
    session_ref: SessionRef | None = None
    issue_url: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class EngagementDispatchResult:
    """Receipt for one executor session spanning multiple node attempts."""

    success: bool
    engagement_id: str | None = None
    session_ref: SessionRef | None = None
    mission_dir: str | None = None
    process_pid: int | None = None
    engagement_branch: str | None = None
    feature_ids: tuple[str, ...] = ()
    error: str | None = None


class EngagementAdapterDefaults:
    """Opt-in engagement extension shared by one-node adapters."""

    def supports_engagement(self) -> bool:
        return False

    def dispatch_engagement(
        self, packets: list[NodePacket]
    ) -> EngagementDispatchResult:
        raise NotImplementedError("adapter does not support engagement dispatch")

    def collect_engagement(self, session_ref: SessionRef) -> list[PatchResult]:
        raise NotImplementedError("adapter does not support engagement collection")

    def completed_feature_ids(self, session_ref: SessionRef) -> tuple[str, ...]:
        """Return feature ids reported successfully completed so far."""
        return ()

    def collect_completed_engagement(
        self,
        session_ref: SessionRef,
        feature_ids: Sequence[str],
    ) -> list[PatchResult]:
        """Collect a completed subset while the engagement remains active."""
        raise NotImplementedError(
            "adapter does not support incremental engagement collection"
        )

    def collect_engagement_features(
        self,
        session_ref: SessionRef,
        feature_ids: Sequence[str],
    ) -> list[PatchResult]:
        """Collect only the requested terminal engagement remainder."""
        raise NotImplementedError(
            "adapter does not support subset engagement collection"
        )


@runtime_checkable
class ExecutorAdapter(Protocol):
    """Direct executor lifecycle protocol."""

    def dispatch(self, packet: NodePacket) -> DispatchResult:
        """Send one node attempt to an executor."""
        ...

    def status(self, session_ref: SessionRef) -> SessionStatus:
        """Poll session state. Idempotent. Fail closed on unfamiliar output."""
        ...

    def collect(self, session_ref: SessionRef, dest_path: Path) -> PatchResult:
        """Retrieve result from a completed session. Does NOT apply or commit.

        Success is either a patch handoff (patch_text/path) or a commit-ref
        handoff (result_commit_sha/result_ref). Saves raw payload to dest_path
        when a file form is available.
        """
        ...

    def cancel(self, session_ref: SessionRef) -> bool:
        """Best-effort cancellation. Not all executors support this."""
        ...

    def supports_engagement(self) -> bool:
        """Whether this adapter can dispatch multiple node attempts together."""
        ...

    def dispatch_engagement(
        self, packets: list[NodePacket]
    ) -> EngagementDispatchResult:
        """Send ordered node attempts through one executor engagement."""
        ...

    def collect_engagement(self, session_ref: SessionRef) -> list[PatchResult]:
        """Collect one node-scoped result per feature in the engagement."""
        ...

    def completed_feature_ids(self, session_ref: SessionRef) -> tuple[str, ...]:
        """Return feature ids reported successfully completed so far."""
        ...

    def collect_completed_engagement(
        self,
        session_ref: SessionRef,
        feature_ids: Sequence[str],
    ) -> list[PatchResult]:
        """Collect a completed subset while the engagement remains active."""
        ...

    def collect_engagement_features(
        self,
        session_ref: SessionRef,
        feature_ids: Sequence[str],
    ) -> list[PatchResult]:
        """Collect only the requested terminal engagement remainder."""
        ...

    # Optional capability, probed with hasattr rather than declared above:
    # adding it to this Protocol would break runtime_checkable isinstance
    # checks for adapters that cannot hold a conversation at all.
    #
    #   def reply(self, session_ref: SessionRef, message: str) -> bool:
    #       """Answer a session parked in awaiting_reply."""
