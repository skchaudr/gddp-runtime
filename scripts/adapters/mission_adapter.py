"""Factory mission adapter with durable engagement-level lifecycle state."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import fcntl

from .executor_protocol import (
    DispatchResult,
    EngagementAdapterDefaults,
    EngagementDispatchResult,
    NodePacket,
    PatchResult,
    SessionRef,
    SessionStatus,
)
from .mission_evidence import collect_mission_evidence
from .mission_projection import project_mission, verify_planned_feature_ids
from scripts.runtime.heartbeat.graph_reader import NodeData

_MISSION_CREATION_LOCK = threading.Lock()


class MissionAdapter(EngagementAdapterDefaults):
    """Factory ``droid exec --mission`` adapter."""

    executor_name = "factory_mission"

    def __init__(
        self,
        repo: str,
        *,
        cwd: str | Path | None = None,
        session_root: str | Path | None = None,
        mission_root: str | Path | None = None,
        droid_path: str = "droid",
        mission_dir_timeout: float = 10,
    ) -> None:
        self.repo = repo
        self.cwd = Path(cwd).resolve() if cwd else None
        runtime_root = Path(__file__).resolve().parents[2]
        self.session_root = Path(
            session_root
            or os.environ.get("GDDP_MISSION_SESSION_DIR")
            or runtime_root / "db" / "mission-sessions"
        ).expanduser().resolve()
        self.mission_root = Path(
            mission_root
            or os.environ.get("GDDP_FACTORY_MISSION_DIR")
            or Path.home() / ".factory" / "missions"
        ).expanduser().resolve()
        self.droid_path = droid_path
        self.mission_dir_timeout = mission_dir_timeout
        self._processes: dict[str, subprocess.Popen] = {}

    def dispatch(self, packet: NodePacket) -> DispatchResult:
        result = self.dispatch_engagement([packet])
        return DispatchResult(
            success=result.success,
            session_ref=result.session_ref,
            error=result.error,
        )

    def supports_engagement(self) -> bool:
        return True

    def dispatch_engagement(
        self, packets: list[NodePacket]
    ) -> EngagementDispatchResult:
        if not packets:
            return EngagementDispatchResult(
                success=False,
                error="factory mission engagement requires at least one packet",
            )
        if self.cwd is None:
            return EngagementDispatchResult(
                success=False,
                error="factory mission dispatch requires a target checkout",
            )

        feature_ids = tuple(packet.node_id for packet in packets)
        if len(set(feature_ids)) != len(feature_ids):
            return EngagementDispatchResult(
                success=False,
                feature_ids=feature_ids,
                error="factory mission engagement contains duplicate node ids",
            )
        expected_bases = {
            packet.expected_base_commit_sha
            for packet in packets
            if packet.expected_base_commit_sha
        }
        if len(expected_bases) > 1:
            return EngagementDispatchResult(
                success=False,
                feature_ids=feature_ids,
                error="factory mission engagement requires one common git base",
            )
        checkout_head = _git_head(self.cwd)
        if (
            checkout_head is not None
            and expected_bases
            and checkout_head not in expected_bases
        ):
            return EngagementDispatchResult(
                success=False,
                feature_ids=feature_ids,
                error=(
                    f"target checkout is at {checkout_head}, but engagement "
                    f"expects {next(iter(expected_bases))}"
                ),
            )

        engagement_id = uuid.uuid4().hex
        engagement_branch = f"gddp/{engagement_id}"
        engagement_dir = self.session_root / engagement_id
        stdout_path = engagement_dir / "stdout"
        stderr_path = engagement_dir / "stderr"
        receipts_path = engagement_dir / "receipts.jsonl"
        process: subprocess.Popen | None = None
        try:
            engagement_dir.mkdir(parents=True, exist_ok=False)
            mission_path = engagement_dir / "mission.md"
            mission_path.write_text(
                project_mission([_packet_node(packet) for packet in packets])
            )
            with _mission_creation_lock(self.session_root):
                existing_missions = _mission_directories(self.mission_root)
                with (
                    stdout_path.open("wb") as stdout,
                    stderr_path.open("wb") as stderr,
                ):
                    mission_env = dict(os.environ)
                    mission_env["GDDP_RECEIPTS_PATH"] = str(receipts_path)
                    process = subprocess.Popen(
                        [
                            self.droid_path,
                            "exec",
                            "--mission",
                            "-f",
                            str(mission_path),
                            "--auto",
                            "high",
                            "-w",
                            engagement_branch,
                        ],
                        cwd=str(self.cwd),
                        stdin=subprocess.DEVNULL,
                        stdout=stdout,
                        stderr=stderr,
                        start_new_session=True,
                        env=mission_env,
                    )
                mission_dir = _wait_for_mission_dir(
                    self.mission_root,
                    existing_missions,
                    timeout=self.mission_dir_timeout,
                )
            if mission_dir is None:
                raise RuntimeError("Factory mission directory was not created")
            record = {
                "engagement_id": engagement_id,
                "mission_dir": str(mission_dir),
                "process_pid": process.pid,
                "process_identity": _process_identity(process.pid),
                "process_returncode": None,
                "engagement_branch": engagement_branch,
                "feature_ids": list(feature_ids),
                "repo_path": str(self.cwd),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "receipts_path": str(receipts_path),
                "cancelled": False,
            }
            _write_json(engagement_dir / "session.json", record)
            self._processes[engagement_id] = process
        except Exception as exc:
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except OSError:
                    pass
            return EngagementDispatchResult(
                success=False,
                engagement_id=engagement_id,
                engagement_branch=engagement_branch,
                feature_ids=feature_ids,
                error=f"factory mission dispatch failed: {exc}",
            )

        return EngagementDispatchResult(
            success=True,
            engagement_id=engagement_id,
            session_ref=SessionRef(self.executor_name, engagement_id),
            mission_dir=str(mission_dir),
            process_pid=process.pid,
            engagement_branch=engagement_branch,
            feature_ids=feature_ids,
        )

    def status(self, session_ref: SessionRef) -> SessionStatus:
        record_path, record = self._record(session_ref)
        if record is None:
            return SessionStatus(state="missing", error="mission session not found")

        process = self._processes.get(session_ref.session_id)
        returncode = record.get("process_returncode")
        if process is not None:
            polled = process.poll()
            if polled is not None:
                returncode = polled
                record["process_returncode"] = polled
                if record_path is not None:
                    _write_json(record_path, record)

        pid = _positive_int(record.get("process_pid"))
        alive = bool(pid and _pid_is_running(pid))
        expected_identity = record.get("process_identity")
        if (
            alive
            and process is None
            and expected_identity
            and _process_identity(pid) != expected_identity
        ):
            alive = False
        if alive:
            return SessionStatus(state="running")

        terminal = _last_progress_event(
            Path(str(record["mission_dir"])) / "progress_log.jsonl"
        )
        terminal_type = terminal.get("type") if terminal else None
        if returncode in {None, 0} and terminal_type == "mission_completed":
            return SessionStatus(state="completed")
        details = (
            f"mission process {pid or 'unknown'} is dead without a "
            "mission_completed progress event"
        )
        if returncode not in {None, 0}:
            details += f" (exit code {returncode})"
        if record.get("cancelled"):
            details += " (cancelled)"
        factory_state = _factory_state(Path(str(record["mission_dir"])))
        if factory_state:
            details += f"; Factory state.json reported {factory_state!r}"
        return SessionStatus(state="crashed", error=details)

    def collect(self, session_ref: SessionRef, dest_path: Path) -> PatchResult:
        results = self.collect_engagement(session_ref)
        if len(results) != 1:
            return PatchResult(
                success=False,
                review_required=True,
                error=(
                    "single-node collect cannot represent "
                    f"{len(results)} engagement results"
                ),
            )
        result = results[0]
        if result.evidence_manifest_path:
            destination = Path(dest_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            manifest = json.loads(Path(result.evidence_manifest_path).read_text())
            _write_json(destination, manifest)
            result.patch_path = str(destination)
        return result

    def collect_engagement(self, session_ref: SessionRef) -> list[PatchResult]:
        record_path, record = self._record(session_ref)
        if record is None or record_path is None:
            return [
                PatchResult(
                    success=False,
                    review_required=True,
                    error="mission session not found",
                )
            ]

        demanded = tuple(str(item) for item in record.get("feature_ids", ()))
        mission_dir = Path(str(record["mission_dir"]))
        verification = verify_planned_feature_ids(
            mission_dir / "features.json", demanded
        )
        evidence = collect_mission_evidence(
            mission_dir=mission_dir,
            output_dir=record_path.parent / "evidence",
            engagement_id=str(record["engagement_id"]),
            result_ref=str(record["engagement_branch"]),
            demanded_feature_ids=demanded,
            receipts_path=record.get("receipts_path"),
            mission_outcome=_collection_outcome(record),
            git_repo_path=record.get("repo_path") or self.cwd,
        )
        results: list[PatchResult] = []
        for item in evidence:
            review_required = item.review_required or not verification.proceed
            error = item.review_reason
            if not verification.proceed:
                error = verification.reason
            results.append(
                PatchResult(
                    success=not review_required,
                    base_commit_sha=item.base_sha,
                    result_commit_sha=(
                        item.result_sha if verification.proceed else None
                    ),
                    result_ref=str(record["engagement_branch"]),
                    feature_id=item.feature_id,
                    evidence_manifest_path=str(item.manifest_path),
                    completion_id=item.completion_id,
                    completion_digest_sha256=item.completion_digest_sha256,
                    completion_quarantine_reason=(
                        item.completion_quarantine_reason
                    ),
                    review_required=review_required,
                    error=error,
                )
            )
        return results

    def cancel(self, session_ref: SessionRef) -> bool:
        record_path, record = self._record(session_ref)
        if record is None or record_path is None:
            return False
        pid = _positive_int(record.get("process_pid"))
        if pid is None:
            return False
        expected_identity = record.get("process_identity")
        if (
            expected_identity
            and _process_identity(pid) != expected_identity
        ):
            return False
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return False
        except OSError:
            return False
        record["cancelled"] = True
        record["cancelled_at"] = time.time()
        _write_json(record_path, record)
        return True

    def _record(
        self, session_ref: SessionRef
    ) -> tuple[Path | None, dict | None]:
        if (
            session_ref.executor != self.executor_name
            or not session_ref.session_id
            or Path(session_ref.session_id).name != session_ref.session_id
        ):
            return None, None
        record_path = self.session_root / session_ref.session_id / "session.json"
        try:
            record = json.loads(record_path.read_text())
        except (OSError, json.JSONDecodeError):
            return record_path, None
        return record_path, record if isinstance(record, dict) else None

def _packet_node(packet: NodePacket) -> NodeData:
    return NodeData(
        node_id=packet.node_id,
        title=packet.title,
        status="ready",
        type="capability",
        why=f"Goal: {packet.goal}\n\nWhy: {packet.why or 'Not supplied.'}",
        depends_on=[],
        acceptance_criteria=list(packet.acceptance_criteria),
        constraints=list(packet.constraints),
        allowed_execution_modes=["factory_mission"],
        required_artifacts=list(packet.required_artifacts),
        priority="normal",
        unlocks=[],
    )


def _mission_directories(root: Path) -> set[Path]:
    try:
        return {path.resolve() for path in root.iterdir() if path.is_dir()}
    except OSError:
        return set()


@contextmanager
def _mission_creation_lock(session_root: Path):
    """Serialize mission-directory discovery across heartbeat processes."""
    lock_path = session_root / ".mission-creation.lock"
    with _MISSION_CREATION_LOCK, lock_path.open("a") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _wait_for_mission_dir(
    root: Path, existing: set[Path], *, timeout: float
) -> Path | None:
    deadline = time.monotonic() + timeout
    while True:
        created = _mission_directories(root) - existing
        if created:
            return max(created, key=lambda path: path.stat().st_mtime_ns)
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.02)


def _last_progress_event(path: Path) -> dict | None:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            return event
    return None


def _factory_state(mission_dir: Path) -> str | None:
    try:
        payload = json.loads((mission_dir / "state.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    state = payload.get("state")
    return str(state) if state is not None else None


def _collection_outcome(record: Mapping[str, object]) -> str:
    returncode = record.get("process_returncode")
    if returncode not in {None, 0}:
        return "failed"
    mission_dir = Path(str(record["mission_dir"]))
    terminal = _last_progress_event(mission_dir / "progress_log.jsonl")
    if terminal and terminal.get("type") == "mission_completed":
        return "completed"
    if _factory_state(mission_dir) == "completed":
        return "completed"
    return "crashed"


def _positive_int(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _git_head(path: Path) -> str | None:
    try:
        process = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    head = process.stdout.strip()
    return head if process.returncode == 0 and head else None


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _process_identity(pid: int) -> str | None:
    """Return an OS-observed start/command token to detect PID reuse."""
    try:
        process = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart=", "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    identity = process.stdout.strip()
    return identity if process.returncode == 0 and identity else None


def _safe_component(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in value
    )
    return safe.strip("-") or "unknown"


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"))
    )
    temporary.replace(path)
