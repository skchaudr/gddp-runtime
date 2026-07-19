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
    node_id: str
    title: str
    goal: str
    why: str
    constraints: tuple[FrozenJSON, ...]
    acceptance_criteria: tuple[FrozenJSON, ...]
    required_artifacts: tuple[str, ...]
    attempt_index: int
    previous_findings: Mapping[str, FrozenJSON] | None = None

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
        if self.previous_findings is not None:
            frozen = _freeze_json(self.previous_findings)
            if not isinstance(frozen, Mapping):
                raise TypeError("previous_findings must be a mapping")
            object.__setattr__(self, "previous_findings", frozen)

    def to_json_value(self) -> dict[str, object]:
        """Return the exact transport shape for this packet."""
        return {
            "job_id": self.job_id,
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
    state: Literal["dispatched", "running", "needs_operator", "completed", "failed"]
    error: str | None = None


@dataclass
class PatchResult:
    """Result of collecting a completed session's work."""
    success: bool
    patch_text: str | None = None       # unified diff text
    patch_path: str | None = None       # path to saved patch file
    error: str | None = None


@dataclass(frozen=True)
class DispatchResult:
    """Common receipt for direct and mediated dispatch."""

    success: bool
    session_ref: SessionRef | None = None
    issue_url: str | None = None
    error: str | None = None

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
        """Retrieve patch from completed session. Does NOT apply or commit.
        Saves patch to dest_path."""
        ...

    def cancel(self, session_ref: SessionRef) -> bool:
        """Best-effort cancellation. Not all executors support this."""
        ...
