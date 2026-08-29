"""Executor-neutral runtime for one local, worktree-backed attempt.

Transports supply invocation and event translation. This module owns attempt
identity, spool paths, supervisor startup, durable exit state, status
derivation, result handoff decoding, worktree durability, evidence, and
process-group signal escalation.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from adapters.executor_events import ExecutorEvent, read_events, turn_usage
from adapters.executor_protocol import (
    DispatchResult,
    NodePacket,
    PatchResult,
    SessionRef,
    SessionStatus,
)
from adapters.session_prompt import merged_turn_pointers
from runtime.context_coverage import compute_turn_context_coverage


@dataclass(frozen=True)
class AttemptPaths:
    """Canonical paths beneath one local attempt spool directory."""

    root: Path

    @property
    def packet(self) -> Path:
        return self.root / "packet.json"

    @property
    def command(self) -> Path:
        return self.root / "command.json"

    @property
    def worktree(self) -> Path:
        return self.root / "worktree_path"

    @property
    def exit(self) -> Path:
        return self.root / "exit.json"

    @property
    def result(self) -> Path:
        return self.root / "result.json"

    @property
    def cancel_requested(self) -> Path:
        return self.root / "cancel.requested"


@dataclass(frozen=True)
class ExitState:
    """Versionless durable exit.json schema shared by local transports."""

    returncode: int
    cancelled: bool
    plumbing: bool
    error: str | None = None

    def to_json_value(self) -> dict[str, object]:
        return {
            "returncode": self.returncode,
            "cancelled": self.cancelled,
            "plumbing": self.plumbing,
            "error": self.error,
        }

    @classmethod
    def from_json_value(cls, value: object) -> "ExitState":
        if not isinstance(value, Mapping):
            raise TypeError("exit state must be an object")
        return cls(
            returncode=int(value["returncode"]),
            cancelled=bool(value.get("cancelled", False)),
            plumbing=bool(value.get("plumbing", False)),
            error=str(value["error"]) if value.get("error") is not None else None,
        )


@dataclass
class LocalAttemptStatus(SessionStatus):
    """SessionStatus carrying retry-budget classification as data."""

    plumbing: bool = False


@dataclass(frozen=True)
class TurnOutcome:
    """Transport result consumed by the generic attempt supervisor."""

    returncode: int
    cancelled: bool = False
    plumbing: bool = False
    error: str | None = None


TurnRunner = Callable[[Path, Mapping[str, object], dict], TurnOutcome]


def make_attempt_id(packet: NodePacket) -> str:
    """Unique, operator-readable local attempt identity."""
    return (
        f"{safe_component(packet.job_id)}-"
        f"{safe_component(packet.node_id)}-attempt-{packet.attempt_index}-"
        f"{uuid.uuid4().hex}"
    )


def attempt_dir_for(spool_root: Path, attempt_id: str) -> Path | None:
    """Resolve one direct child of a spool root, rejecting traversal."""
    if (
        not attempt_id
        or attempt_id in {".", ".."}
        or Path(attempt_id).name != attempt_id
    ):
        return None
    return Path(spool_root) / attempt_id


def dispatch_worktree_attempt(
    *,
    packet: NodePacket,
    spool_root: Path,
    repo: Path,
    executor: str,
    command: Mapping[str, object],
    supervisor_module: str,
    supervisor_cwd: Path,
) -> DispatchResult:
    """Prepare a worktree attempt and publish its detached supervisor."""
    from local_agent_executor import create_worktree, remove_worktree

    attempt_id = make_attempt_id(packet)
    paths = AttemptPaths(Path(spool_root) / attempt_id)
    worktree: Path | None = None
    supervisor: subprocess.Popen[bytes] | None = None
    start_read: int | None = None
    start_write: int | None = None
    try:
        paths.root.mkdir(parents=True, exist_ok=False)
        paths.packet.write_text(packet.to_json())
        base_sha = packet.expected_base_commit_sha
        if not base_sha:
            raise ValueError("packet missing expected_base_commit_sha")
        worktree = create_worktree(repo, str(base_sha))
        atomic_write(paths.worktree, str(worktree))
        paths.command.write_text(
            json.dumps(
                {**command, "repo": str(repo), "worktree": str(worktree)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )

        start_read, start_write = os.pipe()
        supervisor = subprocess.Popen(
            [
                sys.executable,
                "-m",
                supervisor_module,
                "--run-attempt",
                str(paths.root),
                "--start-fd",
                str(start_read),
            ],
            cwd=str(supervisor_cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            pass_fds=(start_read,),
        )
        os.close(start_read)
        start_read = None
        atomic_write(paths.root / "supervisor.pid", str(supervisor.pid))
        os.write(start_write, b"1")
    except Exception as exc:
        if supervisor is not None:
            _signal_process_group(supervisor.pid, signal.SIGTERM)
        if worktree is not None:
            try:
                remove_worktree(repo, worktree)
            except Exception:
                pass
        return DispatchResult(
            success=False,
            error=f"{executor} dispatch failed: {exc}",
        )
    finally:
        if start_read is not None:
            os.close(start_read)
        if start_write is not None:
            os.close(start_write)

    return DispatchResult(
        success=True,
        session_ref=SessionRef(executor=executor, session_id=attempt_id),
    )


def read_attempt_status(
    spool_root: Path,
    attempt_id: str,
    *,
    executor: str,
) -> LocalAttemptStatus:
    """Derive status from durable state first, then live process markers."""
    attempt_dir = attempt_dir_for(Path(spool_root), attempt_id)
    if attempt_dir is None:
        return LocalAttemptStatus(
            state="failed",
            error=f"invalid {executor} session id",
            plumbing=True,
        )
    if not attempt_dir.is_dir():
        return LocalAttemptStatus(
            state="failed",
            error=f"{executor} spool not found",
            plumbing=True,
        )

    exit_path = attempt_dir / "exit.json"
    if exit_path.exists():
        try:
            exit_state = ExitState.from_json_value(json.loads(exit_path.read_text()))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return LocalAttemptStatus(
                state="failed",
                error=f"invalid {executor} exit state: {exc}",
                plumbing=True,
            )
        if exit_state.returncode == 0:
            return LocalAttemptStatus(state="completed", plumbing=False)
        detail = exit_state.error or f"{executor} exited with code {exit_state.returncode}"
        if exit_state.cancelled:
            detail = f"{executor} cancelled: {detail}"
        return LocalAttemptStatus(
            state="failed",
            error=str(detail),
            plumbing=exit_state.plumbing,
        )

    pid = read_pid(attempt_dir / "pid")
    if pid is not None and pid_is_running(pid):
        return LocalAttemptStatus(state="running")
    supervisor_pid = read_pid(attempt_dir / "supervisor.pid")
    if supervisor_pid is not None and pid_is_running(supervisor_pid):
        return LocalAttemptStatus(state="dispatched")
    return LocalAttemptStatus(
        state="failed",
        error=f"{executor} attempt terminal record is missing",
        plumbing=True,
    )


def collect_persisted_result(
    attempt_dir: Path,
    dest_path: Path,
    *,
    executor: str,
) -> PatchResult:
    """Decode result.json and save the exact handoff at the requested path."""
    try:
        handoff = json.loads((attempt_dir / "result.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return PatchResult(
            success=False,
            error=f"{executor} missing result handoff: {exc}",
        )
    if not isinstance(handoff, dict):
        return PatchResult(
            success=False,
            error=f"{executor} result handoff is not an object",
        )
    try:
        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(handoff, sort_keys=True, separators=(",", ":"))
        )
    except OSError as exc:
        return PatchResult(
            success=False,
            error=f"failed to write handoff to {dest_path}: {exc}",
        )
    return decode_result_handoff(handoff, patch_path=destination, executor=executor)


def decode_result_handoff(
    handoff: Mapping[str, object],
    *,
    patch_path: Path,
    executor: str,
) -> PatchResult:
    """Map one persist_result handoff onto the common PatchResult."""
    result_sha = handoff.get("result_commit_sha")
    result_ref = handoff.get("result_ref")
    worktree_path = handoff.get("worktree_path")
    common = {
        "patch_path": str(patch_path),
        "result_ref": result_ref if isinstance(result_ref, str) else None,
        "worktree_path": (
            worktree_path if isinstance(worktree_path, str) else None
        ),
    }
    if isinstance(result_sha, str) and result_sha:
        return PatchResult(
            success=True,
            result_commit_sha=result_sha,
            **common,
        )
    return PatchResult(
        success=False,
        error=str(handoff.get("error") or f"{executor} persist failed without result"),
        **common,
    )


def cancel_attempt(
    attempt_dir: Path,
    *,
    grace_s: float,
    signals: tuple[int, int] = (signal.SIGTERM, signal.SIGKILL),
) -> bool:
    """Request cancellation and preempt a published process when present."""
    paths = AttemptPaths(attempt_dir)
    if not attempt_dir.is_dir() or paths.exit.exists():
        return False
    try:
        atomic_write(paths.cancel_requested, "")
    except OSError:
        return False
    pid = read_pid(attempt_dir / "pid")
    if pid is not None:
        terminate_process_group(
            pid,
            grace_s=grace_s,
            graceful_signal=signals[0],
            final_signal=signals[1],
        )
    return True


def terminate_process_group(
    pid: int,
    *,
    grace_s: float,
    graceful_signal: int,
    final_signal: int,
) -> None:
    """Escalate a process group from the transport's graceful to final signal."""
    if not _signal_process_group(pid, graceful_signal):
        return
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        if not pid_is_running(pid):
            return
        time.sleep(0.05)
    _signal_process_group(pid, final_signal)


