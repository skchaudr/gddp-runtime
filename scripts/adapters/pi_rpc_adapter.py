"""Persistent Pi executor via `pi --mode rpc` (JSONL stdin/stdout).

Verified transport (scripts/runtime/spike/pi_rpc_persistent_spike.py):
  - Turn boundary event: agent_end
  - Resume after process death: --session <sessionFile>
  - Multi-turn context survives in one process / session file

One NodePacket = one RPC turn. The process is supervised in a durable spool
and may outlive a single status poll. Plumbing death (no agent_end) maps to
the reconciler's plumbing-failure path via the same exit.json contract as
local_subprocess ("exited without durable exit state" when supervisor dies
mid-turn without writing exit.json).
"""

from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import sys
import threading
import time
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

_EXECUTOR = "pi_rpc"
_SPOOL_ENV = "GDDP_PI_RPC_SPOOL_DIR"
_MODEL_ENV = "GDDP_PI_RPC_MODEL"
_BINARY_ENV = "GDDP_PI_RPC_BINARY"
_TOOLS_ENV = "GDDP_PI_RPC_TOOLS"
_TIMEOUT_ENV = "GDDP_PI_RPC_TURN_TIMEOUT_S"
_DEFAULT_MODEL = "xai/grok-4.5"
_DEFAULT_TOOLS = "read,bash,edit,write,grep,find,ls"
_DEFAULT_TIMEOUT_S = 1800.0

_PACKET_PREAMBLE = (
    "Treat the following JSON as the authoritative GDDP NodePacket. "
    "Work only in the current worktree. Implement its goal within its "
    "constraints, create its required artifacts, run relevant checks, then "
    "stop. Never modify graph truth or runtime databases. "
    "When finished, leave your changes as ordinary git working-tree edits "
    "(do not push to main)."
)


