"""Rebuild one cumulative remote review branch per graph.

Whenever a durable result commit arrives, the runtime rebuilds
``gddp/review/<project_id>`` from ``origin/<target_branch>`` and then
deletes temporary ``gddp/result-*`` / ``gddp/attempt-*`` refs whose
commits are already represented on that review branch.

Graph completion stays human-owned. Publishing the review branch is
evidence delivery only.
"""

from __future__ import annotations

import fcntl
import os
import sqlite3
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from .repo_resolver import resolve_project_repo_checkout
from .results_store import DB_PATH, RUNTIME_ROOT

REVIEW_REF_PREFIX = "gddp/review/"
RESULT_REF_PREFIX = "gddp/result-"
ATTEMPT_REF_PREFIX = "gddp/attempt-"
TERMINAL_NODE_STATUSES = frozenset({"complete", "deferred"})
_GIT_TIMEOUT = 60
_FETCH_TIMEOUT = 120
_PUSH_TIMEOUT = 90

_rebuild_lock = threading.Lock()
_in_flight: set[str] = set()
_pending: set[str] = set()
_workers: dict[str, threading.Thread] = {}
_publish_locks_guard = threading.Lock()
_publish_locks: dict[str, threading.Lock] = {}
_LOCK_DIR_ENV = "GDDP_REVIEW_LOCK_DIR"


@dataclass(frozen=True)
class ActiveResult:
    """One node's latest durable result commit, plus its transport refs."""

    node_id: str
    job_id: str
    session_id: str
    commit_sha: str
    depends_on: tuple[str, ...] = ()


@dataclass
class CleanupOutcome:
    """Separate remote lease-delete success from local cleanup."""

    remote_deleted: list[str] = field(default_factory=list)
    local_deleted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def cleaned_refs(self) -> list[str]:
        return list(self.remote_deleted)


@dataclass
class RebuildReport:
    project_id: str
    review_ref: str
    target_branch: str
    review_sha: str | None = None
    merged_shas: list[str] = field(default_factory=list)
    skipped_shas: list[str] = field(default_factory=list)
    cleaned_refs: list[str] = field(default_factory=list)
    local_cleaned_refs: list[str] = field(default_factory=list)
    skipped_cleanup_refs: list[str] = field(default_factory=list)
    published: bool = False
    incomplete: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return (
            self.error is None
            and self.published
            and not self.incomplete
            and bool(self.review_sha)
        )


def review_ref_name(project_id: str) -> str:
    return f"{REVIEW_REF_PREFIX}{project_id}"


def result_ref_name(job_id: str, session_id: str) -> str:
    return f"{RESULT_REF_PREFIX}{job_id}-{session_id}"


def config_root() -> Path:
    runtime_root = Path(__file__).resolve().parents[2]
    return Path(
        os.environ.get("GDDP_CONFIG_PATH", str(runtime_root.parent / "gddp-config"))
    )