def run_attempt_supervisor(
    attempt_dir: Path,
    *,
    run_turn: TurnRunner,
    start_fd: int | None = None,
) -> int:
    """Run one transport turn and always publish a durable terminal record."""
    from local_agent_executor import load_packet, record_worktree_correlation

    outcome = TurnOutcome(
        returncode=127,
        plumbing=True,
        error="local attempt supervisor failed before the turn",
    )
    packet: dict | None = None
    command: Mapping[str, object] = {}
    worktree: Path | None = None
    repo: Path | None = None
    try:
        if start_fd is not None and os.read(start_fd, 1) != b"1":
            raise RuntimeError("dispatch startup handshake was not published")
        command_value = json.loads((attempt_dir / "command.json").read_text())
        if not isinstance(command_value, Mapping):
            raise TypeError("command.json must contain an object")
        command = command_value
        packet = load_packet((attempt_dir / "packet.json").read_text())
        worktree = Path(str(command["worktree"]))
        repo = Path(str(command["repo"]))
        record_worktree_correlation(worktree, packet)
        outcome = run_turn(attempt_dir, command, packet)
    except Exception as exc:
        outcome = TurnOutcome(
            returncode=127,
            plumbing=True,
            error=f"local attempt supervisor failed: {exc}",
        )

    write_post_turn_evidence(
        attempt_dir=attempt_dir,
        events=read_events(attempt_dir / "events.jsonl"),
        packet=packet,
        worktree=worktree,
    )

    if (
        not outcome.cancelled
        and not outcome.plumbing
        and packet is not None
        and worktree is not None
        and repo is not None
    ):
        handoff = persist_post_turn_result(
            attempt_dir=attempt_dir,
            packet=packet,
            worktree=worktree,
            repo=repo,
        )
        if handoff.get("result_commit_sha"):
            write_exit_state(
                attempt_dir,
                ExitState(returncode=0, cancelled=False, plumbing=False),
            )
            return 0
        error = (
            f"persist failed; worktree kept at {worktree}: "
            f"{handoff.get('error') or 'no result commit'}"
        )
        write_exit_state(
            attempt_dir,
            ExitState(
                returncode=1,
                cancelled=False,
                plumbing=False,
                error=error,
            ),
        )
        return 0

    error = outcome.error
    if worktree is not None:
        error = f"{error or 'turn ended without a result'}; worktree kept at {worktree}"
    write_exit_state(
        attempt_dir,
        ExitState(
            returncode=outcome.returncode if outcome.returncode != 0 else 1,
            cancelled=outcome.cancelled,
            plumbing=outcome.plumbing,
            error=error,
        ),
    )
    return 0


