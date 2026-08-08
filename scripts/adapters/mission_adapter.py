"""Factory mission adapter registration surface.

The lifecycle implementation lands with the mission-adapter-protocol feature.
This module establishes the constructible adapter identity used by config and
heartbeat registration.
"""

from __future__ import annotations

from pathlib import Path

from .executor_protocol import (
    DispatchResult,
    NodePacket,
    PatchResult,
    SessionRef,
    SessionStatus,
)


class MissionAdapter:
    """Factory ``droid exec --mission`` adapter."""

    executor_name = "factory_mission"

    def __init__(self, repo: str, *, cwd: str | Path | None = None) -> None:
        self.repo = repo
        self.cwd = Path(cwd).resolve() if cwd else None

    def dispatch(self, packet: NodePacket) -> DispatchResult:
        raise NotImplementedError("factory mission dispatch is not implemented")

    def status(self, session_ref: SessionRef) -> SessionStatus:
        raise NotImplementedError("factory mission status is not implemented")

    def collect(self, session_ref: SessionRef, dest_path: Path) -> PatchResult:
        raise NotImplementedError("factory mission collection is not implemented")

    def cancel(self, session_ref: SessionRef) -> bool:
        raise NotImplementedError("factory mission cancellation is not implemented")
