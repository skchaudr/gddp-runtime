"""Rebuild one cumulative remote review branch per graph.

Whenever a durable result commit arrives, the runtime rebuilds
``gddp/review/<project_id>`` from ``origin/<target_branch>`` and then
deletes temporary ``gddp/result-*`` / ``gddp/attempt-*`` refs whose
commits are already represented on that review branch.

Graph completion stays human-owned. Publishing the review branch is
evidence delivery only.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from .repo_resolver import resolve_project_repo_checkout
from .results_store import DB_PATH

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
_worker_pool: list[threading.Thread] = []


@dataclass(frozen=True)
class ActiveResult:
    """One node's latest durable result commit, plus its transport refs."""

    node_id: str
    job_id: str
    session_id: str
    commit_sha: str
    depends_on: tuple[str, ...] = ()


@dataclass
class RebuildReport:
    project_id: str
    review_ref: str
    target_branch: str
    review_sha: str | None = None
    merged_shas: list[str] = field(default_factory=list)
    skipped_shas: list[str] = field(default_factory=list)
    cleaned_refs: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.review_sha)


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


def delete_temporary_ref(repo_path: Path, ref_name: str) -> bool:
    """Delete a temporary transport ref locally and on origin. Best-effort."""
    if not (
        ref_name.startswith(RESULT_REF_PREFIX)
        or ref_name.startswith(ATTEMPT_REF_PREFIX)
    ):
        return False
    local = _run_git(["update-ref", "-d", _heads_ref(ref_name)], cwd=repo_path)
    if local.returncode != 0:
        _run_git(["branch", "-D", ref_name], cwd=repo_path)
    remote = _run_git(
        ["push", "origin", "--delete", ref_name],
        cwd=repo_path,
        timeout=_PUSH_TIMEOUT,
    )
    remote_err = (remote.stderr or "") + (remote.stdout or "")
    remote_ok = remote.returncode == 0 or any(
        token in remote_err
        for token in (
            "remote ref does not exist",
            "does not exist",
            "No such remote",
            "not a git repository",
        )
    )
    return remote_ok or local.returncode == 0


def cleanup_preserved_refs(
    repo_path: Path,
    review_sha: str,
    extra_refs: Iterable[str] = (),
) -> list[str]:
    """Delete temp refs whose commit is already on the review branch."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for ref_name in list(extra_refs) + list_temporary_refs(repo_path):
        if ref_name in seen:
            continue
        seen.add(ref_name)
        sha = ref_commit(repo_path, ref_name)
        if not sha:
            continue
        if not commit_is_ancestor(repo_path, sha, review_sha):
            continue
        if delete_temporary_ref(repo_path, ref_name):
            cleaned.append(ref_name)
    return cleaned


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


def _merge_commit(worktree: Path, sha: str) -> bool:
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
        return True
    _run_git(["merge", "--abort"], cwd=worktree)
    return False


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
    try:
        for item in ordered:
            if _merge_commit(worktree, item.commit_sha):
                report.merged_shas.append(item.commit_sha)
            else:
                report.skipped_shas.append(item.commit_sha)
        head = _run_git(["rev-parse", "HEAD"], cwd=worktree)
        if head.returncode != 0 or not head.stdout.strip():
            report.error = "could not read rebuilt HEAD"
            return report
        report.review_sha = head.stdout.strip()
        push = _run_git(
            [
                "push",
                "--force",
                "origin",
                f"HEAD:refs/heads/{review_ref}",
            ],
            cwd=worktree,
            timeout=_PUSH_TIMEOUT,
        )
        if push.returncode != 0:
            report.error = f"force-push failed: {(push.stderr or push.stdout).strip()}"
            return report
        extra = [result_ref_name(item.job_id, item.session_id) for item in ordered]
        report.cleaned_refs = cleanup_preserved_refs(
            repo_path, report.review_sha, extra_refs=extra
        )
        return report
    finally:
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


def _worker_loop() -> None:
    while True:
        with _rebuild_lock:
            if not _pending:
                return
            project_id = next(iter(_pending))
            _pending.discard(project_id)
            _in_flight.add(project_id)
        try:
            report = rebuild_project(project_id)
            if report.ok:
                print(
                    f"[review-branch] {project_id}: "
                    f"{report.review_ref} @ {report.review_sha[:12]} "
                    f"(merged={len(report.merged_shas)} "
                    f"skipped={len(report.skipped_shas)} "
                    f"cleaned={len(report.cleaned_refs)})"
                )
            else:
                print(
                    f"[review-branch] {project_id}: rebuild failed: {report.error}"
                )
        except Exception as exc:  # noqa: BLE001 — never break the caller
            print(f"[review-branch] {project_id}: rebuild crashed: {exc}")
        with _rebuild_lock:
            _in_flight.discard(project_id)
            if not _pending:
                return


def schedule_rebuild(project_id: str | None) -> None:
    """Offload a rebuild. Coalesces in-flight work for the same project."""
    if not project_id:
        return
    # Existing unit tests must not rebuild against the live runtime DB.
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
        "GDDP_REVIEW_BRANCH_IN_TESTS"
    ):
        return
    with _rebuild_lock:
        if project_id in _in_flight:
            _pending.add(project_id)
            return
        if project_id in _pending:
            return
        _pending.add(project_id)
        _worker_pool[:] = [thread for thread in _worker_pool if thread.is_alive()]
        worker = threading.Thread(
            target=_worker_loop,
            name=f"gddp-review-{project_id}",
            daemon=True,
        )
        _worker_pool.append(worker)
        worker.start()
