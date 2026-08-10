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
from .mission_push_guard import install_git_push_guard
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
        model: str | None = None,
        reasoning_effort: str | None = None,
        worker_model: str | None = None,
        worker_reasoning_effort: str | None = None,
        validator_model: str | None = None,
        validator_reasoning_effort: str | None = None,
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
        self.model = model or os.environ.get("GDDP_MISSION_MODEL")
        self.reasoning_effort = reasoning_effort or os.environ.get(
            "GDDP_MISSION_REASONING_EFFORT"
        )
        self.worker_model = worker_model or os.environ.get(
            "GDDP_MISSION_WORKER_MODEL"
        )
        self.worker_reasoning_effort = worker_reasoning_effort or os.environ.get(
            "GDDP_MISSION_WORKER_REASONING_EFFORT"
        )
        self.validator_model = validator_model or os.environ.get(
            "GDDP_MISSION_VALIDATOR_MODEL"
        )
        self.validator_reasoning_effort = (
            validator_reasoning_effort
            or os.environ.get("GDDP_MISSION_VALIDATOR_REASONING_EFFORT")
        )
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
            bases = sorted(expected_bases)
            return EngagementDispatchResult(
                success=False,
                feature_ids=feature_ids,
                error=(
                    "factory mission engagement requires one common git base; "
                    f"got {len(bases)} distinct expected bases: "
                    + ", ".join(b[:12] for b in bases)
                    + ". Reconcile: re-derive bases so all packets share one "
                    "base (e.g. normalize to the checkout tip when the "
                    "expected bases are ancestors of it), then re-dispatch."
                ),
            )
        checkout_head = _git_head(self.cwd)
        if (
            checkout_head is not None
            and expected_bases
            and checkout_head not in expected_bases
        ):
            expected = next(iter(expected_bases))
            return EngagementDispatchResult(
                success=False,
                feature_ids=feature_ids,
                error=(
                    f"target checkout is at {checkout_head}, but engagement "
                    f"expects {expected}. Reconcile: cd {self.cwd} && "
                    f"git checkout {expected}  (moves the checkout to the "
                    "expected base), or re-dispatch after the node's base "
                    "is re-derived to match the checkout."
                ),
            )

        engagement_id = uuid.uuid4().hex
        engagement_branch = f"gddp/{engagement_id}"
        engagement_dir = self.session_root / engagement_id
        stdout_path = engagement_dir / "stdout"
        stderr_path = engagement_dir / "stderr"
        receipts_path = engagement_dir / "receipts.jsonl"
        push_audit_path = engagement_dir / "push-audit.jsonl"
        process: subprocess.Popen | None = None
        try:
            engagement_dir.mkdir(parents=True, exist_ok=False)
            mission_path = engagement_dir / "mission.md"
            mission_path.write_text(
                project_mission(
                    [_packet_node(packet) for packet in packets],
                    engagement_branch=engagement_branch,
                )
            )
            with _mission_creation_lock(self.session_root):
                existing_missions = _mission_directories(self.mission_root)
                with (
                    stdout_path.open("wb") as stdout,
                    stderr_path.open("wb") as stderr,
                ):
                    mission_env = dict(os.environ)
                    mission_env["GDDP_RECEIPTS_PATH"] = str(receipts_path)
                    mission_env = install_git_push_guard(
                        engagement_dir / "git-guard",
                        engagement_branch=engagement_branch,
                        audit_path=push_audit_path,
                        base_env=mission_env,
                    )
                    mission_argv = [
                        self.droid_path,
                        "exec",
                        "--mission",
                        "-f",
                        str(mission_path),
                        "--auto",
                        "high",
                        "-w",
                        engagement_branch,
                    ]
                    if self.model:
                        mission_argv.extend(["-m", self.model])
                    if self.reasoning_effort:
                        mission_argv.extend(["-r", self.reasoning_effort])
                    if self.worker_model:
                        mission_argv.extend(["--worker-model", self.worker_model])
                    if self.worker_reasoning_effort:
                        mission_argv.extend(
                            [
                                "--worker-reasoning-effort",
                                self.worker_reasoning_effort,
                            ]
                        )
                    if self.validator_model:
                        mission_argv.extend(
                            ["--validator-model", self.validator_model]
                        )
                    if self.validator_reasoning_effort:
                        mission_argv.extend(
                            [
                                "--validator-reasoning-effort",
                                self.validator_reasoning_effort,
                            ]
                        )
                    process = subprocess.Popen(
                        mission_argv,
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
                "push_audit_path": str(push_audit_path),
                "launch_argv": list(mission_argv),
                "model_profile": {
                    "orchestrator": {
                        "model": self.model,
                        "reasoning_effort": self.reasoning_effort,
                    },
                    "worker": {
                        "model": self.worker_model,
                        "reasoning_effort": self.worker_reasoning_effort,
                    },
                    "validator": {
                        "model": self.validator_model,
                        "reasoning_effort": self.validator_reasoning_effort,
                    },
                },
                "cancelled": False,
            }
            # Capture immediate exits before the adapter returns success.
            # Heartbeat processes are short-lived; in-memory Popen is gone on
            # the next tick, so an already-dead process must not look "running".
            early_returncode = process.poll()
            if early_returncode is not None:
                record["process_returncode"] = early_returncode
            _write_json(engagement_dir / "session.json", record)
            self._processes[engagement_id] = process
            if early_returncode is not None and early_returncode != 0:
                return EngagementDispatchResult(
                    success=False,
                    engagement_id=engagement_id,
                    session_ref=SessionRef(self.executor_name, engagement_id),
                    mission_dir=str(mission_dir),
                    process_pid=process.pid,
                    engagement_branch=engagement_branch,
                    feature_ids=feature_ids,
                    error=_format_process_failure(
                        record, returncode=early_returncode
                    ),
                )
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
        if alive and process is None:
            current_identity = _process_identity(pid) if pid else None
            if expected_identity:
                if current_identity != expected_identity:
                    alive = False
            elif current_identity is None or "exec --mission" not in current_identity:
                # No durable launch identity: do not trust bare PID liveness
                # (PID reuse would strand the job as running forever).
                alive = False
        if alive:
            return SessionStatus(state="running")

        mission_dir = Path(str(record["mission_dir"]))
        terminal = _last_progress_event(mission_dir / "progress_log.jsonl")
        terminal_type = terminal.get("type") if terminal else None
        factory_state = _factory_state(mission_dir)
        if returncode in {None, 0} and (
            terminal_type == "mission_completed" or factory_state == "completed"
        ):
            return SessionStatus(state="completed")
        return SessionStatus(
            state="failed" if returncode not in {None, 0} else "crashed",
            error=_format_process_failure(record, returncode=returncode),
        )

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
        return self._collect_engagement_results(session_ref)

    def completed_feature_ids(self, session_ref: SessionRef) -> tuple[str, ...]:
        """Return demanded features reported successfully completed by Factory."""
        _record_path, record = self._record(session_ref)
        if record is None:
            return ()
        demanded = tuple(str(item) for item in record.get("feature_ids", ()))
        mission_dir = Path(str(record["mission_dir"]))
        completed: set[str] = set()
        try:
            lines = (mission_dir / "progress_log.jsonl").read_text(
                errors="replace"
            ).splitlines()
        except OSError:
            return ()
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, Mapping):
                continue
            feature_id = event.get("featureId")
            if (
                event.get("type") == "worker_completed"
                and event.get("successState") == "success"
                and isinstance(feature_id, str)
            ):
                completed.add(feature_id)
        return tuple(feature_id for feature_id in demanded if feature_id in completed)

    def collect_completed_engagement(
        self,
        session_ref: SessionRef,
        feature_ids: Sequence[str],
    ) -> list[PatchResult]:
        """Collect a durable completed subset while the mission keeps running."""
        return self._collect_engagement_results(
            session_ref,
            selected_feature_ids=feature_ids,
            mission_outcome="running",
        )

    def collect_engagement_features(
        self,
        session_ref: SessionRef,
        feature_ids: Sequence[str],
    ) -> list[PatchResult]:
        """Collect only remaining feature rows after engagement termination."""
        return self._collect_engagement_results(
            session_ref,
            selected_feature_ids=feature_ids,
        )

    def _collect_engagement_results(
        self,
        session_ref: SessionRef,
        *,
        selected_feature_ids: Sequence[str] | None = None,
        mission_outcome: str | None = None,
    ) -> list[PatchResult]:
        record_path, record = self._record(session_ref)
        if record is None or record_path is None:
            return [
                PatchResult(
                    success=False,
                    review_required=True,
                    error="mission session not found",
                )
            ]

        terminal_status = self.status(session_ref)
        _, refreshed_record = self._record(session_ref)
        if refreshed_record is not None:
            record = refreshed_record
        demanded = tuple(str(item) for item in record.get("feature_ids", ()))
        selected = demanded
        if selected_feature_ids is not None:
            requested = {str(item) for item in selected_feature_ids}
            selected = tuple(item for item in demanded if item in requested)
            unknown = requested.difference(demanded)
            if unknown:
                raise ValueError(
                    f"completed feature ids are not demanded: {sorted(unknown)!r}"
                )
        mission_dir = Path(str(record["mission_dir"]))
        mission_outcome = mission_outcome or _collection_outcome(record)
        mission_failure_reason = (
            terminal_status.error
            if terminal_status.state in {"crashed", "failed"}
            else None
        )
        verification = verify_planned_feature_ids(
            mission_dir / "features.json", demanded
        )
        evidence = collect_mission_evidence(
            mission_dir=mission_dir,
            output_dir=record_path.parent / "evidence",
            engagement_id=str(record["engagement_id"]),
            result_ref=str(record["engagement_branch"]),
            demanded_feature_ids=selected,
            planned_feature_ids=demanded,
            receipts_path=record.get("receipts_path"),
            mission_outcome=mission_outcome,
            mission_failure_reason=mission_failure_reason,
            mission_process={
                "pid": _positive_int(record.get("process_pid")),
                "exit_code": record.get("process_returncode"),
                "stdout_path": record.get("stdout_path"),
                "stderr_path": record.get("stderr_path"),
                "cancelled": bool(record.get("cancelled")),
            },
            worktree=_git_worktree_evidence(
                record.get("repo_path") or self.cwd,
                str(record["engagement_branch"]),
            ),
            git_repo_path=record.get("repo_path") or self.cwd,
            origin_remote="origin",
            push_audit_path=record.get("push_audit_path"),
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
    if (
        terminal and terminal.get("type") == "mission_completed"
    ) or _factory_state(mission_dir) == "completed":
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


def _git_worktree_evidence(
    repo_path: object,
    engagement_branch: str,
) -> dict[str, object]:
    """Observe, but never clean or stage, the engagement worktree."""
    if not isinstance(repo_path, str | Path):
        return {
            "path": None,
            "dirty": None,
            "status_porcelain": [],
            "changed_paths": [],
            "error": "repository path is unavailable",
        }
    repo = Path(repo_path).expanduser().resolve()
    worktree = _find_branch_worktree(repo, engagement_branch)
    if worktree is None:
        return {
            "path": None,
            "dirty": None,
            "status_porcelain": [],
            "changed_paths": [],
            "error": (
                f"engagement worktree for branch {engagement_branch} "
                "could not be located"
            ),
        }
    try:
        process = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "path": str(worktree),
            "dirty": None,
            "status_porcelain": [],
            "changed_paths": [],
            "error": f"git status failed: {exc}",
        }
    if process.returncode != 0:
        return {
            "path": str(worktree),
            "dirty": None,
            "status_porcelain": [],
            "changed_paths": [],
            "error": (
                f"git status exited with code {process.returncode}: "
                f"{process.stderr.strip()}"
            ),
        }
    entries = [line for line in process.stdout.splitlines() if line]
    changed_paths = sorted(
        {
            line[3:].split(" -> ", 1)[-1]
            for line in entries
            if len(line) > 3
        }
    )
    return {
        "path": str(worktree),
        "dirty": bool(entries),
        "status_porcelain": entries,
        "changed_paths": changed_paths,
        "error": None,
    }


def _find_branch_worktree(repo: Path, engagement_branch: str) -> Path | None:
    try:
        process = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if process.returncode != 0:
        return None
    current_path: Path | None = None
    desired_ref = f"refs/heads/{engagement_branch}"
    for line in process.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree ")).resolve()
        elif line == f"branch {desired_ref}" and current_path is not None:
            return current_path
        elif not line:
            current_path = None
    return None


def _read_text_tail(path: object, *, limit: int = 2000) -> str:
    if not isinstance(path, str | Path):
        return ""
    try:
        raw = Path(path).read_text(errors="replace")
    except OSError:
        return ""
    text = raw.strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[-limit:]


def _format_process_failure(
    record: Mapping[str, object],
    *,
    returncode: object,
) -> str:
    pid = _positive_int(record.get("process_pid"))
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
    stderr = _read_text_tail(record.get("stderr_path"))
    stdout = _read_text_tail(record.get("stdout_path"))
    if stderr:
        details += f"; stderr: {stderr}"
    elif stdout:
        details += f"; stdout: {stdout}"
    return details


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