def load_target_branch(project_id: str, *, root: Path | None = None) -> str:
    """Read ``target_branch`` from project.yaml; default to ``main``."""
    project_yaml = (root or config_root()) / "graphs" / project_id / "project.yaml"
    try:
        doc = yaml.safe_load(project_yaml.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return "main"
    raw = doc.get("target_branch") or "main"
    branch = str(raw).strip()
    return branch or "main"


def load_node_statuses(
    project_id: str, *, root: Path | None = None
) -> dict[str, str]:
    """Map node_id → status from node YAML, falling back to project.yaml."""
    root = root or config_root()
    project_dir = root / "graphs" / project_id
    statuses: dict[str, str] = {}
    project_yaml = project_dir / "project.yaml"
    try:
        doc = yaml.safe_load(project_yaml.read_text()) or {}
    except (OSError, yaml.YAMLError):
        doc = {}
    for summary in doc.get("nodes") or []:
        if isinstance(summary, dict) and summary.get("id"):
            statuses[str(summary["id"])] = str(summary.get("status") or "")
    nodes_dir = project_dir / "nodes"
    if nodes_dir.is_dir():
        for node_file in nodes_dir.glob("*.yaml"):
            try:
                node_doc = yaml.safe_load(node_file.read_text()) or {}
            except (OSError, yaml.YAMLError):
                continue
            node_id = node_doc.get("node_id") or node_file.stem
            if node_doc.get("status") is not None:
                statuses[str(node_id)] = str(node_doc.get("status") or "")
    return statuses


def load_node_dependencies(
    project_id: str, *, root: Path | None = None
) -> dict[str, tuple[str, ...]]:
    """Map node_id → depends_on from node YAML, then job.dependencies."""
    root = root or config_root()
    nodes_dir = root / "graphs" / project_id / "nodes"
    deps: dict[str, tuple[str, ...]] = {}
    if not nodes_dir.is_dir():
        return deps
    for node_file in nodes_dir.glob("*.yaml"):
        try:
            node_doc = yaml.safe_load(node_file.read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        node_id = node_doc.get("node_id") or node_file.stem
        raw = node_doc.get("depends_on") or []
        if isinstance(raw, list):
            deps[str(node_id)] = tuple(str(item) for item in raw)
    return deps


def _parse_dependencies(raw) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, (list, tuple)):
        return tuple(str(item) for item in raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ()
        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError:
            return ()
        if isinstance(parsed, list):
            return tuple(str(item) for item in parsed)
    return ()


def query_active_results(
    con: sqlite3.Connection,
    project_id: str,
    *,
    statuses: dict[str, str] | None = None,
    dependencies: dict[str, tuple[str, ...]] | None = None,
) -> list[ActiveResult]:
    """Latest result_commit_sha per non-terminal project node."""
    statuses = statuses if statuses is not None else load_node_statuses(project_id)
    dependencies = (
        dependencies
        if dependencies is not None
        else load_node_dependencies(project_id)
    )
    rows = con.execute(
        """
        SELECT j.node_id, j.job_id, j.dependencies,
               s.session_id, s.result_commit_sha, s.attempt_index, s.updated_at
          FROM jobs j
          JOIN executor_sessions s ON s.job_id = j.job_id
         WHERE j.project_id = ?
           AND s.result_commit_sha IS NOT NULL
           AND TRIM(s.result_commit_sha) != ''
         ORDER BY s.attempt_index DESC, s.updated_at DESC
        """,
        (project_id,),
    ).fetchall()
    seen: set[str] = set()
    results: list[ActiveResult] = []
    for row in rows:
        node_id = str(row["node_id"])
        if node_id in seen:
            continue
        if (statuses.get(node_id) or "") in TERMINAL_NODE_STATUSES:
            continue
        seen.add(node_id)
        results.append(
            ActiveResult(
                node_id=node_id,
                job_id=str(row["job_id"]),
                session_id=str(row["session_id"]),
                commit_sha=str(row["result_commit_sha"]),
                depends_on=dependencies.get(node_id)
                or _parse_dependencies(row["dependencies"]),
            )
        )
    return results


def topological_merge_order(results: Iterable[ActiveResult]) -> list[ActiveResult]:
    """Stable Kahn order; leftover cycles keep original relative order."""
    items = list(results)
    by_id = {item.node_id: item for item in items}
    remaining = {item.node_id: set(item.depends_on) & set(by_id) for item in items}
    ordered: list[ActiveResult] = []
    ready = [item for item in items if not remaining[item.node_id]]
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for item in items:
            if current.node_id in remaining[item.node_id]:
                remaining[item.node_id].discard(current.node_id)
                if not remaining[item.node_id] and item not in ordered and item not in ready:
                    ready.append(item)
    leftover = [item for item in items if item not in ordered]
    return ordered + leftover


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = _GIT_TIMEOUT,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            ["git", *args], 124, exc.stdout or "", str(exc)
        )
    except OSError as exc:
        return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))


def _heads_ref(name: str) -> str:
    return name if name.startswith("refs/") else f"refs/heads/{name}"


