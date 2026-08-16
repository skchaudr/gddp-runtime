"""Persistent Pi executor via `pi --mode rpc` (JSONL stdin/stdout).

Verified transport (scripts/runtime/spike/pi_rpc_persistent_spike.py):
  - Turn boundary event: agent_end
  - Resume after process death: --session <sessionFile>
  - Multi-turn context survives in one process / session file

Fork A (2026-08-16): one long-lived `pi --mode rpc` process is spawned PER
PROJECT, not per node. dispatch() drops each NodePacket into that project's
"orchestrator" inbox; a single background loop (run_orchestrator) claims
EVERY packet currently queued (not just the oldest one) and runs them as
ONE shared RPC turn: one prompt, one agent_end, N NodePackets fanned out to
N top-level subagents inside pi, each pointed at its own git worktree
created at that packet's own base commit (_claim_ready_set / _run_one_turn).
Packets that arrive mid-turn queue for the NEXT turn; they are never
injected into a running one. A project's effective fan-out is however many
packets happen to be queued together when a turn starts — execution_policy
(max_concurrent_jobs) is not currently plumbed down to this adapter, see
the fan-out-ceiling comment in _run_one_turn. The orchestrator's own cwd is
the repo root; per-node isolation moves inside the session as a worktree
each packet's subagent is pointed at via the prompt (see _PACKET_PREAMBLE
and the per-packet worktree_path lines built in _run_one_turn).

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
_IDLE_TIMEOUT_ENV = "GDDP_PI_RPC_IDLE_TIMEOUT_S"
_DEFAULT_MODEL = "xai/grok-4.5"
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
    "You are the ORCHESTRATOR of this attempt, not the implementer. Doing "
    "the node's investigation, construction, or measurement work directly "
    "is a protocol violation.\n\n"
    "Operating protocol:\n"
    "1. Read the packet, then decompose the goal into bounded tasks.\n"
    "2. Dispatch worker subagents to perform the work: up to 5 concurrent, "
    "model xai/grok-4.6 via the subagent tool's model parameter. Workers "
    "investigate, build, and measure; you do not.\n"
    "3. While work is in flight, dispatch ONE watcher subagent (model "
    "deepseek/deepseek-v4-flash) that actively polls state with tools and "
    "reports changes. Never spend your own turns on sleep loops or polling "
    "scripts.\n"
    "4. Integrate worker returns into the required artifacts yourself. "
    "Integration, synthesis, and small edits are yours; bulk work is not.\n"
    "5. Close with parallel reviewer subagents (model "
    "deepseek/deepseek-v4-pro), each assigned a different explicit focus "
    "(criteria coverage, evidence integrity, constraint compliance). "
    "Resolve their findings before finishing.\n\n"
    "This session is long-lived and handles one project across many "
    "packets. A turn may carry more than one packet at once — when it "
    "does, treat the operating protocol above as the job of a PER-PACKET "
    "subagent, not your own: for each packet below, dispatch one top-level "
    "subagent (model xai/grok-4.6) as that packet's own orchestrator, "
    "handing it only that packet's JSON and instructing it to run steps "
    "1-5 above scoped to that packet alone, up to the fan-out ceiling "
    "stated below. Your own working directory never changes and is NOT a "
    "worktree — never edit files there yourself, and never do a packet's "
    "own work directly no matter how many packets this turn carries. Each "
    "packet's trailing lines name its own worktree_path, already created "
    "at that packet's own base commit; the subagent for a packet must be "
    "pointed at that path and must read and edit only there — never in "
    "your own cwd, never in another packet's worktree from this same "
    "turn, and never in a worktree left over from a previous turn. Create "
    "each packet's required artifacts in its own worktree, run relevant "
    "checks there, then stop. Never modify graph truth or runtime "
    "databases. Leave your changes as ordinary git working-tree edits in "
    "each worktree — do not commit and do not push; the runtime persists "
    "each packet's result deterministically and independently after you "
    "stop. A failure or cancellation on one packet must never stop you "
    "from finishing the others."
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
        self.model = model or os.environ.get(_MODEL_ENV) or _DEFAULT_MODEL
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

    def dispatch(self, packet: NodePacket) -> DispatchResult:
        session_id = (
            f"{_safe_component(packet.job_id)}-"
            f"{_safe_component(packet.node_id)}-attempt-{packet.attempt_index}-"
            f"{uuid.uuid4().hex}"
        )
        attempt_dir = self.spool_root / session_id
        supervisor: subprocess.Popen[bytes] | None = None
        try:
            attempt_dir.mkdir(parents=True, exist_ok=False)
            execution_cwd = self.cwd
            if execution_cwd is None:
                # Fall back to the process cwd (dispatcher sets repo_path as cwd
                # for local transports). This becomes the orchestrator session's
                # own cwd — never a worktree (fork A: per-node isolation moves
                # inside the session; see _PACKET_PREAMBLE).
                execution_cwd = Path.cwd()
            (attempt_dir / "packet.json").write_text(packet.to_json())

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
                    str(self.resume_session_file)
                    if self.resume_session_file
                    else None
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
        # That is the whole action. Under batch turns (fork A item 4) this
        # attempt's `pid` file may equal the SAME shared pi process running
        # up to N-1 other packets in the same turn right now — there is no
        # per-packet abort in the RPC protocol, so we never signal or kill
        # that process here. _run_one_turn checks this marker for THIS
        # attempt_dir twice: once before the packet is ever sent to pi
        # (skips it, never spawns/sends anything for it) and once more
        # right before persisting its result (discards whatever the
        # worktree holds). Every other packet in the batch, and the shared
        # session itself, runs to completion undisturbed either way.
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
        # Covers both "a fresh orchestrator is starting up" (legacy per-
        # attempt meaning) and, under fork A, "queued in a live project
        # orchestrator's inbox, turn not started yet."
        return SessionStatus(state="dispatched")
    return SessionStatus(
        state="failed",
        error="pi_rpc exited without durable exit state",
    )


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
    only (gddp-<project_id>); per-node identity is carried instead by each
    subagent's own pi session reporting into the fleet hub (see the
    per-packet subagent framing in _PACKET_PREAMBLE / handoff 097), which
    can express it truthfully turn over turn in a way this parent env
    cannot.
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
    repo: Path,
    turn_timeout_s: float,
    create_worktree: Callable[[Path, str], Path],
    load_packet: Callable[[str], dict],
    persist_result: Callable[[Path, dict], dict],
    record_worktree_correlation: Callable[[Path, dict], None],
    remove_worktree: Callable[[Path, Path], None],
) -> tuple[list[_TurnOutcome], bool]:
    """Run ONE shared RPC turn against an already-running pi session,
    covering every packet in `attempt_dirs` at once: one prompt, one
    agent_end, N NodePackets fanned out to N top-level subagents inside
    pi, each in its own worktree.

    Returns (outcomes, terminate_session): `outcomes` has exactly one
    entry per input attempt_dir, same order. `terminate_session` is a
    single batch-level flag.

    Only a pi-health failure (dead process, broken protocol, timed out
    waiting for agent_end) sets terminate_session=True. A worktree-
    creation failure, a persist_result failure, or an operator cancel is
    scoped to that one packet's attempt_dir — the caller's loop keeps the
    session alive for the next queued packet regardless of how many
    packets in THIS batch failed or were cancelled.
    """
    outcomes: dict[Path, _TurnOutcome] = {}
    # (attempt_dir, packet dict, raw packet json, worktree) for every
    # packet that actually makes it into this turn's prompt.
    active: list[tuple[Path, dict, str, Path]] = []

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
        try:
            worktree = create_worktree(repo, str(packet["expected_base_commit_sha"]))
            record_worktree_correlation(worktree, packet)
            (attempt_dir / "worktree_path").write_text(str(worktree))
        except Exception as exc:
            error = f"pi_rpc worktree setup failed: {exc}"
            _write_exit(attempt_dir, returncode=1, cancelled=False, plumbing=True, error=error)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 1, True, False, error)
            continue
        active.append((attempt_dir, packet, packet_raw, worktree))

    if not active:
        # Every packet in this batch was pre-cancelled or failed setup in
        # isolation. No RPC round needed; the session is untouched and
        # stays healthy for the caller's next claim.
        return [outcomes[d] for d in attempt_dirs], False

    n = len(active)
    # Fan-out ceiling: ideally execution_policy.max_concurrent_jobs from
    # the graph, but that is not plumbed through NodePacket / dispatcher /
    # runner down to this adapter today (see module docstring). The only
    # value available here without inventing one is the batch's own size —
    # how many packets actually queued together for THIS turn — which is
    # what we use. A real ceiling read from the graph would go here once
    # that plumbing exists.
    fan_out_ceiling = n

    # Operator steer channel: `gddp steer` appends lines to steer.jsonl in
    # an attempt dir; the drain below runs on the client's single reader
    # thread (via on_poll) and delivers each message as an RPC prompt.
    # Plain lines are accepted as raw message text; JSON objects take
    # their "message" field. A batch turn drains EVERY active packet's own
    # steer.jsonl, tagging each delivered message with which packet it
    # came from so the operator can steer any node in the batch.
    steer_state: dict[Path, dict[str, int]] = {
        attempt_dir: {"offset": 0, "sent": 0} for attempt_dir, *_ in active
    }

    def _drain_steer(kind: str = "steer") -> None:
        # kind="steer": native RPC steer — delivered into the running turn
        # (accepted mid-turn, consumed before agent_end). kind="prompt":
        # used after agent_end while idle; starts a follow-up turn the
        # caller waits on. A bare "prompt" mid-turn is REJECTED by pi —
        # never use it for mid-turn delivery.
        for attempt_dir, *_ in active:
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

    # Per-turn events file, on the one long-lived client's reader loop.
    # The first active attempt is the live target; its full event stream
    # (including this turn's agent_end) is copied to every other active
    # attempt below once the turn ends, since it is the SAME shared turn.
    client.events_path = active[0][0] / "events.jsonl"

    packet_blocks = [
        f"--- packet {idx} of {n} ---\n"
        f"execution_attempt_id: {packet.get('execution_attempt_id')}\n"
        f"worktree_path: {worktree}\n\n"
        f"{packet_raw}"
        for idx, (attempt_dir, packet, packet_raw, worktree) in enumerate(active, start=1)
    ]
    batch_header = (
        f"### BATCH TURN — {n} packet(s) this turn, fan out up to "
        f"{fan_out_ceiling} top-level subagents concurrently (one per "
        "packet, per the final paragraph above).\n"
    )
    prompt = f"{_PACKET_PREAMBLE}\n\n{batch_header}\n" + "\n\n".join(packet_blocks)

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
        # try to persist whatever is in each worktree below rather than
        # treating the whole session as unhealthy.
        turn_error = str(exc)
        if proc.poll() is None:
            try:
                client.send({"type": "abort"}, wait_response=False)
            except Exception:
                pass

    if n > 1:
        try:
            shared_events = (active[0][0] / "events.jsonl").read_bytes()
        except OSError:
            shared_events = b""
        for attempt_dir, *_ in active[1:]:
            try:
                (attempt_dir / "events.jsonl").write_bytes(shared_events)
            except OSError:
                pass

    for attempt_dir, packet, _packet_raw, worktree in active:
        if plumbing:
            _write_exit(attempt_dir, returncode=1, cancelled=False, plumbing=True, error=turn_error)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 1, True, False, turn_error)
            continue

        cancel_path = attempt_dir / "cancel.requested"
        if cancel_path.exists():
            cancel_error = "cancelled during this packet's turn"
            _write_exit(attempt_dir, returncode=130, cancelled=True, plumbing=False, error=cancel_error)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 130, False, True, cancel_error)
            with contextlib.suppress(Exception):
                remove_worktree(repo, worktree)
            continue

        handoff = persist_result(worktree, packet)
        (attempt_dir / "result.json").write_text(
            json.dumps(handoff, sort_keys=True, separators=(",", ":"))
        )
        if handoff.get("result_commit_sha"):
            with contextlib.suppress(Exception):
                remove_worktree(repo, worktree)
            _write_exit(attempt_dir, returncode=0, cancelled=False, plumbing=False, error=None)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 0, False, False, None)
        else:
            persist_error = str(handoff.get("error") or "persist failed")
            _write_exit(attempt_dir, returncode=1, cancelled=False, plumbing=False, error=persist_error)
            outcomes[attempt_dir] = _TurnOutcome(attempt_dir, 1, False, False, persist_error)

    return [outcomes[d] for d in attempt_dirs], plumbing


def run_orchestrator(orchestrator_dir: Path) -> int:
    """Persistent per-project loop: claim packets from an inbox and run each
    as an RPC turn against one long-lived `pi --mode rpc` process.

    Exits (and kills pi) only on idle timeout or a pi-health plumbing
    failure — never unconditionally after a turn, and never because one
    packet in a batch was cancelled or failed to persist.
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

        client = _RpcClient(proc, events_path=orchestrator_dir / "events.jsonl")
        session_file_value: str | None = None
        try:
            state = client.get_state()
            session_file_value = state.get("sessionFile") or state.get("session_file")
        except Exception as exc:
            # Non-fatal: some builds emit bootstrap noise first.
            (orchestrator_dir / "get_state_error.txt").write_text(str(exc))

        batch: list[Path] | None = first_batch
        while batch is not None:
            active_attempt_dirs = batch
            _atomic_write(orchestrator_dir / "state", "busy")
            _atomic_write(
                orchestrator_dir / "current_attempt",
                "\n".join(str(d) for d in batch),
            )
            for attempt_dir in batch:
                _atomic_write(attempt_dir / "pid", str(proc.pid))
                if session_file_value:
                    _atomic_write(attempt_dir / "session_file", str(session_file_value))

            outcomes, terminate_session = _run_one_turn(
                attempt_dirs=batch,
                proc=proc,
                client=client,
                repo=repo,
                turn_timeout_s=turn_timeout_s,
                create_worktree=create_worktree,
                load_packet=load_packet,
                persist_result=persist_result,
                record_worktree_correlation=record_worktree_correlation,
                remove_worktree=remove_worktree,
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
        with contextlib.suppress(OSError):
            (orchestrator_dir / "pid").unlink()
        _atomic_write(orchestrator_dir / "state", "exited")


class _PlumbingError(RuntimeError):
    """Process died or protocol broke before a durable agent_end."""


class _RpcClient:
    def __init__(self, proc: subprocess.Popen[str], *, events_path: Path):
        self.proc = proc
        self.events_path = events_path
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

    def _record(self, evt: dict) -> None:
        try:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(evt, separators=(",", ":")) + "\n")
        except OSError:
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

    Fork A's batch turn (task item 1): a turn must carry every packet
    sitting in the inbox at the moment it is claimed, not just the oldest
    one, so `max_concurrent_jobs`-wide graphs fan out inside one RPC turn
    instead of serializing one attempt per turn. Packets that land in the
    inbox AFTER this snapshot is taken queue for the next call, never get
    injected into a turn already in flight.

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
    if len(argv) >= 2 and argv[0] == "--run-orchestrator":
        return run_orchestrator(Path(argv[1]))
    print(
        "usage: python -m adapters.pi_rpc_adapter --run-orchestrator DIR",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
