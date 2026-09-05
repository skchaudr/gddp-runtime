"""Persistent Pi executor via `pi --mode rpc` (JSONL stdin/stdout).

Verified transport (scripts/runtime/spike/pi_rpc_persistent_spike.py):
  - Turn boundary event: agent_end
  - Resume after process death: --session <sessionFile>
  - Multi-turn context survives in one process / session file

Fork A (2026-08-16): one long-lived `pi --mode rpc` process is spawned PER
PROJECT, not per node — that process is the project's single executor.
dispatch() drops each NodePacket into that project's inbox.
run_orchestrator opens ONE git worktree for the session (at the first
packet's base commit) and keeps it until the session exits. Each claimed
packet is one RPC turn against that same worktree; persist_result commits
the node boundary. Worker-subagent count is a separate budget in
_PACKET_PREAMBLE. Packets that arrive mid-turn queue for the NEXT turn.

Attempt spool (the canonical half is identical to every other transport's —
adapters/executor_events.py, docs/proposals/executor-event-vocabulary.md):
  packet.json command.json supervisor.pid pid session_file worktree_path
  events.jsonl  — canonical ExecutorEvents, translated by events_pi_rpc
  raw.jsonl     — pi's own RPC lines, verbatim, for forensics and tail -F
  steer.jsonl prompt_cache_report.json context_coverage.json result.json
  exit.json

Only a pi-health failure (dead process, broken protocol, turn timeout) ends
the whole session. A worktree/persist failure OR an operator cancel is
scoped to that one node's attempt_dir: the other N-1 packets in the same
batch still persist real results, and the session stays alive for the next
queued packet. Plumbing death (no agent_end) maps to the reconciler's
plumbing-failure path via the same exit.json contract as local_subprocess
("exited without durable exit state" when the session dies mid-turn
without writing exit.json for that attempt).
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import select
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from adapters.events_pi_rpc import PiStreamTranslator
from adapters.executor_events import EventWriter, ExecutorEvent, turn_usage
from adapters.executor_protocol import (
    AttemptContext,
    FRESH,
    CapabilityUnsupported,
    Continuity,
    DispatchResult,
    ExecutorCapabilities,
    NodePacket,
    PatchResult,
    SessionRef,
    SessionStatus,
)

# build_project_zone/merged_turn_pointers/build_turn_prompt moved to the
# transport-neutral session_prompt module so a second transport reuses the
# four-zone machinery instead of copying it. Re-exported here: they are part
# of this module's existing public surface.
from adapters.session_prompt import (  # noqa: F401 - re-export
    build_project_zone,
    build_turn_prompt,
    merged_turn_pointers,
    split_packet_zones,
)
from prompt_topology import TurnPrompt, prompt_cache_report
from runtime.context_coverage import compute_turn_context_coverage
from runtime.local_attempt import locate_attempt_dir, resolve_attempt_spool_root

_EXECUTOR = "pi_rpc"
_SPOOL_ENV = "GDDP_PI_RPC_SPOOL_DIR"
_MODEL_ENV = "GDDP_PI_RPC_MODEL"
_BINARY_ENV = "GDDP_PI_RPC_BINARY"
_TOOLS_ENV = "GDDP_PI_RPC_TOOLS"
_TIMEOUT_ENV = "GDDP_PI_RPC_TURN_TIMEOUT_S"
_IDLE_TIMEOUT_ENV = "GDDP_PI_RPC_IDLE_TIMEOUT_S"
_DEFAULT_TOOLS = "read,bash,edit,write,grep,find,ls,subagent"
_DEFAULT_TIMEOUT_S = 1800.0
# Idle grace is sized for a session to survive a working day, not a
# heartbeat gap: the point of fork A is one orchestrator per project held
# across a whole graph, including long human-review pauses between nodes.
# A short grace turns every gap into a cold respawn, which is the failure
# this fork exists to remove. Env-tunable via GDDP_PI_RPC_IDLE_TIMEOUT_S.
_DEFAULT_IDLE_TIMEOUT_S = 43200.0  # 12h

_PACKET_PREAMBLE = (
    "Treat the following JSON as the authoritative GDDP NodePacket.\n\n"
    "You are the ORCHESTRATOR for this node execution session. You have autonomy "
    "over how you oversee and accomplish the work within its constraints. You do "
    "not edit the codebase or implement the changes yourself — your worker subagents "
    "are the executors of the task. You are not the graph-level orchestrator — "
    "overall graph progression, ready-node selection, and project-level status "
    "transitions are handled externally by the GDDP runtime. Your job is to oversee "
    "satisfying this node's contract in service of graph completion, without "
    "unnecessary scope expansion or speculative hardening.\n\n"
    "Execution protocol:\n"
    "1. Read the packet, then decompose the goal into bounded tasks.\n"
    "2. Dispatch worker subagents to perform the actual execution: up to 5 concurrent, "
    "model xai/grok-4.6 via the subagent tool's model parameter. Workers "
    "investigate, build, and measure; you do not.\n"
    "3. While work is in flight, dispatch ONE watcher subagent (model "
    "deepseek/deepseek-v4-flash) that actively polls state with tools and "
    "reports changes. Never spend your own turns on sleep loops or polling "
    "scripts.\n"
    "4. Integrate worker returns into the required artifacts yourself. "
    "Integration, synthesis, and small edits are yours; bulk execution work is not.\n"
    "5. Reviewers — one review per node, all reviewers count as one logical "
    "review. Close by dispatching the reviewer subagents once: deepseek-v4-pro "
    "and xai/grok-4.6 as parallel reviewers (each with a single distinct focus: "
    "criteria coverage, evidence integrity, constraint compliance), openai-codex/"
    "gpt-5.6-sol, and google/gemini-3.1-pro. Resolve their findings. If fixes are "
    "needed you may make ONE more dispatch to address them; afterwards NO further "
    "review. Then stop — the evaluator takes over from here.\n\n"
    "This session is long-lived and is the ONE persistent orchestrator for this "
    "project across many packets. The session owns one worktree for its "
    "whole life — the worktree_path named below. Point every worker at "
    "that path. Do not create another worktree, and do not spawn a "
    "per-packet executor. Worker-subagent count is the concurrent "
    "cap in step 2, a shared budget, not one worker per packet. Your "
    "own working directory never changes and is NOT the worktree — "
    "never edit files there yourself. Create this packet's required "
    "artifacts in the session worktree, run relevant checks there, then "
    "stop. Never modify graph truth or runtime databases. Leave changes "
    "as ordinary git working-tree edits — do not commit and do not "
    "push; the runtime persists this packet's result after you stop. A "
    "failure or cancellation on one packet must never stop you from "
    "finishing later packets in this session."
)


class PiRpcAdapter:
    """Drive NodePacket turns over one durable, per-project `pi --mode rpc` session."""

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
        idle_timeout_s: float | None = None,
        resume_session_file: str | Path | None = None,
    ) -> None:
        self.repo = repo
        self.spool_root = _configured_spool_root(spool_root)
        configured_cwd = cwd if cwd is not None else os.environ.get("GDDP_PI_RPC_CWD")
        self.cwd = Path(configured_cwd).resolve() if configured_cwd else None
        # No default model. A silent fallback here is invisible at the call
        # site, so an operator's chosen (cheap) model can be overridden by a
        # constant in this file without anyone noticing.
        resolved_model = model or os.environ.get(_MODEL_ENV)
        if not resolved_model:
            raise ValueError(
                "pi_rpc model is required: pass model= explicitly or set "
                f"{_MODEL_ENV}"
            )
        self.model = resolved_model
        self.pi_binary = pi_binary or os.environ.get(_BINARY_ENV) or "pi"
        self.tools = tools or os.environ.get(_TOOLS_ENV) or _DEFAULT_TOOLS
        if turn_timeout_s is not None:
            self.turn_timeout_s = float(turn_timeout_s)
        else:
            self.turn_timeout_s = float(
                os.environ.get(_TIMEOUT_ENV, str(_DEFAULT_TIMEOUT_S))
            )
        if idle_timeout_s is not None:
            self.idle_timeout_s = float(idle_timeout_s)
        else:
            self.idle_timeout_s = float(
                os.environ.get(_IDLE_TIMEOUT_ENV, str(_DEFAULT_IDLE_TIMEOUT_S))
            )
        self.resume_session_file = (
            Path(resume_session_file) if resume_session_file else None
        )

    def capabilities(self) -> ExecutorCapabilities:
        """Declared capabilities. Pure — safe in preflight, no live session.

        Evidence for each field: docs/proposals/executor-capability-contract.md
        §4. cancellation is COOPERATIVE, not preemptive: cancel() writes a
        marker and deliberately never signals, because this attempt's pid may
        be the shared per-project process. engagement is False, which is what
        supports_engagement() has always reported by omission.
        """
        return ExecutorCapabilities(
            executor=self.executor_name,
            streaming_events=True,
            partial_text=True,
            cancellation="cooperative",
            resume="session_file",
            midturn_steering=True,
            usage_reporting=True,
            native_subagents=True,
            structured_tool_calls=True,
        )

    def supports_engagement(self) -> bool:
        """Thin shim over the declaration so call sites keep working."""
        return self.capabilities().engagement

    def attempt_root(self) -> Path:
        """Root where the runtime reserves transport attempts."""
        return self.spool_root

    def dispatch(
        self,
        packet: NodePacket,
        *,
        attempt: AttemptContext,
        continuity: Continuity = FRESH,
    ) -> DispatchResult:
        if continuity.mode == "resume" and self.capabilities().resume == "none":
            raise CapabilityUnsupported("resume", self.executor_name)
        # Continuity is packet-scoped runtime policy. Ambient constructor
        # state must not turn an explicit fresh dispatch into a resumed one.
        resume_session_file = (
            Path(continuity.token)
            if continuity.mode == "resume" and continuity.token
            else None
        )

        session_id = attempt.attempt_id
        attempt_dir = attempt.attempt_dir
        supervisor: subprocess.Popen[bytes] | None = None
        try:
            execution_cwd = self.cwd
            if execution_cwd is None:
                # Fall back to the process cwd (dispatcher sets repo_path as cwd
                # for local transports). This becomes the orchestrator session's
                # own cwd — never the session worktree (see _PACKET_PREAMBLE).
                execution_cwd = Path.cwd()
            project_key = _safe_component(packet.project_id or self.repo or "default")
            orchestrator_dir = self.spool_root / "_orchestrators" / project_key

            config = {
                "pi_binary": self.pi_binary,
                "model": self.model,
                "tools": self.tools,
                "turn_timeout_s": self.turn_timeout_s,
                "idle_timeout_s": self.idle_timeout_s,
                "repo_cwd": str(execution_cwd),
                "orchestrator_dir": str(orchestrator_dir),
                "resume_session_file": (
                    str(resume_session_file) if resume_session_file else None
                ),
            }
            (attempt_dir / "command.json").write_text(
                json.dumps(config, sort_keys=True, separators=(",", ":"))
            )

            orchestrator_dir.mkdir(parents=True, exist_ok=True)
            with _orchestrator_lock(orchestrator_dir):
                live_pid = _read_pid(orchestrator_dir / "pid")
                if live_pid is not None and _pid_is_running(live_pid):
                    # A session for this project is already live (idle or
                    # mid-turn) — queue behind it instead of spawning a
                    # second `pi` process for the same project.
                    _enqueue_attempt(orchestrator_dir, attempt_dir)
                    _atomic_write(attempt_dir / "supervisor.pid", str(live_pid))
                else:
                    # Enqueue BEFORE spawning: the orchestrator's first act
                    # is an inbox claim, so this guarantees it always finds
                    # its first job instead of racing an empty inbox.
                    _enqueue_attempt(orchestrator_dir, attempt_dir)
                    supervisor = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "adapters.pi_rpc_adapter",
                            "--run-orchestrator",
                            str(orchestrator_dir),
                        ],
                        cwd=str(Path(__file__).resolve().parents[1]),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    _atomic_write(orchestrator_dir / "pid", str(supervisor.pid))
                    _atomic_write(attempt_dir / "supervisor.pid", str(supervisor.pid))
                    # Fire-and-forget spawn: nobody else ever calls .wait() on
                    # this Popen. Without reaping it in the background, an
                    # exited orchestrator sits as a zombie under whichever
                    # process called dispatch() until THAT process exits —
                    # and os.kill(pid, 0) reports zombies as alive, which
                    # would make a later dispatch() for this project wrongly
                    # enqueue into a dead orchestrator instead of spawning a
                    # fresh one. Reap it the moment it exits, regardless of
                    # how long the calling process itself stays up.
                    threading.Thread(target=supervisor.wait, daemon=True).start()
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

        return DispatchResult(
            success=True,
            session_ref=SessionRef(executor=self.executor_name, session_id=session_id),
        )

    def status(self, session_ref: SessionRef) -> SessionStatus:
        attempt_dir = self._attempt_dir(session_ref)
        if attempt_dir is None or not attempt_dir.is_dir():
            return read_pi_rpc_status(self.spool_root, session_ref.session_id)
        return read_pi_rpc_status_from_dir(attempt_dir)

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
        # That is the whole action. Under batch turns (fork A item 4) this
        # attempt's `pid` file may equal the SAME shared pi process running
        # up to N-1 other packets in the same turn right now — there is no
        # per-packet abort in the RPC protocol, so we never signal or kill
        # that process here. _run_one_turn checks this marker for THIS
        # attempt_dir twice: once before the packet is ever sent to pi
        # (skips it, never sends it to pi) and once more right before
        # persisting its result (skips persist). The session worktree and
        # every other packet stay up either way.
        return True

    def _attempt_dir(self, session_ref: SessionRef) -> Path | None:
        if session_ref.executor != self.executor_name:
            return None
        return locate_attempt_dir(
            session_ref.session_id,
            spool_root=self.spool_root,
            recorded_dir=session_ref.attempt_dir,
        )


def read_pi_rpc_status_from_dir(attempt_dir: Path) -> SessionStatus:
    """Read-only durable status from one resolved pi_rpc attempt directory."""
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
        # Covers both "a fresh orchestrator is starting up" (legacy per-
        # attempt meaning) and, under fork A, "queued in a live project
        # orchestrator's inbox, turn not started yet."
        return SessionStatus(state="dispatched")
    return SessionStatus(
        state="failed",
        error="pi_rpc exited without durable exit state",
    )


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
    return read_pi_rpc_status_from_dir(attempt_dir)


# ---------------------------------------------------------------------------
# Orchestrator (--run-orchestrator): one long-lived pi session per project
# ---------------------------------------------------------------------------


def _observability_env(
    packet: dict, env_file: Path | None = None
) -> dict[str, str]:
    """Child env for the pi-observability extension, tagged per PROJECT.

    The extension loads globally via ~/.pi/agent/settings.json. Without
    OBS_* it defaults to localhost with no token and spams post_failed
    into the session stream. Token stays in env, never argv. Returns an
    empty dict when the fleet client is not configured (feature off).

    Fork A + batch turns: the orchestrator process (and its env) now lives
    across many packets, and a single turn may itself cover several nodes
    at once. A per-node tag fixed once at process spawn (env cannot change
    on a running child) was never going to stay true past the first
    packet or the first turn — that staleness is not fixed here by trying
    to mutate env later; it is removed by dropping node/job/attempt from
    this env entirely. OBS_NAME/OBS_TAG identify the PROJECT-level session
    only (gddp-<project_id>); per-node identity belongs on the worker
    subagent sessions the orchestrator dispatches into each worktree,
    which can express it truthfully turn over turn in a way this parent
    env cannot.
    """
    env_file = env_file or (Path.home() / ".config" / "pi-observability" / "env")
    obs: dict[str, str] = {}
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or not line.startswith("export "):
                continue
            key, _, value = line[len("export "):].partition("=")
            obs[key.strip()] = value.strip().strip("'").strip('"')
    except OSError:
        return {}
    if not obs.get("OBS_SERVER_URL"):
        return {}
    project_id = str(packet.get("project_id") or "unknown")
    tags = [
        f"host:{socket.gethostname().split('.')[0]}",
        "gddp",
        f"project:{project_id}",
    ]
    obs["OBS_POOL"] = "gddp"
    obs["OBS_NAME"] = f"gddp-{project_id}"
    obs["OBS_TAG"] = ",".join(tags)
    return obs


def build_executor_turn_prompt(*, worktree: Path, packets: Sequence[dict]) -> TurnPrompt:
    """Four-zone TurnPrompt for one pi orchestrator turn.

    Zone assembly is shared (session_prompt.build_turn_prompt); what is pi's
    own is the protocol zone and the turn note, both of which describe pi's
    subagent fan-out. The rendered bytes are unchanged.
    """
    return build_turn_prompt(
        worktree=worktree,
        packets=packets,
        preamble=_PACKET_PREAMBLE,
        turn_note=(
            f"### TURN — {len(packets)} packet(s) on the session worktree "
            f"{worktree}. Worker-subagent count is the step-2 cap, not one "
            "per packet."
        ),
    )


def _assemble_turn_prompt(*, worktree: Path, packets: Sequence[dict]) -> str:
    """Assemble the executor turn prompt as text (backward-compat shim).

    Prefer ``build_executor_turn_prompt`` when you need the TurnPrompt object
    (e.g. to compute a prompt_cache_report). This keeps the existing string
    contract for tests and the RPC send path.
    """
    return build_executor_turn_prompt(worktree=worktree, packets=packets).assemble()


@dataclass(frozen=True)
class _TurnOutcome:
    """Result of persisting exactly one NodePacket's slot within a (possibly
    batched) turn on a live pi session."""

    attempt_dir: Path
    returncode: int
    plumbing: bool
    cancelled: bool
    error: str | None


def _run_one_turn(
    *,
    attempt_dirs: list[Path],
    proc: subprocess.Popen[str],
    client: "_RpcClient",
    worktree: Path,
    turn_timeout_s: float,
    load_packet: Callable[[str], dict],
    persist_result: Callable[[Path, dict], dict],
    record_worktree_correlation: Callable[[Path, dict], None],
    repo: Path | None = None,
) -> tuple[list[_TurnOutcome], bool]:
    """Run ONE RPC turn against an already-running pi session on the
    session-owned worktree. Caller should pass one attempt_dir so
    persist_result is one node commit; a list is still accepted so a
    pre-cancelled packet can be skipped without a prompt.

    Returns (outcomes, terminate_session). Only a pi-health failure
    (dead process, broken protocol, timed out waiting for agent_end)
    sets terminate_session=True. A persist failure or operator cancel
    is scoped to that packet — the session and its worktree stay up.
    """
    outcomes: dict[Path, _TurnOutcome] = {}
    # (attempt_dir, packet dict, raw packet json) for every packet that
    # actually makes it into this turn's prompt.
    active: list[tuple[Path, dict, str]] = []

    for attempt_dir in attempt_dirs:
        cancel_path = attempt_dir / "cancel.requested"
        if cancel_path.exists():
            error = "cancelled before this packet's turn started"
            _write_exit(attempt_dir, returncode=130, cancelled=True, plumbing=False, error=error)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 130, False, True, error)
            continue
        try:
            packet_raw = (attempt_dir / "packet.json").read_text()
            packet = load_packet(packet_raw)
        except Exception as exc:
            error = f"pi_rpc packet load failed: {exc}"
            _write_exit(attempt_dir, returncode=1, cancelled=False, plumbing=True, error=error)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 1, True, False, error)
            continue
        record_worktree_correlation(worktree, packet)
        (attempt_dir / "worktree_path").write_text(str(worktree))
        active.append((attempt_dir, packet, packet_raw))

    if not active:
        # Every packet in this batch was pre-cancelled or failed setup in
        # isolation. No RPC round needed; the session is untouched and
        # stays healthy for the caller's next claim.
        return [outcomes[d] for d in attempt_dirs], False

    n = len(active)

    # Operator steer channel: `gddp steer` appends lines to steer.jsonl in
    # an attempt dir; the drain below runs on the client's single reader
    # thread (via on_poll) and delivers each message as an RPC prompt.
    # Plain lines are accepted as raw message text; JSON objects take
    # their "message" field. A batch turn drains EVERY active packet's own
    # steer.jsonl, tagging each delivered message with which packet it
    # came from so the operator can steer any node in the batch.
    steer_state: dict[Path, dict[str, int]] = {
        attempt_dir: {"offset": 0, "sent": 0} for attempt_dir, _packet, _raw in active
    }

    def _drain_steer(kind: str = "steer") -> None:
        # kind="steer": native RPC steer — delivered into the running turn
        # (accepted mid-turn, consumed before agent_end). kind="prompt":
        # used after agent_end while idle; starts a follow-up turn the
        # caller waits on. A bare "prompt" mid-turn is REJECTED by pi —
        # never use it for mid-turn delivery.
        for attempt_dir, _packet, _raw in active:
            state = steer_state[attempt_dir]
            steer_path = attempt_dir / "steer.jsonl"
            messages, state["offset"] = _read_steer_messages(steer_path, state["offset"])
            for msg in messages:
                try:
                    resp = client.send(
                        {
                            "type": kind,
                            "message": f"[operator steer for {attempt_dir.name}] {msg}",
                        },
                        timeout=30.0,
                    )
                except Exception as exc:  # delivery failure must not kill the turn
                    (attempt_dir / "steer.error.txt").write_text(str(exc))
                    continue
                if resp and resp.get("success"):
                    if kind == "prompt":
                        state["sent"] += 1
                else:
                    (attempt_dir / "steer.error.txt").write_text(
                        f"{kind} rejected: {resp}"
                    )

    # Per-turn spool, on the one long-lived client's reader loop. The first
    # active attempt is the live target; its full event stream (including
    # this turn's agent_end) is copied to every other active attempt below
    # once the turn ends, since it is the SAME shared turn.
    client.begin_turn(active[0][0], turn_id=uuid.uuid4().hex)

    turn_packets = [packet for _attempt_dir, packet, _packet_raw in active]
    tp = build_executor_turn_prompt(worktree=worktree, packets=turn_packets)
    # The pointers this turn's project zone actually offered — the offered set
    # coverage is measured against below.
    turn_pointers = merged_turn_pointers(turn_packets)
    prompt = tp.assemble()
    # Structural cache report: how much of this turn's prompt is reusable
    # prefix vs volatile tail. Persisted into the result handoff so it flows
    # through the operator loop as node evidence, not a side dashboard.
    # `actual_cached_tokens` is wired later from the provider usage feed
    # (events.jsonl / OpenRouter); today this is the potential-reuse ceiling
    # and the per-zone token breakdown.
    cache_report = prompt_cache_report(tp).as_dict()
    for attempt_dir, _packet, _raw in active:
        _atomic_write(
            attempt_dir / "prompt_cache_report.json",
            json.dumps(cache_report, sort_keys=True, separators=(",", ":")),
        )

    plumbing = False
    turn_error: str | None = None
    try:
        client.prompt_and_wait_agent_end(
            prompt, timeout=turn_timeout_s, on_poll=_drain_steer
        )
        # Operator steers sent mid-turn are consumed by the running turn.
        # Steers that arrive after agent_end are sent as fresh prompts
        # (session idle), each producing a follow-up turn; keep collecting
        # until a full agent_end passes with no new operator input across
        # every packet in the batch. Bounded against a steer storm.
        for _ in range(_MAX_STEER_FOLLOWUPS):
            _drain_steer("prompt")
            total_sent = sum(state["sent"] for state in steer_state.values())
            if total_sent == 0 or proc.poll() is not None:
                break
            for state in steer_state.values():
                state["sent"] = 0
            client.wait_agent_end(timeout=turn_timeout_s, on_poll=_drain_steer)
    except _PlumbingError as exc:
        plumbing = True
        turn_error = str(exc)
    except Exception as exc:
        # Turn may have completed with a non-zero agent outcome — still
        # try to persist whatever is in the session worktree below rather
        # than treating the whole session as unhealthy.
        turn_error = str(exc)
        if proc.poll() is None:
            try:
                client.send({"type": "abort"}, wait_response=False)
            except Exception:
                pass

    if not client.translator.saw_turn_end:
        # pi reported no turn boundary: the process died, the protocol broke,
        # or the operator cancelled. The canonical stream says so explicitly
        # rather than just stopping.
        client.emit_turn_ended(
            status=(
                "cancelled"
                if (active[0][0] / "cancel.requested").exists()
                else "failed"
            ),
            error=turn_error,
        )

    turn_events = list(client.turn_events)

    if n > 1:
        # Same shared turn, so every packet in the batch gets the same spool.
        for name in ("events.jsonl", "raw.jsonl"):
            try:
                shared = (active[0][0] / name).read_bytes()
            except OSError:
                continue
            for attempt_dir, _packet, _raw in active[1:]:
                try:
                    (attempt_dir / name).write_bytes(shared)
                except OSError:
                    pass

    for attempt_dir, packet, _packet_raw in active:
        if plumbing:
            _write_exit(attempt_dir, returncode=1, cancelled=False, plumbing=True, error=turn_error)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 1, True, False, turn_error)
            continue

        cancel_path = attempt_dir / "cancel.requested"
        if cancel_path.exists():
            cancel_error = "cancelled during this packet's turn"
            _write_exit(attempt_dir, returncode=130, cancelled=True, plumbing=False, error=cancel_error)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 130, False, True, cancel_error)
            continue

        handoff = persist_result(worktree, packet)
        # Evidence from THIS turn's canonical events. Both measurements below
        # are strictly best-effort: the node's result is already persisted
        # above and must not turn on a measurement.
        report_path = attempt_dir / "prompt_cache_report.json"
        # Cached tokens the provider reported for this turn, summed across
        # its per-message usage records. Streaming updates cannot reach this
        # number any more — they never become canonical usage events — so it
        # no longer inflates on a turn where a delta happened to carry usage
        # (docs/proposals/executor-event-vocabulary.md §1.2).
        try:
            usage = turn_usage(turn_events)
            if usage is not None and usage.cached_input_tokens is not None:
                _atomic_write(
                    report_path,
                    json.dumps(
                        prompt_cache_report(
                            tp, actual_cached_tokens=usage.cached_input_tokens
                        ).as_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
        except OSError:
            pass

        # Which of the pointers the project zone offered were actually
        # opened, plus the read paths that were never offered. Makes
        # orchestrator context growth observable per turn instead of
        # reconstructed from session logs afterwards.
        try:
            coverage = compute_turn_context_coverage(
                pointers=turn_pointers, events=turn_events, base=repo
            )
            if coverage is not None:
                _atomic_write(
                    attempt_dir / "context_coverage.json",
                    json.dumps(coverage, sort_keys=True, separators=(",", ":")),
                )
        except Exception:
            pass

        # Attach the structural cache report (now with actual_cached_tokens if present)
        # so it flows through collect() -> the operator loop as part of the node's evidence.
        if report_path.exists():
            try:
                handoff["prompt_cache_report"] = json.loads(report_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass
        (attempt_dir / "result.json").write_text(
            json.dumps(handoff, sort_keys=True, separators=(",", ":"))
        )
        if handoff.get("result_commit_sha"):
            _write_exit(attempt_dir, returncode=0, cancelled=False, plumbing=False, error=None)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 0, False, False, None)
        else:
            persist_error = str(handoff.get("error") or "persist failed")
            _write_exit(attempt_dir, returncode=1, cancelled=False, plumbing=False, error=persist_error)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 1, False, False, persist_error)

    return [outcomes[d] for d in attempt_dirs], plumbing


def run_orchestrator(orchestrator_dir: Path) -> int:
    """Persistent per-project loop: claim packets from an inbox and run each
    as an RPC turn against one long-lived `pi --mode rpc` process and ONE
    session worktree.

    Exits (and kills pi, then removes the session worktree) only on idle
    timeout or a pi-health plumbing failure — never unconditionally after
    a turn, and never because one packet was cancelled or failed to persist.
    """
    from local_agent_executor import (  # noqa: PLC0415 - scripts/ on path
        create_worktree,
        load_packet,
        persist_result,
        record_worktree_correlation,
        remove_worktree,
    )

    first_batch = _claim_ready_set(orchestrator_dir)
    if not first_batch:
        return 2

    config = json.loads((first_batch[0] / "command.json").read_text())
    repo = Path(config["repo_cwd"]).resolve()
    model = str(config["model"])
    tools = str(config["tools"])
    pi_binary = str(config["pi_binary"])
    turn_timeout_s = float(config.get("turn_timeout_s") or _DEFAULT_TIMEOUT_S)
    idle_timeout_s = float(config.get("idle_timeout_s") or _DEFAULT_IDLE_TIMEOUT_S)
    resume_session = config.get("resume_session_file")

    session_dir = orchestrator_dir / "pi-session"
    session_dir.mkdir(parents=True, exist_ok=True)

    proc: subprocess.Popen[str] | None = None
    active_attempt_dirs: list[Path] | None = first_batch
    session_worktree: Path | None = None

    def _kill_pi() -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass

    def _drain_inbox(reason: str, *, plumbing: bool, cancelled: bool) -> None:
        # Anything still queued when the session dies must not hang in
        # "dispatched" forever — fail it out now so the reconciler's
        # existing plumbing-retry path picks it up on the next tick.
        while True:
            pending = _claim_ready_set(orchestrator_dir)
            if not pending:
                return
            for attempt_dir in pending:
                _write_exit(
                    attempt_dir, returncode=1, cancelled=cancelled, plumbing=plumbing, error=reason
                )

    try:
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

        first_packet_dict = json.loads((first_batch[0] / "packet.json").read_text())

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(repo),
            env={**os.environ, **_observability_env(first_packet_dict)},
            start_new_session=True,
        )

        # Settle + readiness probe (matches spike).
        time.sleep(0.4)
        if proc.poll() is not None:
            err = proc.stderr.read() if proc.stderr else ""
            reason = f"pi exited immediately ({proc.returncode}): {err[:500]}"
            for attempt_dir in first_batch:
                _write_exit(
                    attempt_dir, returncode=proc.returncode or 1,
                    cancelled=False, plumbing=True, error=reason,
                )
            active_attempt_dirs = None
            _drain_inbox(reason, plumbing=True, cancelled=False)
            return proc.returncode or 1

        # Bootstrap spool: the get_state exchange happens before any packet's
        # turn, so its events land in the orchestrator dir. begin_turn
        # repoints the writer at each attempt dir from there on.
        client = _RpcClient(
            proc,
            writer=EventWriter(
                orchestrator_dir,
                executor=_EXECUTOR,
                session_id="",
                turn_id="bootstrap",
            ),
        )
        session_file_value: str | None = None
        try:
            state = client.get_state()
            session_file_value = state.get("sessionFile") or state.get("session_file")
        except Exception as exc:
            # Non-fatal: some builds emit bootstrap noise first.
            (orchestrator_dir / "get_state_error.txt").write_text(str(exc))

        ready: list[Path] = []
        for attempt_dir in first_batch:
            if (attempt_dir / "cancel.requested").exists():
                error = "cancelled before this packet's turn started"
                _write_exit(
                    attempt_dir, returncode=130, cancelled=True, plumbing=False, error=error
                )
                continue
            try:
                packet = load_packet((attempt_dir / "packet.json").read_text())
            except Exception as exc:
                error = f"pi_rpc packet load failed: {exc}"
                _write_exit(
                    attempt_dir, returncode=1, cancelled=False, plumbing=True, error=error
                )
                continue
            if session_worktree is None:
                try:
                    session_worktree = create_worktree(
                        repo, str(packet["expected_base_commit_sha"])
                    )
                    record_worktree_correlation(session_worktree, packet)
                    _atomic_write(orchestrator_dir / "worktree_path", str(session_worktree))
                except Exception as exc:
                    error = f"pi_rpc worktree setup failed: {exc}"
                    _write_exit(
                        attempt_dir, returncode=1, cancelled=False, plumbing=True, error=error
                    )
                    continue
            ready.append(attempt_dir)

        if session_worktree is None:
            _drain_inbox(
                "pi_rpc session worktree setup failed", plumbing=True, cancelled=False
            )
            return 1

        batch: list[Path] | None = ready or None
        while batch is not None:
            for attempt_dir in batch:
                active_attempt_dirs = [attempt_dir]
                _atomic_write(orchestrator_dir / "state", "busy")
                _atomic_write(orchestrator_dir / "current_attempt", str(attempt_dir))
                _atomic_write(attempt_dir / "pid", str(proc.pid))
                if session_file_value:
                    _atomic_write(attempt_dir / "session_file", str(session_file_value))

                outcomes, terminate_session = _run_one_turn(
                    attempt_dirs=[attempt_dir],
                    proc=proc,
                    client=client,
                    worktree=session_worktree,
                    turn_timeout_s=turn_timeout_s,
                    load_packet=load_packet,
                    persist_result=persist_result,
                    record_worktree_correlation=record_worktree_correlation,
                    repo=repo,
                )
                active_attempt_dirs = None

                if terminate_session:
                    plumbing_outcome = next((o for o in outcomes if o.plumbing), None)
                    reason = (
                        (plumbing_outcome.error if plumbing_outcome else None)
                        or "session terminated"
                    )
                    returncode = plumbing_outcome.returncode if plumbing_outcome else 1
                    _drain_inbox(reason, plumbing=True, cancelled=False)
                    return returncode

            _atomic_write(orchestrator_dir / "state", "idle")
            batch = _claim_ready_set(orchestrator_dir) or None
            if batch is None:
                deadline = time.time() + idle_timeout_s
                while batch is None and time.time() < deadline:
                    time.sleep(_INBOX_POLL_S)
                    batch = _claim_ready_set(orchestrator_dir) or None
                if batch is None:
                    # Final check happens under the SAME lock dispatch()
                    # takes before enqueuing, closing the race where a
                    # packet lands just as this loop decides to exit: one
                    # side or the other wins the lock and sees a
                    # consistent world (either the new item(s), or a pid
                    # file that is already gone).
                    with _orchestrator_lock(orchestrator_dir):
                        batch = _claim_ready_set(orchestrator_dir) or None
                        if batch is None:
                            with contextlib.suppress(OSError):
                                (orchestrator_dir / "pid").unlink()
        return 0
    except Exception as exc:
        reason = f"pi_rpc orchestrator failed: {exc}"
        if active_attempt_dirs:
            for attempt_dir in active_attempt_dirs:
                if not (attempt_dir / "exit.json").exists():
                    _write_exit(
                        attempt_dir, returncode=1, cancelled=False, plumbing=True, error=reason
                    )
        _drain_inbox(reason, plumbing=True, cancelled=False)
        return 1
    finally:
        _kill_pi()
        if session_worktree is not None:
            with contextlib.suppress(Exception):
                remove_worktree(repo, session_worktree)
        with contextlib.suppress(OSError):
            (orchestrator_dir / "pid").unlink()
            (orchestrator_dir / "worktree_path").unlink()
        _atomic_write(orchestrator_dir / "state", "exited")


class _PlumbingError(RuntimeError):
    """Process died or protocol broke before a durable agent_end."""


class _RpcClient:
    """One long-lived pi RPC process, plus the canonical spool it writes.

    Every line pi emits goes verbatim to ``raw.jsonl`` and, when it maps onto
    the canonical vocabulary, to ``events.jsonl`` as an ExecutorEvent. The
    translator is session-scoped because the pi process is: it learns the
    session identity once from ``get_state`` and keeps it across turns.
    ``begin_turn`` repoints the writer at the attempt dir whose turn is about
    to run, which is what makes a pi attempt's spool mean the same thing as a
    cursor attempt's.
    """

    def __init__(self, proc: subprocess.Popen[str], *, writer: EventWriter):
        self.proc = proc
        self.writer = writer
        self.translator = PiStreamTranslator()
        # This turn's canonical events, in emission order. Held in memory so
        # the post-turn evidence pass reads exactly the turn it just ran,
        # with no byte-offset windowing into a file other turns also append
        # to.
        self.turn_events: list[ExecutorEvent] = []
        self._req = 0
        self._lock = threading.Lock()
        # Raw-fd line buffer. Never mix select() with buffered TextIOWrapper
        # reads: readline() can pull several JSONL records into the wrapper's
        # buffer in one syscall, leaving later records invisible to select
        # (fd looks empty) — the reader then waits forever with complete
        # events stranded in userspace.
        assert self.proc.stdout is not None
        self._fd = self.proc.stdout.fileno()
        self._buf = b""

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

    def prompt_and_wait_agent_end(
        self, message: str, *, timeout: float, on_poll: Callable[[], None] | None = None
    ) -> None:
        resp = self.send({"type": "prompt", "message": message}, timeout=min(60.0, timeout))
        if not resp or not resp.get("success"):
            # Some builds accept via event stream only; tolerate missing success
            # if the process is still alive and we can wait for agent_end.
            if self.proc.poll() is not None:
                raise _PlumbingError(f"prompt rejected and process dead: {resp}")
        self.wait_agent_end(timeout=timeout, on_poll=on_poll)

    def wait_agent_end(
        self, *, timeout: float, on_poll: Callable[[], None] | None = None
    ) -> None:
        """Wait for the next agent_end. on_poll runs each read cycle so the
        caller can inject operator input from the single reader thread."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if on_poll is not None:
                on_poll()
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

    def _pop_line(self) -> str | None:
        idx = self._buf.find(b"\n")
        if idx < 0:
            return None
        line = self._buf[:idx]
        self._buf = self._buf[idx + 1 :]
        return line.decode("utf-8", errors="replace")

    def _read_one(self, *, timeout: float) -> dict | None:
        line = self._pop_line()
        if line is None:
            ready, _, _ = select.select([self._fd], [], [], timeout)
            if not ready:
                return None
            chunk = os.read(self._fd, 65536)
            if not chunk:
                return None
            self._buf += chunk
            line = self._pop_line()
            if line is None:
                return None
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"type": "_non_json", "raw": line[:500]}

    def begin_turn(self, attempt_dir: Path, *, turn_id: str) -> None:
        """Point the spool at one attempt's turn and start a fresh seq.

        Emits ``session_started`` so every attempt's canonical stream is
        self-describing — the identity was learned once, out-of-band, at
        orchestrator startup, and an attempt spool that never saw that
        exchange would otherwise carry no session or resume handle at all.
        """
        self.translator.begin_turn()
        self.turn_events = []
        self.writer = EventWriter(
            attempt_dir,
            executor=_EXECUTOR,
            session_id=self.translator.session_id or "",
            turn_id=turn_id,
        )
        if self.translator.session_id or self.translator.resume_token:
            self._emit(
                "session_started",
                raw_type="",
                model=self.translator.model,
                resume_token=self.translator.resume_token,
            )

    def emit_turn_ended(self, *, status: str, error: str | None) -> None:
        """Terminal record for a turn pi never closed.

        pi emits nothing when its process dies mid-turn and nothing when the
        operator cancels, so the boundary those turns get is the one the
        driver already knows about from the outcome it is writing to
        exit.json.
        """
        self._emit("turn_ended", raw_type="", status=status, error=error)

    def _emit(self, type: str, *, raw_type: str = "", **fields: object) -> None:
        try:
            self.turn_events.append(
                self.writer.emit(type, raw_type=raw_type, **fields)  # type: ignore[arg-type]
            )
        except OSError:
            pass

    def _record(self, evt: dict) -> None:
        """Verbatim to raw.jsonl, canonical to events.jsonl.

        Recording is observability: a failure here must never end a turn that
        is otherwise healthy, which is why the whole path is best-effort.
        """
        try:
            self.writer.raw(json.dumps(evt, separators=(",", ":")))
        except OSError:
            pass
        try:
            for translated in self.translator.translate(evt):
                self._emit(
                    translated.type,
                    raw_type=translated.raw_type,
                    **translated.fields,
                )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


