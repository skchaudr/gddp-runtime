"""When-to-resume policy. Separate from can-resume capability, by design.

`Continuity` (adapters/executor_protocol.py) is the runtime's decision for
ONE dispatch and defaults to FRESH at the adapter signature, so "the packet
owns continuity, not the chat id" is structural rather than a convention an
adapter could forget. This module is the only place that decision is made.

Doctrine and evidence: docs/proposals/continuity-boundary.md. The short
version of why the default is cold: the only executor state GDDP cannot
rebuild is the git object store and its per-attempt refs; chat history is the
one surviving item nothing reads. pi has had `--session` wired end to end
since it was written and the runtime has never set it, while the armed
heartbeat runs `pi --print --no-session`. Resume earns exactly one trigger —
a human explicitly asking for it.

The operator's request is keyed by the durable job id at
`<attempt-root>/_continuity/<job-id>/resume.requested`. That path exists before
the runtime reserves a transport attempt, so the dispatcher can consume the
request before calling the adapter. There is deliberately NO policy env var:
resume changes what the model is told and what it remembers, which sits next
to node intent.

Resume is a HINT. A missing, malformed, or guard-failing token falls back to
a cold turn silently; it never fails the attempt. The cursor chat store is
host-local and cwd-namespaced (`~/.cursor/chats/<cwd-hash>/<session_id>/`),
GDDP executes in a fresh `tempfile.mkdtemp` worktree every attempt, and
cross-cwd resume was never proven by the spike — so the guards below are the
difference between a hint and a lie.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from adapters.executor_protocol import FRESH, Continuity, ExecutorCapabilities

RESUME_MARKER = "resume.requested"

# The one admitted trigger. docs/proposals/continuity-boundary.md §2 rejects
# native-session-state, cache economics, and crash recovery on measured
# grounds; §3.3 states the evidence each would need to be admitted.
OPERATOR_REQUESTED = "operator_requested"
ALLOWED_RESUME_WHEN = frozenset({OPERATOR_REQUESTED})
ALLOWED_RESUME_SCOPES = frozenset({"attempt", "never"})


@dataclass(frozen=True)
class SessionPolicy:
    """Resolved `execution_policy.session_policy` for one project."""

    default: str = "cold"
    resume_when: tuple[str, ...] = ()
    resume_scope: str = "attempt"
    require_same_cwd: bool = True
    require_same_host: bool = True


DEFAULT_SESSION_POLICY = SessionPolicy()


def parse_session_policy(value: object) -> SessionPolicy:
    """Validate a project.yaml `session_policy` block into a SessionPolicy.

    Validation follows `parse_execution_policy`'s existing shape: raise, so a
    typo is a configuration error at preflight rather than a silent cold turn
    nobody notices.

    `default: resume` is REJECTED at v1. Resume portability is unproven —
    cross-cwd resume was never tested, the store is host-local, and the
    spike's own risk list names retention as unknown — so a project-wide
    default that assumes it would be exactly the failure pattern AGENTS.md
    warns about. A human asking per attempt is the only supported path.

    NOT WIRED into `graph_reader.parse_execution_policy` this wave. Attaching
    it there would put a new raise in the path of every project read for a
    key no project sets yet; the call site to add when a project does is
    `graph_reader.parse_execution_policy` (scripts/runtime/heartbeat/
    graph_reader.py:78), whose result already flows to the runner and the
    reconciler.
    """
    if value is None:
        return DEFAULT_SESSION_POLICY
    if not isinstance(value, Mapping):
        raise ValueError("session_policy must be a mapping")

    default = value.get("default", "cold")
    if default == "resume":
        raise ValueError(
            "session_policy.default: resume is not accepted at v1; resume is "
            "per-attempt and operator-requested"
        )
    if default != "cold":
        raise ValueError("session_policy.default must be 'cold'")

    raw_when = value.get("resume_when", [])
    if raw_when is None:
        raw_when = []
    if isinstance(raw_when, str) or not isinstance(raw_when, Sequence):
        raise ValueError("session_policy.resume_when must be a list")
    resume_when = tuple(str(item) for item in raw_when)
    unknown = [item for item in resume_when if item not in ALLOWED_RESUME_WHEN]
    if unknown:
        raise ValueError(
            f"session_policy.resume_when has unknown trigger(s) {unknown!r}; "
            f"allowed: {sorted(ALLOWED_RESUME_WHEN)}"
        )

    scope = str(value.get("resume_scope", "attempt"))
    if scope not in ALLOWED_RESUME_SCOPES:
        raise ValueError(
            f"session_policy.resume_scope must be one of "
            f"{sorted(ALLOWED_RESUME_SCOPES)}"
        )

    return SessionPolicy(
        default="cold",
        resume_when=resume_when,
        resume_scope=scope,
        require_same_cwd=_require_bool(value, "require_same_cwd"),
        require_same_host=_require_bool(value, "require_same_host"),
    )


def _require_bool(value: Mapping[str, object], key: str) -> bool:
    configured = value.get(key, True)
    if not isinstance(configured, bool):
        raise ValueError(f"session_policy.{key} must be a boolean")
    return configured


@dataclass(frozen=True)
class ResumeRequest:
    """Contents of an operator's resume.requested marker."""

    token: str
    cwd: str | None = None
    host: str | None = None