def list_temporary_refs(repo_path: Path) -> list[str]:
    """Local + remote temporary transport refs."""
    names: set[str] = set()
    local = _run_git(
        ["for-each-ref", "--format=%(refname:short)", "refs/heads/gddp/"],
        cwd=repo_path,
    )
    if local.returncode == 0:
        for line in local.stdout.splitlines():
            name = line.strip()
            if name.startswith(RESULT_REF_PREFIX) or name.startswith(ATTEMPT_REF_PREFIX):
                names.add(name)
    remote = _run_git(
        ["ls-remote", "--heads", "origin", "gddp/result-*", "gddp/attempt-*"],
        cwd=repo_path,
        timeout=_FETCH_TIMEOUT,
    )
    if remote.returncode == 0:
        for line in remote.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            ref = parts[1]
            if ref.startswith("refs/heads/"):
                name = ref[len("refs/heads/") :]
                if name.startswith(RESULT_REF_PREFIX) or name.startswith(ATTEMPT_REF_PREFIX):
                    names.add(name)
    return sorted(names)


def commit_is_ancestor(repo_path: Path, maybe_ancestor: str, descendant: str) -> bool:
    proc = _run_git(
        ["merge-base", "--is-ancestor", maybe_ancestor, descendant],
        cwd=repo_path,
    )
    return proc.returncode == 0


def ref_commit(repo_path: Path, ref_name: str) -> str | None:
    proc = _run_git(
        ["rev-parse", "--verify", f"{_heads_ref(ref_name)}^{{commit}}"],
        cwd=repo_path,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    remote = _run_git(
        ["ls-remote", "--heads", "origin", ref_name],
        cwd=repo_path,
        timeout=_FETCH_TIMEOUT,
    )
    if remote.returncode != 0:
        return None
    for line in remote.stdout.splitlines():
        sha = line.split()[0].strip() if line.split() else ""
        if sha:
            return sha
    return None


def remote_ref_sha(repo_path: Path, ref_name: str) -> str | None:
    remote = _run_git(
        ["ls-remote", "--heads", "origin", ref_name],
        cwd=repo_path,
        timeout=_FETCH_TIMEOUT,
    )
    if remote.returncode != 0:
        return None
    wanted = _heads_ref(ref_name)
    for line in remote.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        sha, ref = parts[0].strip(), parts[1].strip()
        if sha and ref in {wanted, ref_name, f"refs/heads/{ref_name}"}:
            return sha
    return None


def delete_local_temporary_ref(repo_path: Path, ref_name: str) -> bool:
    if not (
        ref_name.startswith(RESULT_REF_PREFIX)
        or ref_name.startswith(ATTEMPT_REF_PREFIX)
    ):
        return False
    local = _run_git(["update-ref", "-d", _heads_ref(ref_name)], cwd=repo_path)
    if local.returncode == 0:
        return True
    fallback = _run_git(["branch", "-D", ref_name], cwd=repo_path)
    return fallback.returncode == 0


def delete_remote_temporary_ref(
    repo_path: Path, ref_name: str, expected_sha: str
) -> bool:
    """Delete origin/<ref> only if it still points at expected_sha."""
    if not (
        ref_name.startswith(RESULT_REF_PREFIX)
        or ref_name.startswith(ATTEMPT_REF_PREFIX)
    ):
        return False
    if not expected_sha:
        return False
    current = remote_ref_sha(repo_path, ref_name)
    if current is None:
        return False
    if current != expected_sha:
        return False
    dest = _heads_ref(ref_name)
    push = _run_git(
        [
            "push",
            f"--force-with-lease={dest}:{expected_sha}",
            "origin",
            f":{dest}",
        ],
        cwd=repo_path,
        timeout=_PUSH_TIMEOUT,
    )
    if push.returncode == 0:
        return True
    # The lease lost or the ref moved; never treat that as success.
    return False


def delete_temporary_ref(
    repo_path: Path, ref_name: str, expected_sha: str | None = None
) -> bool:
    """Backward-compatible helper: remote lease-delete is the success signal."""
    sha = expected_sha or remote_ref_sha(repo_path, ref_name) or ref_commit(repo_path, ref_name)
    if not sha:
        return False
    return delete_remote_temporary_ref(repo_path, ref_name, sha)


def cleanup_preserved_refs(
    repo_path: Path,
    review_sha: str,
    extra_refs: Iterable[str] = (),
) -> CleanupOutcome:
    """Lease-delete remote temp refs whose observed SHA is on the review branch."""
    outcome = CleanupOutcome()
    seen: set[str] = set()
    for ref_name in list(extra_refs) + list_temporary_refs(repo_path):
        if ref_name in seen:
            continue
        seen.add(ref_name)
        observed = remote_ref_sha(repo_path, ref_name)
        local_sha = ref_commit(repo_path, ref_name)
        sha = observed or local_sha
        if not sha:
            continue
        if not commit_is_ancestor(repo_path, sha, review_sha):
            outcome.skipped.append(ref_name)
            continue
        if observed and delete_remote_temporary_ref(repo_path, ref_name, observed):
            outcome.remote_deleted.append(ref_name)
            if delete_local_temporary_ref(repo_path, ref_name):
                outcome.local_deleted.append(ref_name)
            continue
        if observed and observed != sha:
            outcome.skipped.append(ref_name)
            continue
        if observed:
            # Remote still present but lease lost (retry moved the tip).
            outcome.skipped.append(ref_name)
            continue
        if local_sha and delete_local_temporary_ref(repo_path, ref_name):
            outcome.local_deleted.append(ref_name)
        else:
            outcome.skipped.append(ref_name)
    return outcome


def _fetch_target(repo_path: Path, target_branch: str) -> str | None:
    fetch = _run_git(
        ["fetch", "origin", target_branch],
        cwd=repo_path,
        timeout=_FETCH_TIMEOUT,
    )
    if fetch.returncode != 0 and "couldn't find remote ref" in (fetch.stderr or ""):
        return None
    for candidate in (f"origin/{target_branch}", target_branch):
        resolved = _run_git(
            ["rev-parse", "--verify", f"{candidate}^{{commit}}"],
            cwd=repo_path,
        )
        if resolved.returncode == 0 and resolved.stdout.strip():
            return resolved.stdout.strip()
    return None


def lock_dir() -> Path:
    configured = os.environ.get(_LOCK_DIR_ENV)
    if configured:
        return Path(configured)
    return RUNTIME_ROOT / "locks" / "review-branch"


def project_lock_path(project_id: str, *, directory: Path | None = None) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in project_id)
    return (directory or lock_dir()) / f"{safe}.lock"