# Operator steer channel bounds: max queued follow-up turns collected per
# attempt (each steer turn runs with the full turn timeout).
_MAX_STEER_FOLLOWUPS = 10

# Orchestrator idle-wait inbox poll cadence.
_INBOX_POLL_S = 0.3


def _read_steer_messages(path: Path, offset: int) -> tuple[list[str], int]:
    """Read new steer lines from path at byte offset.

    Returns (messages, new_offset). JSON lines take their "message" field;
    anything else is treated as raw message text. Pure file IO — testable
    without a live pi process.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return [], offset
    if size <= offset:
        return [], offset
    messages: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("{"):
                try:
                    msg = json.loads(stripped).get("message")
                except json.JSONDecodeError:
                    msg = None
                if isinstance(msg, str) and msg.strip():
                    messages.append(msg.strip())
            else:
                messages.append(stripped)
        return messages, handle.tell()
    return messages, offset


@contextlib.contextmanager
def _orchestrator_lock(orchestrator_dir: Path):
    """Exclusive file lock serializing claim/spawn/idle-exit decisions for
    one project's orchestrator across threads and processes.

    Self-healing: flock is released by the OS if a holder crashes without
    reaching the `finally` (fd closes on process exit), so a dead holder
    never wedges a project's dispatch path.
    """
    orchestrator_dir.mkdir(parents=True, exist_ok=True)
    lock_path = orchestrator_dir / "lock"
    with open(lock_path, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _enqueue_attempt(orchestrator_dir: Path, attempt_dir: Path) -> None:
    """Queue one packet's attempt_dir for the project's orchestrator loop.

    Caller must hold _orchestrator_lock. Filename is time-ordered so
    _claim_ready_set drains in FIFO order.
    """
    inbox = orchestrator_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    marker = inbox / f"{time.time_ns():020d}-{attempt_dir.name}"
    _atomic_write(marker, str(attempt_dir))


def _claim_ready_set(orchestrator_dir: Path) -> list[Path]:
    """Drain EVERY currently-queued attempt_dir, oldest first, as a list.

    A turn carries every packet sitting in the inbox at the moment it is
    claimed, not just the oldest one, so concurrent ready nodes share one
    orchestrator turn instead of waiting in series. Packets that land in
    the inbox AFTER this snapshot is taken queue for the next call.

    Single-consumer (only the owning orchestrator loop calls this outside
    the lock-protected idle-exit check), so no lock is needed here.
    """
    inbox = orchestrator_dir / "inbox"
    try:
        entries = sorted(p for p in inbox.iterdir() if ".tmp." not in p.name)
    except OSError:
        return []
    claimed: list[Path] = []
    for entry in entries:
        try:
            text = entry.read_text().strip()
            entry.unlink()
        except OSError:
            continue
        if text:
            claimed.append(Path(text))
    return claimed


def _write_exit(
    attempt_dir: Path, *, returncode: int, cancelled: bool, plumbing: bool, error: str | None
) -> None:
    exit_state = {
        "returncode": returncode,
        "cancelled": cancelled,
        "plumbing": plumbing,
        "error": error,
    }
    _atomic_write(
        attempt_dir / "exit.json",
        json.dumps(exit_state, sort_keys=True, separators=(",", ":")),
    )


def _configured_spool_root(spool_root: str | Path | None) -> Path:
    return resolve_attempt_spool_root(spool_root, legacy_env=_SPOOL_ENV)


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
    if len(argv) >= 2 and argv[0] == "--run-orchestrator":
        return run_orchestrator(Path(argv[1]))
    print(
        "usage: python -m adapters.pi_rpc_adapter --run-orchestrator DIR",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
