"""cursor-agent CLI as a per-turn executor transport.

Second transport on the capability contract, and deliberately thin: the only
cursor-specific code here is invocation shape, stream parsing (delegated to
events_cursor_cli), cancellation mechanism, and where the session id lives.
Everything else — the four-zone prompt, context coverage, the prompt cache
report, the commit-ref handoff, the durable exit record — is GDDP-owned and
shared with the existing transports.

Transport shape, proven by scripts/runtime/spike/cursor_cli_spike.py:
  - one subprocess per turn (`cursor-agent -p --trust --output-format
    stream-json --stream-partial-output <prompt>`), no persistent process
  - the terminal `result` event is the turn boundary; there is NO terminal
    event after a kill or a bad invocation, so the driver synthesizes one
  - cancellation is PREEMPTIVE: SIGTERM killed the turn in 1.16s, SIGKILL in
    0.02s, and the session stayed resumable afterwards
  - `--resume <session_id>` restores prior context cross-process

Continuity is cold by default and structurally so: dispatch() takes
`continuity=FRESH`. Resume happens only when an operator wrote a
`resume.requested` marker and the guards in
runtime/heartbeat/continuity_policy.py pass; an unusable token falls back to
a cold turn silently and never fails the attempt.

Spool layout per attempt (same conventions as pi_rpc/local_subprocess, so the
operator's watch surface keeps working):
  packet.json command.json worktree_path session_id supervisor.pid pid
  events.jsonl raw.jsonl stderr prompt_cache_report.json
  context_coverage.json result.json exit.json
  cancel.requested / resume.requested  (operator-written markers)
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from adapters.events_cursor_cli import CursorStreamTranslator
from adapters.executor_events import EventWriter
from adapters.executor_protocol import (
    FRESH,
    CapabilityUnsupported,
    Continuity,
    DispatchResult,
    EngagementAdapterDefaults,
    ExecutorCapabilities,
    NodePacket,
    PatchResult,
    SessionRef,
    SessionStatus,
)
from adapters.session_prompt import build_turn_prompt
from prompt_topology import prompt_cache_report
from runtime.local_attempt import (
    TurnOutcome,
    attempt_dir_for,
    atomic_write,
    cancel_attempt,
    collect_persisted_result,
    dispatch_worktree_attempt,
    read_attempt_status,
    read_text,
    run_attempt_supervisor,
    terminate_process_group,
)

_EXECUTOR = "cursor_cli"
_SPOOL_ENV = "GDDP_CURSOR_CLI_SPOOL_DIR"
_BINARY_ENV = "GDDP_CURSOR_CLI_BINARY"
# Optional. cursor-agent picks its own default model when unset (the spike ran
# model_defaulted=True end to end), so unlike pi_rpc this adapter never raises
# for a missing model — status/collect/cancel must be constructible from the
# repo alone by a reconciler that carries no executor env.
_MODEL_ENV = "GDDP_CURSOR_CLI_MODEL"
_TIMEOUT_ENV = "GDDP_CURSOR_CLI_TURN_TIMEOUT_S"

_DEFAULT_TIMEOUT_S = 1800.0
# Spike measurement: SIGTERM -> process death 1.16s; SIGKILL -> 0.02s. The
# grace is sized above the measured SIGTERM latency with headroom, not
# guessed.
_CANCEL_GRACE_S = 3.0
_CANCEL_SIGNALS = (signal.SIGTERM, signal.SIGKILL)

# Protocol zone for cursor turns. Deliberately NOT pi's preamble: pi's text
# instructs subagent fan-out and reviewer dispatch, and cursor_cli declares
# native_subagents=False. Telling an executor to use a capability it does not
# have is how a capability contract quietly becomes decoration.
_CURSOR_PREAMBLE = (
    "Treat the following JSON as the authoritative GDDP NodePacket.\n\n"
    "You are the EXECUTOR for this node. You do the work yourself: "
    "investigate, implement, and verify. You are not the graph-level "
    "orchestrator — overall graph progression, ready-node selection, and "
    "project-level status transitions are handled externally by the GDDP "
    "runtime. Your job is to satisfy this node's contract in service of "
    "graph completion, without unnecessary scope expansion or speculative "
    "hardening.\n\n"
    "Execution protocol:\n"
    "1. Read the packet, then read the project context pointers below "
    "before writing anything. A read is evidence; assuming is not.\n"
    "2. Implement the goal within the stated constraints and create every "
    "required artifact.\n"
    "3. Run the checks relevant to what you changed, and record what you "
    "ran and what it showed.\n"
    "4. Stop when the acceptance criteria are addressed. An evaluator reads "
    "your work next, and a human accepts or rejects it; you never mark a "
    "node complete yourself.\n\n"
    "This process runs ONE turn against ONE git worktree — the worktree_path "
    "named below, which is already your working directory. Everything you "
    "create must live there. Never modify graph truth or runtime databases. "
    "Leave changes as ordinary git working-tree edits — do not commit and do "
    "not push; the runtime persists this attempt's result after you stop. If "
    "you cannot satisfy part of the contract, say so plainly in your final "
    "message rather than pretending or silently narrowing the work."
)


def build_cursor_turn_prompt(*, worktree: Path, packets: Sequence[dict]):
    """Four-zone TurnPrompt for one cursor turn."""
    return build_turn_prompt(
        worktree=worktree,
        packets=packets,
        preamble=_CURSOR_PREAMBLE,
        turn_note=(
            f"### TURN — one turn on the attempt worktree {worktree}. "
            "You are the only agent working this node."
        ),
    )


class CursorCliAdapter(EngagementAdapterDefaults):
    """Run one NodePacket per cursor-agent subprocess in its own worktree."""

    executor_name = _EXECUTOR

    def __init__(
        self,
        repo: str,
        *,
        spool_root: str | Path | None = None,
        cwd: str | Path | None = None,
        binary: str | None = None,
        model: str | None = None,
        turn_timeout_s: float | None = None,
    ) -> None:
        self.repo = repo
        self.spool_root = _configured_spool_root(spool_root)
        configured_cwd = cwd if cwd is not None else os.environ.get("GDDP_CURSOR_CLI_CWD")
        self.cwd = Path(configured_cwd).resolve() if configured_cwd else None
        self.binary = binary or os.environ.get(_BINARY_ENV) or "cursor-agent"
        self.model = model or os.environ.get(_MODEL_ENV) or None
        if turn_timeout_s is not None:
            self.turn_timeout_s = float(turn_timeout_s)
        else:
            self.turn_timeout_s = float(
                os.environ.get(_TIMEOUT_ENV, str(_DEFAULT_TIMEOUT_S))
            )

    def capabilities(self) -> ExecutorCapabilities:
        """Declared capabilities. Evidence per field in the spike results.

        midturn_steering is False and must stay visible as False: a per-turn
        subprocess has no in-flight input channel, so steering here is
        cancel-then-recompose (the next attempt carries the operator's
        message), not delivery into the running turn. native_subagents is
        False because nothing in the spike or the probe exercised a subagent
        tool — unmeasured is not the same as absent, and the least-capable
        declaration is the safe one.
        """
        return ExecutorCapabilities(
            executor=self.executor_name,
            streaming_events=True,
            partial_text=True,
            cancellation="preemptive",
            resume="token",
            midturn_steering=False,
            usage_reporting=True,
            native_subagents=False,
            structured_tool_calls=True,
            engagement=False,
            reply=False,
        )

    def supports_engagement(self) -> bool:
        return self.capabilities().engagement

    def dispatch(
        self, packet: NodePacket, *, continuity: Continuity = FRESH
    ) -> DispatchResult:
        if continuity.mode == "resume" and self.capabilities().resume == "none":
            raise CapabilityUnsupported("resume", self.executor_name)

        repo_path = self.cwd or Path.cwd()
        resume_token = (
            continuity.token
            if continuity.mode == "resume" and continuity.token
            else None
        )
        return dispatch_worktree_attempt(
            packet=packet,
            spool_root=self.spool_root,
            repo=repo_path,
            executor=self.executor_name,
            command={
                "binary": self.binary,
                "model": self.model,
                "turn_timeout_s": self.turn_timeout_s,
                "continuity_mode": "resume" if resume_token else "fresh",
                "resume_token": resume_token,
                "continuity_reason": continuity.reason,
            },
            supervisor_module="adapters.cursor_cli_adapter",
            supervisor_cwd=Path(__file__).resolve().parents[1],
        )

    def status(self, session_ref: SessionRef) -> SessionStatus:
        if session_ref.executor != self.executor_name:
            return SessionStatus(state="failed", error="invalid cursor_cli session")
        return read_cursor_cli_status(self.spool_root, session_ref.session_id)

    def collect(self, session_ref: SessionRef, dest_path: Path) -> PatchResult:
        status = self.status(session_ref)
        if status.state != "completed":
            return PatchResult(
                success=False,
                error=status.error or f"cursor_cli session is {status.state}",
            )
        attempt_dir = self._attempt_dir(session_ref)
        if attempt_dir is None:
            return PatchResult(success=False, error="invalid cursor_cli session")
        return collect_persisted_result(
            attempt_dir,
            Path(dest_path),
            executor=self.executor_name,
        )

    def cancel(self, session_ref: SessionRef) -> bool:
        """Preemptive: SIGTERM the turn, SIGKILL it if it does not go.

        Returns False only when there is nothing left to cancel — no attempt
        dir, or a terminal record already written. That distinction is what
        lets the operator surface stop rendering an exited session as
        "remote may continue".
        """
        attempt_dir = self._attempt_dir(session_ref)
        if attempt_dir is None or not attempt_dir.is_dir():
            return False
        if (attempt_dir / "exit.json").exists():
            return False
        return cancel_attempt(
            attempt_dir,
            grace_s=_CANCEL_GRACE_S,
            signals=_CANCEL_SIGNALS,
        )

    def _attempt_dir(self, session_ref: SessionRef) -> Path | None:
        if session_ref.executor != self.executor_name:
            return None
        return attempt_dir_for(self.spool_root, session_ref.session_id)


def read_cursor_cli_status(spool_root: Path, session_id: str) -> SessionStatus:
    """Read-only durable status of one cursor_cli attempt (operator-safe)."""
    return read_attempt_status(
        Path(spool_root),
        session_id,
        executor=_EXECUTOR,
    )


# ---------------------------------------------------------------------------
# Attempt supervisor (--run-attempt): one cursor-agent turn, then a durable
# terminal record no matter how the turn ended.
# ---------------------------------------------------------------------------


def build_argv(
    *,
    binary: str,
    prompt: str,
    model: str | None = None,
    resume_token: str | None = None,
) -> list[str]:
    """Exact invocation the spike proved (scripts/runtime/spike/
    cursor_cli_spike.py:69-80)."""
    argv = [
        binary,
        "-p",
        "--trust",
        "--output-format",
        "stream-json",
        "--stream-partial-output",
    ]
    if model:
        argv.extend(["--model", model])
    if resume_token:
        argv.extend(["--resume", resume_token])
    argv.append(prompt)
    return argv


def _run_attempt(attempt_dir: Path, start_fd: int | None = None) -> int:
    return run_attempt_supervisor(
        attempt_dir,
        run_turn=_run_cursor_turn,
        start_fd=start_fd,
    )


def _run_cursor_turn(
    attempt_dir: Path,
    command: Mapping[str, object],
    packet: dict,
) -> TurnOutcome:
    """Cursor-specific prompt, stream translation, and terminal synthesis."""
    turn_id = uuid.uuid4().hex
    translator = CursorStreamTranslator()
    writer: EventWriter | None = None
    worktree = Path(str(command["worktree"]))
    turn_prompt = build_cursor_turn_prompt(worktree=worktree, packets=[packet])
    atomic_write(
        attempt_dir / "prompt_cache_report.json",
        json.dumps(
            prompt_cache_report(turn_prompt).as_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ),
    )

    if (attempt_dir / "cancel.requested").exists():
        cancelled = True
        returncode = 143
        error = "cancelled before the turn started"
    else:
        returncode, error, writer = _stream_turn(
            attempt_dir=attempt_dir,
            command=command,
            prompt=turn_prompt.assemble(),
            translator=translator,
            turn_id=turn_id,
        )
        cancelled = (
            returncode != 0 and (attempt_dir / "cancel.requested").exists()
        )
    plumbing = not translator.saw_turn_end and not cancelled

    if writer is None:
        # Zero stream events (a bad invocation produces none at all) still
        # needs a canonical spool to carry the synthesized turn boundary.
        writer = EventWriter(
            attempt_dir,
            executor=_EXECUTOR,
            session_id=translator.session_id or "",
            turn_id=turn_id,
        )
    if not translator.saw_turn_end:
        for pending in translator.flush_text():
            writer.emit(pending.type, raw_type=pending.raw_type, **pending.fields)
        writer.emit(
            "turn_ended",
            raw_type="",
            status="cancelled" if cancelled else "failed",
            error=error or f"cursor-agent exited with code {returncode}",
        )
    return TurnOutcome(
        returncode=returncode,
        cancelled=cancelled,
        plumbing=plumbing,
        error=error,
    )


def _stream_turn(
    *,
    attempt_dir: Path,
    command: Mapping[str, object],
    prompt: str,
    translator: CursorStreamTranslator,
    turn_id: str,
) -> tuple[int, str | None, EventWriter | None]:
    """Spawn cursor-agent and translate its stream as it arrives.

    Returns (returncode, error, writer). The writer comes back because it can
    only be built once the session id is known, and the caller needs it to
    synthesize a turn boundary the harness never emitted.
    """
    argv = build_argv(
        binary=str(command["binary"]),
        prompt=prompt,
        model=command.get("model") if isinstance(command.get("model"), str) else None,
        resume_token=command.get("resume_token")
        if isinstance(command.get("resume_token"), str)
        else None,
    )
    timeout_s = float(command.get("turn_timeout_s") or _DEFAULT_TIMEOUT_S)
    writer: EventWriter | None = None
    timed_out = threading.Event()

    with (attempt_dir / "stderr").open("wb") as stderr_file:
        proc = subprocess.Popen(
            argv,
            cwd=str(command["worktree"]),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        try:
            atomic_write(attempt_dir / "pid", str(proc.pid))
        except Exception:
            terminate_process_group(
                proc.pid,
                grace_s=_CANCEL_GRACE_S,
                graceful_signal=_CANCEL_SIGNALS[0],
                final_signal=_CANCEL_SIGNALS[1],
            )
            proc.wait()
            raise
        # Close the race where cancel() landed between spawn and pid
        # publication: cancel() could not have signalled a pid it never saw.
        if (attempt_dir / "cancel.requested").exists():
            terminate_process_group(
                proc.pid,
                grace_s=_CANCEL_GRACE_S,
                graceful_signal=_CANCEL_SIGNALS[0],
                final_signal=_CANCEL_SIGNALS[1],
            )

        def _on_timeout() -> None:
            timed_out.set()
            terminate_process_group(
                proc.pid,
                grace_s=_CANCEL_GRACE_S,
                graceful_signal=_CANCEL_SIGNALS[0],
                final_signal=_CANCEL_SIGNALS[1],
            )

        watchdog = threading.Timer(timeout_s, _on_timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    raw = None
                if writer is None:
                    # The session id rides every event and system/init is
                    # first in every observed turn; the writer needs it for
                    # the envelope, so it is built from the first line.
                    session_id = ""
                    if isinstance(raw, Mapping):
                        candidate = raw.get("session_id")
                        session_id = candidate if isinstance(candidate, str) else ""
                    writer = EventWriter(
                        attempt_dir,
                        executor=_EXECUTOR,
                        session_id=session_id,
                        turn_id=turn_id,
                    )
                    writer.emit("turn_started", raw_type="")
                writer.raw(line)
                if raw is None:
                    continue
                for translated in translator.translate(raw):
                    writer.emit(
                        translated.type,
                        raw_type=translated.raw_type,
                        **translated.fields,
                    )
                    if translated.type == "session_started" and translator.session_id:
                        # Persisted on EVERY dispatch, cold included: it is
                        # the operator's only handle for a future
                        # operator_requested resume, and it costs nothing.
                        atomic_write(
                            attempt_dir / "session_id", translator.session_id
                        )
            returncode = proc.wait()
        finally:
            watchdog.cancel()

    if timed_out.is_set():
        return returncode, f"turn exceeded {timeout_s}s and was terminated", writer
    if returncode != 0 and not translator.saw_turn_end:
        tail = read_text(attempt_dir / "stderr").strip()[-500:]
        return (
            returncode,
            tail or f"cursor-agent exited with code {returncode}",
            writer,
        )
    return returncode, None, writer


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
        raise ValueError(f"cursor_cli spool root is required ({_SPOOL_ENV})")
    return Path(configured).expanduser().resolve()


def _main(argv: Sequence[str]) -> int:
    argv = list(argv)
    if len(argv) == 4 and argv[0] == "--run-attempt" and argv[2] == "--start-fd":
        return _run_attempt(Path(argv[1]), int(argv[3]))
    if len(argv) == 2 and argv[0] == "--run-attempt":
        return _run_attempt(Path(argv[1]))
    print(
        "usage: python -m adapters.cursor_cli_adapter --run-attempt DIR "
        "[--start-fd FD]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