class PiRpcAdapter:
    """Drive one NodePacket turn over a durable `pi --mode rpc` session."""

    executor_name = _EXECUTOR

    def __init__(
        self,
        repo: str,
        *,
        spool_root: str | Path | None = None,
        cwd: str | Path | None = None,
        model: str | None = None,
        pi_binary: str | None = None,
        tools: str | None = None,
        turn_timeout_s: float | None = None,
        resume_session_file: str | Path | None = None,
    ) -> None:
        self.repo = repo
        self.spool_root = _configured_spool_root(spool_root)
        configured_cwd = cwd if cwd is not None else os.environ.get("GDDP_PI_RPC_CWD")
        self.cwd = Path(configured_cwd).resolve() if configured_cwd else None
        self.model = model or os.environ.get(_MODEL_ENV) or _DEFAULT_MODEL
        self.pi_binary = pi_binary or os.environ.get(_BINARY_ENV) or "pi"
        self.tools = tools or os.environ.get(_TOOLS_ENV) or _DEFAULT_TOOLS
        if turn_timeout_s is not None:
            self.turn_timeout_s = float(turn_timeout_s)
        else:
            self.turn_timeout_s = float(
                os.environ.get(_TIMEOUT_ENV, str(_DEFAULT_TIMEOUT_S))
            )
        self.resume_session_file = (
            Path(resume_session_file) if resume_session_file else None
        )

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
                # Fall back to the process cwd (dispatcher sets repo_path as cwd
                # for local transports). The supervisor creates the worktree.
                execution_cwd = Path.cwd()
            (attempt_dir / "packet.json").write_text(packet.to_json())
            config = {
                "pi_binary": self.pi_binary,
                "model": self.model,
                "tools": self.tools,
                "turn_timeout_s": self.turn_timeout_s,
                "repo_cwd": str(execution_cwd),
                "resume_session_file": (
                    str(self.resume_session_file)
                    if self.resume_session_file
                    else None
                ),
            }
            (attempt_dir / "command.json").write_text(
                json.dumps(config, sort_keys=True, separators=(",", ":"))
            )
            start_read, start_write = os.pipe()
            supervisor = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "adapters.pi_rpc_adapter",
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
                error=f"pi_rpc dispatch failed: {exc}",
            )
        finally:
            if start_read is not None:
                os.close(start_read)
            if start_write is not None:
                os.close(start_write)

        return DispatchResult(
            success=True,
            session_ref=SessionRef(executor=self.executor_name, session_id=session_id),
        )

    def status(self, session_ref: SessionRef) -> SessionStatus:
        return read_pi_rpc_status(self.spool_root, session_ref.session_id)

    def collect(self, session_ref: SessionRef, dest_path: Path) -> PatchResult:
        status = self.status(session_ref)
        if status.state != "completed":
            return PatchResult(
                success=False,
                error=status.error or f"pi_rpc session is {status.state}",
            )
        attempt_dir = self._attempt_dir(session_ref)
        if attempt_dir is None:
            return PatchResult(success=False, error="invalid pi_rpc session")
        result_path = attempt_dir / "result.json"
        try:
            handoff = json.loads(result_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return PatchResult(
                success=False,
                error=f"pi_rpc missing result handoff: {exc}",
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
        result_sha = handoff.get("result_commit_sha")
        if isinstance(result_sha, str) and result_sha:
            return PatchResult(
                success=True,
                patch_path=str(destination),
                result_commit_sha=result_sha,
                result_ref=handoff.get("result_ref")
                if isinstance(handoff.get("result_ref"), str)
                else None,
                worktree_path=handoff.get("worktree_path")
                if isinstance(handoff.get("worktree_path"), str)
                else None,
            )
        return PatchResult(
            success=False,
            patch_path=str(destination),
            result_ref=handoff.get("result_ref")
            if isinstance(handoff.get("result_ref"), str)
            else None,
            worktree_path=handoff.get("worktree_path")
            if isinstance(handoff.get("worktree_path"), str)
            else None,
            error=str(handoff.get("error") or "pi_rpc persist failed without result"),
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
        if pid is not None:
            try:
                os.killpg(pid, signal.SIGTERM)
            except OSError:
                pass
        supervisor_pid = _read_pid(attempt_dir / "supervisor.pid")
        if supervisor_pid is not None:
            try:
                os.killpg(supervisor_pid, signal.SIGTERM)
            except OSError:
                pass
        return True

    def _attempt_dir(self, session_ref: SessionRef) -> Path | None:
        if session_ref.executor != self.executor_name:
            return None
        session_id = session_ref.session_id
        if (
            not session_id
            or session_id in {".", ".."}
            or Path(session_id).name != session_id
        ):
            return None
        return self.spool_root / session_id


def read_pi_rpc_status(spool_root: Path, session_id: str) -> SessionStatus:
    """Read-only durable status of one pi_rpc session (operator-shell safe)."""
    if (
        not session_id
        or session_id in {".", ".."}
        or Path(session_id).name != session_id
    ):
        return SessionStatus(state="failed", error="invalid pi_rpc session id")
    attempt_dir = Path(spool_root) / session_id
    if not attempt_dir.is_dir():
        return SessionStatus(state="failed", error="pi_rpc spool not found")

    exit_path = attempt_dir / "exit.json"
    if exit_path.exists():
        try:
            exit_state = json.loads(exit_path.read_text())
            returncode = int(exit_state["returncode"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return SessionStatus(
                state="failed",
                error=f"invalid pi_rpc exit state: {exc}",
            )
        if returncode == 0:
            return SessionStatus(state="completed")
        detail = exit_state.get("error") or f"pi_rpc exited with code {returncode}"
        if exit_state.get("cancelled"):
            detail = f"pi_rpc cancelled: {detail}"
        # No agent_end → plumbing-class failure text (reconciler classifies).
        if exit_state.get("plumbing"):
            detail = (
                "pi_rpc exited without durable exit state"
                if not exit_state.get("error")
                else f"pi_rpc exited without durable exit state: {exit_state.get('error')}"
            )
        return SessionStatus(state="failed", error=str(detail))

    pid = _read_pid(attempt_dir / "pid")
    if pid is not None and _pid_is_running(pid):
        return SessionStatus(state="running")
    supervisor_pid = _read_pid(attempt_dir / "supervisor.pid")
    if supervisor_pid is not None and _pid_is_running(supervisor_pid):
        return SessionStatus(state="dispatched")
    return SessionStatus(
        state="failed",
        error="pi_rpc exited without durable exit state",
    )


# ---------------------------------------------------------------------------
# Supervisor (--run-attempt)
# ---------------------------------------------------------------------------


def run_attempt(attempt_dir: Path) -> int:
    """Drive one packet turn to agent_end, then persist a commit-ref handoff."""
    from local_agent_executor import (  # noqa: PLC0415 - scripts/ on path
        create_worktree,
        load_packet,
        persist_result,
        record_worktree_correlation,
        remove_worktree,
    )

    packet_raw = (attempt_dir / "packet.json").read_text()
    config = json.loads((attempt_dir / "command.json").read_text())
    packet = load_packet(packet_raw)
    repo = Path(config["repo_cwd"]).resolve()
    model = str(config["model"])
    tools = str(config["tools"])
    pi_binary = str(config["pi_binary"])
    turn_timeout_s = float(config.get("turn_timeout_s") or _DEFAULT_TIMEOUT_S)
    resume_session = config.get("resume_session_file")
    session_dir = attempt_dir / "pi-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    events_path = attempt_dir / "events.jsonl"
    worktree: Path | None = None
    client: _RpcClient | None = None
    cancelled = False
    plumbing = False
    error: str | None = None
    returncode = 1

    cancel_path = attempt_dir / "cancel.requested"

    def _cancel_watcher(proc: subprocess.Popen[str]) -> None:
        nonlocal cancelled
        while proc.poll() is None:
            if cancel_path.exists():
                cancelled = True
                try:
                    client and client.send({"type": "abort"}, wait_response=False)
                except Exception:
                    pass
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except OSError:
                    pass
                return
            time.sleep(0.25)

    try:
        worktree = create_worktree(repo, str(packet["expected_base_commit_sha"]))
        record_worktree_correlation(worktree, packet)
        (attempt_dir / "worktree_path").write_text(str(worktree))

        cmd = [
            pi_binary,
            "--mode",
            "rpc",
            "--model",
            model,
            "--session-dir",
            str(session_dir),
            "--tools",
            tools,
        ]
        if resume_session:
            cmd.extend(["--session", str(resume_session)])

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(worktree),
            start_new_session=True,
        )
        _atomic_write(attempt_dir / "pid", str(proc.pid))
        client = _RpcClient(proc, events_path=events_path)
        threading.Thread(target=_cancel_watcher, args=(proc,), daemon=True).start()

        # Settle + readiness probe (matches spike).
        time.sleep(0.4)
        if proc.poll() is not None:
            err = proc.stderr.read() if proc.stderr else ""
            plumbing = True
            error = f"pi exited immediately ({proc.returncode}): {err[:500]}"
            returncode = proc.returncode or 1
        else:
            try:
                state = client.get_state()
                session_file = state.get("sessionFile") or state.get("session_file")
                if session_file:
                    _atomic_write(attempt_dir / "session_file", str(session_file))
            except Exception as exc:
                # Non-fatal: some builds emit bootstrap noise first.
                (attempt_dir / "get_state_error.txt").write_text(str(exc))

            prompt = (
                f"{_PACKET_PREAMBLE}\n\n"
                f"execution_attempt_id: {packet.get('execution_attempt_id')}\n\n"
                f"{packet_raw}"
            )
            try:
                client.prompt_and_wait_agent_end(prompt, timeout=turn_timeout_s)
            except _PlumbingError as exc:
                plumbing = True
                error = str(exc)
                returncode = 1
            except Exception as exc:
                if cancelled:
                    error = f"cancelled: {exc}"
                    returncode = 130
                else:
                    # Turn may have completed with a non-zero agent outcome —
                    # still try to persist whatever is in the worktree.
                    error = str(exc)
                    returncode = 1
                if proc.poll() is None and not cancelled:
                    # agent_end never arrived and process still up → treat as
                    # work failure after aborting the turn.
                    try:
                        client.send({"type": "abort"}, wait_response=False)
                    except Exception:
                        pass

            if not plumbing and not cancelled:
                handoff = persist_result(worktree, packet)
                (attempt_dir / "result.json").write_text(
                    json.dumps(handoff, sort_keys=True, separators=(",", ":"))
                )
                if handoff.get("result_commit_sha"):
                    returncode = 0
                    error = None
                    try:
                        remove_worktree(repo, worktree)
                        worktree = None
                    except Exception:
                        pass
                else:
                    returncode = 1
                    error = str(handoff.get("error") or "persist failed")
    except Exception as exc:
        plumbing = True
        error = f"pi_rpc supervisor failed: {exc}"
        returncode = 1
    finally:
        if client is not None and client.proc.poll() is None:
            try:
                os.killpg(client.proc.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                client.proc.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(client.proc.pid, signal.SIGKILL)
                except OSError:
                    pass
        exit_state = {
            "returncode": returncode,
            "cancelled": cancelled,
            "plumbing": plumbing and not cancelled,
            "error": error,
        }
        _atomic_write(
            attempt_dir / "exit.json",
            json.dumps(exit_state, sort_keys=True, separators=(",", ":")),
        )
    return returncode


class _PlumbingError(RuntimeError):
    """Process died or protocol broke before a durable agent_end."""


class _RpcClient:
    def __init__(self, proc: subprocess.Popen[str], *, events_path: Path):
        self.proc = proc
        self.events_path = events_path
        self._req = 0
        self._lock = threading.Lock()

    def send(self, obj: dict, *, wait_response: bool = True, timeout: float = 60.0) -> dict | None:
        with self._lock:
            self._req += 1
            if "id" not in obj:
                obj = {**obj, "id": f"req-{self._req}"}
            assert self.proc.stdin is not None
            self.proc.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
            self.proc.stdin.flush()
            if not wait_response:
                return None
            deadline = time.time() + timeout
            while time.time() < deadline:
                evt = self._read_one(timeout=max(0.05, deadline - time.time()))
                if evt is None:
                    if self.proc.poll() is not None:
                        raise _PlumbingError(
                            f"pi exited during send ({self.proc.returncode})"
                        )
                    continue
                self._record(evt)
                if evt.get("type") == "response" and evt.get("id") == obj["id"]:
                    return evt
            raise TimeoutError(f"no response for {obj.get('type')}")

    def get_state(self) -> dict:
        resp = self.send({"type": "get_state"})
        if not resp or not resp.get("success"):
            raise RuntimeError(f"get_state failed: {resp}")
        data = resp.get("data") or {}
        if not isinstance(data, dict):
            return {}
        return data

    def prompt_and_wait_agent_end(self, message: str, *, timeout: float) -> None:
        resp = self.send({"type": "prompt", "message": message}, timeout=min(60.0, timeout))
        if not resp or not resp.get("success"):
            # Some builds accept via event stream only; tolerate missing success
            # if the process is still alive and we can wait for agent_end.
            if self.proc.poll() is not None:
                raise _PlumbingError(f"prompt rejected and process dead: {resp}")
        deadline = time.time() + timeout
        while time.time() < deadline:
            evt = self._read_one(timeout=max(0.1, min(1.0, deadline - time.time())))
            if evt is None:
                if self.proc.poll() is not None:
                    raise _PlumbingError(
                        f"pi exited before agent_end ({self.proc.returncode})"
                    )
                continue
            self._record(evt)
            et = evt.get("type") or evt.get("event")
            # Spike: agent_end is the durable turn boundary.
            if et == "agent_end" or (
                isinstance(evt.get("event"), dict)
                and evt["event"].get("type") == "agent_end"
            ):
                return
            # Nested shapes from some builds.
            if evt.get("type") == "agent_end":
                return
        raise _PlumbingError("timed out waiting for agent_end")

    def _read_one(self, *, timeout: float) -> dict | None:
        assert self.proc.stdout is not None
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            return None
        line = self.proc.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"type": "_non_json", "raw": line[:500]}

    def _record(self, evt: dict) -> None:
        try:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(evt, separators=(",", ":")) + "\n")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _configured_spool_root(spool_root: str | Path | None) -> Path:
    configured = (
        spool_root
        if spool_root is not None
        else os.environ.get(_SPOOL_ENV)
        or os.environ.get("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR")
    )
    if configured is None:
        raise ValueError(f"pi_rpc spool root is required ({_SPOOL_ENV})")
    return Path(configured).expanduser().resolve()


def _safe_component(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value)[:80]


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp.{uuid.uuid4().hex}")
    tmp.write_text(text)
    tmp.replace(path)


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and argv[0] == "--run-attempt":
        attempt_dir = Path(argv[1])
        start_fd: int | None = None
        if len(argv) >= 4 and argv[2] == "--start-fd":
            start_fd = int(argv[3])
        if start_fd is not None:
            # Wait for parent to finish recording supervisor.pid.
            try:
                os.read(start_fd, 1)
            finally:
                os.close(start_fd)
        return run_attempt(attempt_dir)
    print("usage: python -m adapters.pi_rpc_adapter --run-attempt DIR", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