def persist_post_turn_result(
    *,
    attempt_dir: Path,
    packet: dict,
    worktree: Path,
    repo: Path,
) -> dict:
    """Persist once; remove the worktree only after result.json is durable."""
    from local_agent_executor import persist_result, remove_worktree

    handoff = persist_result(worktree, packet)
    report_path = attempt_dir / "prompt_cache_report.json"
    if report_path.exists():
        try:
            handoff["prompt_cache_report"] = json.loads(report_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    try:
        atomic_write(
            attempt_dir / "result.json",
            json.dumps(handoff, sort_keys=True, separators=(",", ":")),
        )
    except OSError as exc:
        handoff = {
            **handoff,
            "result_commit_sha": None,
            "worktree_path": str(worktree),
            "error": f"result handoff write failed: {exc}",
        }
        return handoff

    if handoff.get("result_commit_sha"):
        try:
            remove_worktree(repo, worktree)
        except Exception:
            pass
    return handoff


def write_post_turn_evidence(
    *,
    attempt_dir: Path,
    events: Sequence[ExecutorEvent],
    packet: dict | None,
    worktree: Path | None,
) -> None:
    """Write normalized usage and context coverage as best-effort evidence."""
    usage = turn_usage(list(events))
    report_path = attempt_dir / "prompt_cache_report.json"
    if (
        usage is not None
        and usage.cached_input_tokens is not None
        and report_path.exists()
    ):
        try:
            report = json.loads(report_path.read_text())
            report["actual_cached_tokens"] = usage.cached_input_tokens
            atomic_write(
                report_path,
                json.dumps(report, sort_keys=True, separators=(",", ":")),
            )
        except (OSError, TypeError, json.JSONDecodeError):
            pass

    if packet is None:
        return
    try:
        coverage = compute_turn_context_coverage(
            pointers=merged_turn_pointers([packet]),
            events=events,
            base=worktree,
        )
        if coverage is not None:
            atomic_write(
                attempt_dir / "context_coverage.json",
                json.dumps(coverage, sort_keys=True, separators=(",", ":")),
            )
    except Exception:
        pass


def write_exit_state(attempt_dir: Path, exit_state: ExitState) -> None:
    atomic_write(
        attempt_dir / "exit.json",
        json.dumps(exit_state.to_json_value(), sort_keys=True, separators=(",", ":")),
    )


def safe_component(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in value
    )[:80]


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + f".tmp.{uuid.uuid4().hex}")
    temporary.write_text(text)
    temporary.replace(path)


def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _signal_process_group(pid: int, selected_signal: int) -> bool:
    try:
        os.killpg(pid, selected_signal)
    except OSError:
        return False
    return True
