"""Executor-neutral adapter protocol.

Every executor adapter (Jules CLI, Jules API, Droid, etc.) implements this
interface. The runtime calls dispatch/status/collect/cancel without knowing
which executor is behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


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


@dataclass
class DispatchResult:
    """Result of dispatching a job to an executor."""
    success: bool
    session_ref: SessionRef | None = None
    error: str | None = None


class ExecutorAdapter(Protocol):
    """Protocol every executor adapter implements."""

    def dispatch(self, job: dict) -> DispatchResult:
        """Send job to executor. Returns durable session reference."""
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