class ProcessPublishLock:
    """Cross-process exclusive lock for one project's publish/cleanup."""

    def __init__(self, project_id: str, *, directory: Path | None = None):
        self.project_id = project_id
        self.path = project_lock_path(project_id, directory=directory)
        self._handle = None

    def acquire(self, *, blocking: bool = False) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+")
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(handle.fileno(), flags)
        except BlockingIOError:
            handle.close()
            return False
        except OSError:
            handle.close()
            raise
        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class ProjectPublishGuard:
    """Thread lock plus flock so one publisher exists in-process and across processes."""

    def __init__(self, project_id: str, *, directory: Path | None = None):
        self._thread = threading.Lock()
        self._process = ProcessPublishLock(project_id, directory=directory)

    def acquire(self, *, blocking: bool = False) -> bool:
        if not self._thread.acquire(blocking=blocking):
            return False
        try:
            if self._process.acquire(blocking=blocking):
                return True
        except Exception:
            self._thread.release()
            raise
        self._thread.release()
        return False

    def release(self) -> None:
        try:
            self._process.release()
        finally:
            self._thread.release()


def _publish_lock_for(project_id: str) -> ProjectPublishGuard:
    with _publish_locks_guard:
        lock = _publish_locks.get(project_id)
        if lock is None:
            lock = ProjectPublishGuard(project_id)
            _publish_locks[project_id] = lock
        return lock


def _remote_review_sha(repo_path: Path, review_ref: str) -> str | None:
    return remote_ref_sha(repo_path, review_ref)


def _merge_commit(worktree: Path, sha: str) -> tuple[bool, str | None]:
    merge = _run_git(
        [
            "-c",
            "user.name=gddp-runtime",
            "-c",
            "user.email=gddp-runtime@local",
            "merge",
            "--no-edit",
            sha,
        ],
        cwd=worktree,
    )
    if merge.returncode == 0:
        return True, None
    _run_git(["merge", "--abort"], cwd=worktree)
    detail = (merge.stderr or merge.stdout or "").strip()
    return False, detail or "merge conflict"


