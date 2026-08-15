"""
graph_delivery.py — publish one legible branch for a finished graph.

Each node's executor branches from the previous node's result commit, so a
graph's result refs form one spine; the terminal commit contains every other
node's work as an ancestor. This finds that commit, publishes it under a
stable branch, and — opt-in, never automatic — retires the transport refs
that fed it, once (and only once) that branch is confirmed to hold it. A ref
belongs to this graph only when its node_id is a member of the graph's own
node ids (via GraphReader), never by ref-name pattern alone. Analysis fetches
land in a private namespace that is always cleared; refs/remotes/origin/* is
never written here.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from scripts.runtime.heartbeat.graph_reader import GraphReader

_RESULT_RE = re.compile(
    r"^gddp/result-(?P<job_id>[^-]+)-(?P=job_id)-(?P<node_id>.+)-attempt-\d+-[0-9a-f]+$"
)
_ATTEMPT_RE = re.compile(r"^gddp/attempt-(?P<job_id>[^-]+)-attempt-\d+$")
_TMP_NS = "refs/gddp-delivery-tmp"

class GraphDeliveryError(Exception):
    """Fatal: spine forked, or a publish/cleanup precondition unmet. Never partial."""

def _git(repo: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=timeout, check=False,
    )

def _node_ids(config_root: Path, project_id: str) -> set[str]:
    graph = GraphReader(config_path=str(config_root)).load_project(project_id)
    return {n["id"] for n in graph.nodes if n.get("id")}

def _ls_remote(repo: Path, pattern: str) -> dict[str, str]:
    proc = _git(repo, "ls-remote", "--heads", "origin", pattern, timeout=60)
    if proc.returncode != 0:
        raise GraphDeliveryError(f"ls-remote failed: {proc.stderr.strip()}")
    refs = {}
    for line in proc.stdout.splitlines():
        sha, ref = line.split("\t", 1)
        refs[ref[len("refs/heads/"):]] = sha
    return refs

def _clear_tmp_refs(repo: Path) -> None:
    for ref in _git(repo, "for-each-ref", "--format=%(refname)", _TMP_NS).stdout.splitlines():
        _git(repo, "update-ref", "-d", ref)

def _fetch(repo: Path, refs: list[str]) -> None:
    """Land objects locally under a private namespace; caller clears it after."""
    if not refs:
        return
    specs = [f"+refs/heads/{r}:{_TMP_NS}/{r}" for r in refs]
    proc = _git(repo, "fetch", "origin", *specs, timeout=120)
    if proc.returncode != 0:
        raise GraphDeliveryError(f"fetch failed: {proc.stderr.strip()}")

def _is_empty_commit(repo: Path, sha: str) -> bool:
    tree = _git(repo, "rev-parse", f"{sha}^{{tree}}").stdout.strip()
    parent = _git(repo, "rev-parse", f"{sha}^1")
    if parent.returncode != 0:
        return False  # root commit — nothing to diff against, treat as content
    ptree = _git(repo, "rev-parse", f"{parent.stdout.strip()}^{{tree}}").stdout.strip()
    return bool(tree) and tree == ptree

def collect_result_commits(repo: Path, config_root: Path, project_id: str):
    """(ref, node_id, sha, job_id) scoped to this graph's nodes.

    Fetch always lands under a private namespace and is always cleared after,
    win or lose — refs/remotes/origin/* is untouched.
    """
    node_ids = _node_ids(config_root, project_id)
    scoped = []
    for ref, sha in _ls_remote(repo, "refs/heads/gddp/result-*").items():
        m = _RESULT_RE.match(ref)
        if m and m.group("node_id") in node_ids:
            scoped.append((ref, m.group("node_id"), sha, m.group("job_id")))
    try:
        _fetch(repo, [ref for ref, *_ in scoped])
    finally:
        _clear_tmp_refs(repo)
    return scoped

def find_delivery_commit(repo: Path, config_root: Path, project_id: str):
    """(sha, non_empty_candidates); raises, naming divergent shas, on a fork."""
    scoped = collect_result_commits(repo, config_root, project_id)
    if not scoped:
        raise GraphDeliveryError(f"no result refs found for graph {project_id!r}")
    nonempty = [
        (ref, node, sha) for ref, node, sha, _job in scoped
        if not _is_empty_commit(repo, sha)
    ]
    if not nonempty:
        raise GraphDeliveryError(f"all result commits for {project_id!r} are empty")
    for ref, node, sha in nonempty:
        if all(
            sha == other or _git(repo, "merge-base", "--is-ancestor", other, sha).returncode == 0
            for _, _, other in nonempty
        ):
            return sha, nonempty
    divergent = "\n".join(f"  {node}  {sha[:12]}  ({ref})" for ref, node, sha in nonempty)
    raise GraphDeliveryError(
        f"spine forked for graph {project_id!r} — no single commit descends from "
        f"every node's result; never publishing a partial branch:\n{divergent}"
    )

def publish(repo: Path, config_root: Path, project_id: str) -> tuple[str, str]:
    """Push the delivery commit to review/<project_id>; verify it landed."""
    sha, _ = find_delivery_commit(repo, config_root, project_id)
    branch = f"review/{project_id}"
    push = _git(repo, "push", "origin", f"{sha}:refs/heads/{branch}", timeout=60)
    if push.returncode != 0:
        raise GraphDeliveryError(f"publish push failed: {push.stderr.strip()}")
    landed = _ls_remote(repo, f"refs/heads/{branch}").get(branch)
    if landed != sha:
        raise GraphDeliveryError(
            f"publish unverifiable: origin/{branch} is {landed!r}, expected {sha}"
        )
    return branch, sha

def _require_delivered(repo: Path, project_id: str, sha: str) -> None:
    """Refuse unless origin/review/<project_id> exists and already holds sha."""
    branch = f"review/{project_id}"
    landed = _ls_remote(repo, f"refs/heads/{branch}").get(branch)
    if landed is None:
        raise GraphDeliveryError(
            f"refusing cleanup for {project_id!r}: origin/{branch} does not exist — publish first"
        )
    if landed == sha:
        return
    try:
        _fetch(repo, [branch])
        ok = _git(repo, "merge-base", "--is-ancestor", sha, landed).returncode == 0
    finally:
        _clear_tmp_refs(repo)
    if not ok:
        raise GraphDeliveryError(
            f"refusing cleanup for {project_id!r}: origin/{branch} ({landed[:12]}) does not "
            f"contain the delivery commit ({sha[:12]}) — publish first"
        )

def cleanup_transport_refs(
    repo: Path, config_root: Path, project_id: str, *, delete: bool = False
) -> list[str]:
    """List (default) or delete transport refs; refuses (deletes nothing) unless
    review/<project_id> already holds the delivery commit — dry run checks too."""
    scoped = collect_result_commits(repo, config_root, project_id)
    sha, _ = find_delivery_commit(repo, config_root, project_id)
    _require_delivered(repo, project_id, sha)
    job_ids = {job_id for *_rest, job_id in scoped}
    result_refs = [ref for ref, *_rest in scoped]
    attempt_refs = [
        ref for ref in _ls_remote(repo, "refs/heads/gddp/attempt-*")
        if (m := _ATTEMPT_RE.match(ref)) and m.group("job_id") in job_ids
    ]
    targets = sorted(result_refs + attempt_refs)
    if not delete:
        for ref in targets:
            print(f"  would delete: {ref}")
        print(f"{len(targets)} ref(s) would be deleted (dry run — pass delete=True to act)")
        return targets
    if targets:
        proc = _git(repo, "push", "origin", *(f":refs/heads/{r}" for r in targets), timeout=60)
        if proc.returncode != 0:
            raise GraphDeliveryError(f"cleanup push failed: {proc.stderr.strip()}")
    print(f"deleted {len(targets)} ref(s)")
    return targets

def main(argv: list[str] | None = None) -> int:
    """Argv boundary: publish/cleanup for one graph, given its config root."""
    p = argparse.ArgumentParser(description="Publish or clean up one graph's delivery.")
    p.add_argument("action", choices=["publish", "cleanup"])
    p.add_argument("project_id")
    p.add_argument("--config-root", required=True, type=Path)
    p.add_argument("--delete", action="store_true", help="cleanup only: actually delete refs")
    args = p.parse_args(argv)
    repo = Path(GraphReader(config_path=str(args.config_root)).load_project(args.project_id).repo)
    try:
        if args.action == "publish":
            branch, sha = publish(repo, args.config_root, args.project_id)
            print(f"published {branch} -> {sha}")
        else:
            cleanup_transport_refs(repo, args.config_root, args.project_id, delete=args.delete)
    except GraphDeliveryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