def continuity_request_dir(attempt_root: Path, job_id: str) -> Path:
    """Return the stable, pre-dispatch request directory for one job."""
    safe_job_id = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in job_id
    ).strip("._-")
    return Path(attempt_root) / "_continuity" / (safe_job_id or "job")


def read_resume_request(request_dir: Path) -> ResumeRequest | None:
    """Parse a job-keyed `resume.requested`, or None when it is unusable.

    Accepts a bare session id (the shape an operator types) or a JSON object
    carrying `session_id` plus the `cwd`/`host` the session was recorded
    against. Never raises: an unreadable or empty marker is a cold turn.
    """
    path = Path(request_dir) / RESUME_MARKER
    try:
        text = path.read_text().strip()
    except OSError:
        return None
    if not text:
        return None
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, Mapping):
            return None
        token = payload.get("session_id") or payload.get("token")
        if not isinstance(token, str) or not token.strip():
            return None
        cwd = payload.get("cwd")
        host = payload.get("host")
        return ResumeRequest(
            token=token.strip(),
            cwd=cwd if isinstance(cwd, str) and cwd else None,
            host=host if isinstance(host, str) and host else None,
        )
    return ResumeRequest(token=text)


def choose_continuity(
    *,
    request_dir: Path,
    capabilities: ExecutorCapabilities,
    policy: SessionPolicy | None = None,
    cwd: str | Path | None = None,
    host: str | None = None,
) -> Continuity:
    """The continuity decision for one dispatch. FRESH unless a human asked.

    `policy=None` means no project `session_policy` is configured, and the
    operator marker alone governs — the human owns graph truth and the marker
    IS the human. When a policy is supplied it must name `operator_requested`
    in `resume_when`, which is how a project turns the marker off entirely.

    Every negative path returns FRESH with a reason recorded on the receipt.
    Nothing here can fail an attempt.
    """
    if capabilities.resume == "none":
        return Continuity(
            mode="fresh",
            reason=f"{capabilities.executor} does not support resume",
        )
    if policy is not None and OPERATOR_REQUESTED not in policy.resume_when:
        return Continuity(
            mode="fresh", reason="project policy does not allow operator resume"
        )
    if policy is not None and policy.resume_scope == "never":
        return Continuity(mode="fresh", reason="session_policy resume_scope: never")

    request = read_resume_request(request_dir)
    if request is None:
        return Continuity(mode="fresh", reason="no operator resume request")

    effective = policy or DEFAULT_SESSION_POLICY
    if effective.require_same_cwd and request.cwd is not None:
        turn_cwd = str(cwd) if cwd is not None else None
        if turn_cwd is None or not _same_path(request.cwd, turn_cwd):
            return Continuity(
                mode="fresh",
                reason=(
                    "resume token recorded against a different cwd "
                    f"({request.cwd}); cold fallback"
                ),
            )
    if effective.require_same_host and request.host is not None:
        turn_host = host or socket.gethostname()
        if request.host != turn_host:
            return Continuity(
                mode="fresh",
                reason=(
                    f"resume token recorded on host {request.host}, running on "
                    f"{turn_host}; cold fallback"
                ),
            )

    return Continuity(
        mode="resume", token=request.token, reason=OPERATOR_REQUESTED
    )


def _same_path(left: str, right: str) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return left == right


__all__ = [
    "ALLOWED_RESUME_WHEN",
    "DEFAULT_SESSION_POLICY",
    "OPERATOR_REQUESTED",
    "RESUME_MARKER",
    "ResumeRequest",
    "SessionPolicy",
    "choose_continuity",
    "continuity_request_dir",
    "parse_session_policy",
    "read_resume_request",
]