def rebuild_review_branch(
    repo_path: Path,
    project_id: str,
    results: Iterable[ActiveResult],
    *,
    target_branch: str | None = None,
) -> RebuildReport:
    """Rebuild ``origin/gddp/review/<project_id>`` from target_branch + results."""
    branch = target_branch or load_target_branch(project_id)
    review_ref = review_ref_name(project_id)
    report = RebuildReport(
        project_id=project_id,
        review_ref=review_ref,
        target_branch=branch,
    )
    lock = _publish_lock_for(project_id)
    if not lock.acquire(blocking=False):
        report.incomplete = True
        report.error = f"rebuild already publishing for {project_id}"
        return report
    tmpdir = None
    try:
        base_sha = _fetch_target(repo_path, branch)
        if not base_sha:
            report.error = f"could not resolve origin/{branch}"
            return report

        ordered = topological_merge_order(results)
        tmpdir = tempfile.mkdtemp(prefix=f"gddp-review-{project_id}-")
        os.rmdir(tmpdir)
        add = _run_git(
            ["worktree", "add", "--detach", tmpdir, base_sha],
            cwd=repo_path,
        )
        if add.returncode != 0:
            report.error = f"worktree add failed: {(add.stderr or add.stdout).strip()}"
            return report
        worktree = Path(tmpdir)
        previous = _remote_review_sha(repo_path, review_ref)
        for item in ordered:
            merged, detail = _merge_commit(worktree, item.commit_sha)
            if merged:
                report.merged_shas.append(item.commit_sha)
                continue
            report.skipped_shas.append(item.commit_sha)
            report.error = (
                f"merge conflict on {item.node_id} ({item.commit_sha[:12]}); "
                f"previous {review_ref} preserved"
            )
            if detail:
                report.error = f"{report.error}: {detail}"
            return report
        head = _run_git(["rev-parse", "HEAD"], cwd=worktree)
        if head.returncode != 0 or not head.stdout.strip():
            report.error = "could not read rebuilt HEAD"
            return report
        report.review_sha = head.stdout.strip()
        dest = _heads_ref(review_ref)
        if previous:
            push_args = [
                "push",
                f"--force-with-lease={dest}:{previous}",
                "origin",
                f"HEAD:{dest}",
            ]
        else:
            # Creating the review ref is exclusive via the process lock.
            push_args = ["push", "origin", f"HEAD:{dest}"]
        push = _run_git(
            push_args,
            cwd=worktree,
            timeout=_PUSH_TIMEOUT,
        )
        if push.returncode != 0:
            report.published = False
            report.incomplete = True
            report.error = f"force-push failed: {(push.stderr or push.stdout).strip()}"
            report.review_sha = previous
            return report
        report.published = True
        extra = [result_ref_name(item.job_id, item.session_id) for item in ordered]
        cleanup = cleanup_preserved_refs(
            repo_path, report.review_sha, extra_refs=extra
        )
        report.cleaned_refs = list(cleanup.remote_deleted)
        report.local_cleaned_refs = list(cleanup.local_deleted)
        report.skipped_cleanup_refs = list(cleanup.skipped)
        return report
    finally:
        lock.release()
        if tmpdir is not None:
            _run_git(["worktree", "remove", "--force", tmpdir], cwd=repo_path)
            _run_git(["worktree", "prune", "--expire", "now"], cwd=repo_path)


def rebuild_project(
    project_id: str,
    *,
    repo_path: Path | None = None,
    db_path: Path | None = None,
    config: Path | None = None,
    con: sqlite3.Connection | None = None,
) -> RebuildReport:
    """Load active results from the runtime DB and rebuild the review branch."""
    root = config or config_root()
    checkout = repo_path or resolve_project_repo_checkout(
        project_id, config_root=root
    )
    review_ref = review_ref_name(project_id)
    target = load_target_branch(project_id, root=root)
    if checkout is None:
        return RebuildReport(
            project_id=project_id,
            review_ref=review_ref,
            target_branch=target,
            error=f"repo checkout not found for project {project_id!r}",
        )
    owns_connection = con is None
    if con is None:
        con = sqlite3.connect(str(db_path or DB_PATH))
        con.row_factory = sqlite3.Row
    try:
        results = query_active_results(
            con,
            project_id,
            statuses=load_node_statuses(project_id, root=root),
            dependencies=load_node_dependencies(project_id, root=root),
        )
    finally:
        if owns_connection:
            con.close()
    return rebuild_review_branch(
        checkout, project_id, results, target_branch=target
    )


