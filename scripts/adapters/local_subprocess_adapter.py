"""Durable direct adapter for a configured local subprocess."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from adapters.executor_protocol import (
    DispatchResult,
    NodePacket,
    PatchResult,
    SessionRef,
    SessionStatus,
)

_ARGV_ENV = "GDDP_LOCAL_SUBPROCESS_ARGV"
_SPOOL_ENV = "GDDP_LOCAL_SUBPROCESS_SPOOL_DIR"
_CWD_ENV = "GDDP_LOCAL_SUBPROCESS_CWD"
_EXECUTOR = "local_subprocess"


class LocalSubprocessAdapter:
    """Run one packet per process and retain lifecycle state in a spool."""

    def __init__(
        self,
        repo: str,
        *,
        argv: Sequence[str] | None = None,
        spool_root: str | Path | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        self.repo = repo
        self.argv = _configured_argv(argv)
        self.spool_root = _configured_spool_root(spool_root)
        configured_cwd = cwd if cwd is not None else os.environ.get(_CWD_ENV)
        self.cwd = Path(configured_cwd).resolve() if configured_cwd else None

    def dispatch(self, packet: NodePacket) -> DispatchResult:
        session_id = (
            f"{_safe_component(packet.job_id)}-"
            f"{_safe_component(packet.node_id)}-attempt-{packet.attempt_index}-"
            f"{uuid.uuid4().hex}"
        )
        attempt_dir = self.spool_root / session_id
        supervisor: subprocess.Popen[bytes] | None = None
        start_read: int | None = None
        start_write: int | None = None
        try:
            attempt_dir.mkdir(parents=True, exist_ok=False)
            execution_cwd = self.cwd
            if execution_cwd is None:
                execution_cwd = attempt_dir / "workspace"
                execution_cwd.mkdir()
            (attempt_dir / "packet.json").write_text(packet.to_json())
            (attempt_dir / "command.json").write_text(
                json.dumps(
                    {"argv": list(self.argv), "cwd": str(execution_cwd)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            start_read, start_write = os.pipe()
            supervisor = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "adapters.local_subprocess_adapter",
                    "--run-attempt",
                    str(attempt_dir),
                    "--start-fd",
                    str(start_read),
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                pass_fds=(start_read,),
            )
            os.close(start_read)
            start_read = None
            _atomic_write(attempt_dir / "supervisor.pid", str(supervisor.pid))
            os.write(start_write, b"1")
        except Exception as exc:
            if supervisor is not None:
                try:
                    os.killpg(supervisor.pid, signal.SIGTERM)
                except OSError:
                    pass
            return DispatchResult(
                success=False,
                error=f"local subprocess dispatch failed: {exc}",
            )
        finally:
            if start_read is not None:
                os.close(start_read)
            if start_write is not None:
                os.close(start_write)

        return DispatchResult(
            success=True,
            session_ref=SessionRef(executor=_EXECUTOR, session_id=session_id),
        )

    def status(self, session_ref: SessionRef) -> SessionStatus:
        return read_local_subprocess_status(self.spool_root, session_ref.session_id)

    def collect(self, session_ref: SessionRef, dest_path: Path) -> PatchResult:
        status = self.status(session_ref)
        if status.state != "completed":
            return PatchResult(
                success=False,
                error=status.error or f"local subprocess is {status.state}",
            )

        attempt_dir = self._attempt_dir(session_ref)
        if attempt_dir is None:
            return PatchResult(success=False, error="invalid local subprocess session")
        stdout_text = _read_text(attempt_dir / "stdout")
        try:
            destination = Path(dest_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(stdout_text)
        except OSError as exc:
            return PatchResult(
                success=False,
                error=f"failed to write handoff to {dest_path}: {exc}",
            )

        handoff = _parse_local_result_handoff(stdout_text)
        if handoff is None:
            return PatchResult(
                success=False,
                patch_path=str(destination),
                error="stdout is not a gddp.local_result.v1 commit-ref handoff",
            )

        result_sha = handoff.get("result_commit_sha")
        worktree_path = handoff.get("worktree_path")
        if isinstance(result_sha, str) and result_sha:
            return PatchResult(
                success=True,
                patch_path=str(destination),
                result_commit_sha=result_sha,
                result_ref=handoff.get("result_ref")
                if isinstance(handoff.get("result_ref"), str)
                else None,
                worktree_path=worktree_path
                if isinstance(worktree_path, str)
                else None,
            )

        error = handoff.get("error")
        return PatchResult(
            success=False,
            patch_path=str(destination),
            result_ref=handoff.get("result_ref")
            if isinstance(handoff.get("result_ref"), str)
            else None,
            worktree_path=worktree_path if isinstance(worktree_path, str) else None,
            error=str(error) if error else "persist failed without result commit",
        )

    def cancel(self, session_ref: SessionRef) -> bool:
        attempt_dir = self._attempt_dir(session_ref)
        if attempt_dir is None or not attempt_dir.is_dir():
            return False
        if (attempt_dir / "exit.json").exists():
            return False
        try:
            _atomic_write(attempt_dir / "cancel.requested", "")
        except OSError:
            return False

        pid = _read_pid(attempt_dir / "pid")
        if pid is None:
            return True
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
        return True

    def _attempt_dir(self, session_ref: SessionRef) -> Path | None:
        if session_ref.executor != _EXECUTOR:
            return None
        session_id = session_ref.session_id
        if (
            not session_id
            or session_id in {".", ".."}
            or Path(session_id).name != session_id
        ):
            return None
        return self.spool_root / session_id


def read_local_subprocess_status(
    spool_root: Path, session_id: str
) -> "SessionStatus":
    """Read-only durable status of one local_subprocess session.

    Computes the same verdict the adapter's status() would, but takes the
    spool root as an explicit argument. Safe to call from a normal operator
    shell that has neither the dispatch argv nor any local_subprocess env
    set. Never mutates the spool, the adapter object, or any external state.
    """
    from adapters.executor_protocol import SessionStatus

    if (
        not session_id
        or session_id in {".", ".."}
        or Path(session_id).name != session_id
    ):
        return SessionStatus(state="failed", error="invalid local subprocess session id")
    attempt_dir = Path(spool_root) / session_id
    if not attempt_dir.is_dir():
        return SessionStatus(state="failed", error="local subprocess spool not found")

    exit_path = attempt_dir / "exit.json"
    if exit_path.exists():
        try:
            exit_state = json.loads(exit_path.read_text())
            returncode = int(exit_state["returncode"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return SessionStatus(
                state="failed", error=f"invalid local subprocess exit state: {exc}"
            )
        if returncode == 0:
            return SessionStatus(state="completed")
        stderr = _read_text(attempt_dir / "stderr").strip()
        if exit_state.get("cancelled"):
            detail = f"local subprocess cancelled (code {returncode})"
        else:
            detail = f"local subprocess exited with code {returncode}"
        if stderr:
            detail = f"{detail}: {stderr}"
        handoff = _parse_local_result_handoff(_read_text(attempt_dir / "stdout"))
        if handoff is not None:
            worktree_path = handoff.get("worktree_path")
            handoff_error = handoff.get("error")
            if isinstance(worktree_path, str) and worktree_path:
                path_detail = f"persist failed; worktree kept at {worktree_path}"
                if handoff_error:
                    path_detail = f"{path_detail}: {handoff_error}"
                detail = f"{detail}; {path_detail}"
            elif handoff_error:
                detail = f"{detail}; {handoff_error}"
        return SessionStatus(state="failed", error=detail)

    pid = _read_pid(attempt_dir / "pid")
    if pid is not None and _pid_is_running(pid):
        return SessionStatus(state="running")
    supervisor_pid = _read_pid(attempt_dir / "supervisor.pid")
    if supervisor_pid is not None and _pid_is_running(supervisor_pid):
        return SessionStatus(state="dispatched")
    return SessionStatus(
        state="failed",
        error="local subprocess exited without durable exit state",
    )


def _configured_argv(argv: Sequence[str] | None) -> tuple[str, ...]:
    if argv is None:
        raw = os.environ.get(_ARGV_ENV)
        if not raw:
            raise ValueError(f"local subprocess argv is required ({_ARGV_ENV})")
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{_ARGV_ENV} must be a JSON argv array") from exc
        if not isinstance(decoded, list):
            raise ValueError(f"{_ARGV_ENV} must be a JSON argv array")
        argv = decoded
    configured = tuple(str(item) for item in argv)
    if not configured:
        raise ValueError("local subprocess argv cannot be empty")
    return configured


def _configured_spool_root(spool_root: str | Path | None) -> Path:
    configured = spool_root if spool_root is not None else os.environ.get(_SPOOL_ENV)
    if configured is None:
        raise ValueError(f"local subprocess spool root is required ({_SPOOL_ENV})")
    return Path(configured).expanduser().resolve()


def _safe_component(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "-" for character in value)
    return safe.strip("-") or "unknown"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _parse_local_result_handoff(stdout_text: str) -> dict | None:
    """Parse gddp.local_result.v1 JSON from attempt stdout.

    Accepts a single JSON object, optionally surrounded by whitespace or a
    trailing newline. Returns None when stdout is not that handoff schema.
    """
    text = (stdout_text or "").strip()
    if not text:
        return None
    # Prefer the last non-empty line in case residual agent noise leaked.
    candidates = [text]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        candidates.insert(0, lines[-1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("schema") == "gddp.local_result.v1":
            return payload
    return None


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text())
    except (OSError, ValueError):
        return None


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content)
    temporary.replace(path)


def _run_attempt(attempt_dir: Path, start_fd: int | None = None) -> int:
    cancelled = False
    try:
        if start_fd is not None and os.read(start_fd, 1) != b"1":
            raise RuntimeError("dispatch startup handshake was not published")
        command = json.loads((attempt_dir / "command.json").read_text())
        argv = command["argv"]
        cwd = command["cwd"]
        if not isinstance(argv, list) or not argv:
            raise ValueError("configured argv is invalid")
        if (attempt_dir / "cancel.requested").exists():
            cancelled = True
            returncode = 143
        else:
            with (
                (attempt_dir / "packet.json").open("rb") as packet_input,
                (attempt_dir / "stdout").open("wb") as stdout,
                (attempt_dir / "stderr").open("wb") as stderr,
            ):
                process = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    stdin=packet_input,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    start_new_session=True,
                )
                try:
                    _atomic_write(attempt_dir / "pid", str(process.pid))
                except Exception:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait()
                    raise
                if (attempt_dir / "cancel.requested").exists():
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except OSError:
                        pass
                returncode = process.wait()
                cancelled = (
                    returncode != 0
                    and (attempt_dir / "cancel.requested").exists()
                )
    except Exception as exc:
        with (attempt_dir / "stderr").open("ab") as stderr:
            stderr.write(f"local subprocess supervisor failed: {exc}\n".encode())
        returncode = 127

    _atomic_write(
        attempt_dir / "exit.json",
        json.dumps(
            {
                "returncode": returncode,
                "cancelled": cancelled,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    return 0


def _main(argv: Sequence[str]) -> int:
    if (
        len(argv) == 4
        and argv[0] == "--run-attempt"
        and argv[2] == "--start-fd"
    ):
        return _run_attempt(Path(argv[1]), int(argv[3]))
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