_after_empty_check_hook = None


def _reset_scheduler_state_for_tests() -> None:
    """Drop scheduler bookkeeping between unit tests."""
    global _after_empty_check_hook
    with _rebuild_lock:
        _in_flight.clear()
        _pending.clear()
        _workers.clear()
    with _publish_locks_guard:
        _publish_locks.clear()
    _after_empty_check_hook = None


def publication_in_progress() -> bool:
    with _rebuild_lock:
        return bool(_in_flight or _pending or any(t.is_alive() for t in _workers.values()))


def _forget_worker_locked(project_id: str) -> None:
    if _workers.get(project_id) is threading.current_thread():
        _workers.pop(project_id, None)


def _start_worker_locked(project_id: str) -> None:
    existing = _workers.get(project_id)
    if existing is not None and existing.is_alive():
        return
    worker = threading.Thread(
        target=_worker_loop,
        args=(project_id,),
        name=f"gddp-review-{project_id}",
        daemon=False,
    )
    _workers[project_id] = worker
    worker.start()


def _ensure_workers_locked() -> None:
    for project_id in list(_pending):
        _start_worker_locked(project_id)


def wait_for_publication(*, timeout: float | None = None) -> None:
    """Block until every scheduled rebuild has finished publishing/cleanup.

    Heartbeat is one-shot. The process must not exit while a review-branch
    worker still holds publish/cleanup ownership. Pending work with no live
    worker is a lost-wakeup; this wait starts a successor instead of hanging.
    """
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        with _rebuild_lock:
            _ensure_workers_locked()
            workers = [thread for thread in _workers.values() if thread.is_alive()]
            pending = bool(_pending or _in_flight)
        if not workers and not pending:
            return
        remaining = None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("review-branch publication still running")
        if workers:
            workers[0].join(timeout=remaining)
        else:
            time.sleep(0.01)


def _worker_loop(owner_project_id: str) -> None:
    """One worker owns one project until that project's queue is empty."""
    try:
        while True:
            with _rebuild_lock:
                if owner_project_id in _pending:
                    _pending.discard(owner_project_id)
                    _in_flight.add(owner_project_id)
                    exiting = False
                else:
                    exiting = True
            if exiting:
                hook = _after_empty_check_hook
                if hook is not None:
                    # Test seam: schedule during this window. Production
                    # schedule either lands in _pending for this worker to
                    # consume, or starts a successor after we forget ourselves.
                    hook(owner_project_id)
                with _rebuild_lock:
                    still_owner = (
                        _workers.get(owner_project_id) is threading.current_thread()
                    )
                    if owner_project_id in _pending and still_owner:
                        continue
                    if still_owner:
                        _forget_worker_locked(owner_project_id)
                    return
            try:
                report = rebuild_project(owner_project_id)
                if report.ok:
                    print(
                        f"[review-branch] {owner_project_id}: "
                        f"{report.review_ref} @ {report.review_sha[:12]} "
                        f"(merged={len(report.merged_shas)} "
                        f"cleaned={len(report.cleaned_refs)})"
                    )
                else:
                    print(
                        f"[review-branch] {owner_project_id}: "
                        f"rebuild failed: {report.error}"
                    )
            except Exception as exc:  # noqa: BLE001 — never break the caller
                print(
                    f"[review-branch] {owner_project_id}: rebuild crashed: {exc}"
                )
            finally:
                with _rebuild_lock:
                    _in_flight.discard(owner_project_id)
    finally:
        with _rebuild_lock:
            _in_flight.discard(owner_project_id)
            if owner_project_id in _pending:
                if _workers.get(owner_project_id) is threading.current_thread():
                    _workers.pop(owner_project_id, None)
                _start_worker_locked(owner_project_id)
            else:
                _forget_worker_locked(owner_project_id)


def schedule_rebuild(project_id: str | None) -> None:
    """Queue one rebuild per project. At most one publisher/cleaner runs."""
    if not project_id:
        return
    # Existing unit tests must not rebuild against the live runtime DB.
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
        "GDDP_REVIEW_BRANCH_IN_TESTS"
    ):
        return
    with _rebuild_lock:
        _pending.add(project_id)
        _start_worker_locked(project_id)
