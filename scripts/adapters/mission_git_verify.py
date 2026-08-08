"""Git-backed verification for one mission feature result boundary."""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

_NODE_TRAILER = re.compile(r"^GDDP-Node-Id:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class GitVerification:
    """Observed git facts and the resulting human-review decision."""

    result_sha: str
    result_object_type: str | None
    commit_exists: bool
    ancestry_holds: bool
    reachable: bool
    origin_reachable: bool | None
    origin_containing_refs: tuple[str, ...]
    trailer_node_ids: tuple[str, ...]
    trailer_matches: bool | None
    review_required: bool
    completion_quarantine_reason: str | None

    @property
    def verified(self) -> bool:
        return (
            self.commit_exists
            and self.ancestry_holds
            and self.reachable
            and self.origin_reachable is not False
            and self.trailer_matches is not False
        )

    def to_manifest(self) -> dict[str, object]:
        return {**asdict(self), "verified": self.verified}


@dataclass(frozen=True)
class EngagementHistoryVerification:
    """Observed base-to-branch commit history for one engagement."""

    base_sha: str
    engagement_branch: str
    demanded_node_ids: tuple[str, ...]
    commit_shas: tuple[str, ...]
    node_ids: tuple[str | None, ...]
    verified: bool
    completion_quarantine_reason: str | None

    def to_manifest(self) -> dict[str, object]:
        return asdict(self)


def verify_git_result(
    repo_path: str | Path,
    *,
    base_sha: str,
    result_sha: str,
    engagement_branch: str,
    origin_remote: str | None = None,
    expected_node_id: str | None = None,
) -> GitVerification:
    """Verify a claimed result against real objects in ``repo_path``.

    The claim is always retained in the returned value. Git command failures
    are evidence for review, not exceptions and never silently become success.
    """

    repo = Path(repo_path).resolve()
    object_type = _object_type(repo, result_sha)
    commit_exists = object_type == "commit"
    ancestry_holds = bool(
        commit_exists
        and base_sha
        and _is_ancestor(repo, base_sha, result_sha)
    )
    branch_tip = (
        _resolve_local_branch(repo, engagement_branch)
        if commit_exists and engagement_branch
        else None
    )
    reachable = bool(
        branch_tip
        and _is_ancestor(repo, result_sha, branch_tip)
    )
    origin_containing_refs = (
        _remote_branches_containing(repo, result_sha)
        if commit_exists and origin_remote
        else ()
    )
    expected_origin_ref = (
        f"{origin_remote}/{engagement_branch}" if origin_remote else None
    )
    origin_reachable = (
        expected_origin_ref in origin_containing_refs
        if expected_origin_ref is not None
        else None
    )
    trailer_node_ids = (
        _commit_node_trailers(repo, result_sha) if commit_exists else ()
    )
    trailer_matches = (
        trailer_node_ids == (expected_node_id,)
        if expected_node_id is not None
        else None
    )

    reasons: list[str] = []
    if not commit_exists:
        if object_type is None:
            reasons.append(f"result commit {result_sha} does not exist")
        else:
            reasons.append(
                f"result {result_sha} resolves to {object_type}, not a commit"
            )
    else:
        if not ancestry_holds:
            reasons.append(
                f"result {result_sha} does not descend from base {base_sha}"
            )
        if branch_tip is None:
            reasons.append(
                f"engagement branch {engagement_branch} cannot be resolved"
            )
        elif not reachable:
            reasons.append(
                f"result {result_sha} is not reachable from engagement "
                f"branch {engagement_branch}"
            )
        if expected_origin_ref is not None and not origin_reachable:
            reasons.append(
                f"result {result_sha} is not reachable from origin ref "
                f"{expected_origin_ref}"
            )
        if trailer_matches is False:
            reasons.append(
                f"result {result_sha} must have exactly one "
                f"GDDP-Node-Id trailer for {expected_node_id}; observed "
                f"{list(trailer_node_ids)!r}"
            )

    quarantine_reason = "; ".join(reasons) if reasons else None
    return GitVerification(
        result_sha=result_sha,
        result_object_type=object_type,
        commit_exists=commit_exists,
        ancestry_holds=ancestry_holds,
        reachable=reachable,
        origin_reachable=origin_reachable,
        origin_containing_refs=origin_containing_refs,
        trailer_node_ids=trailer_node_ids,
        trailer_matches=trailer_matches,
        review_required=quarantine_reason is not None,
        completion_quarantine_reason=quarantine_reason,
    )


def verify_engagement_history(
    repo_path: str | Path,
    *,
    base_sha: str,
    engagement_branch: str,
    demanded_node_ids: tuple[str, ...],
) -> EngagementHistoryVerification:
    """Require a bijection between demanded nodes and branch-range commits."""
    repo = Path(repo_path).resolve()
    branch_tip = _resolve_local_branch(repo, engagement_branch)
    commits = (
        _commits_in_range(repo, base_sha, branch_tip)
        if branch_tip is not None
        else ()
    )
    trailers = tuple(
        _commit_node_trailers(repo, commit_sha) for commit_sha in commits
    )
    node_ids = tuple(
        values[0] if len(values) == 1 else None for values in trailers
    )
    reasons: list[str] = []
    if branch_tip is None:
        reasons.append(
            f"engagement branch {engagement_branch} cannot be resolved"
        )
    if len(commits) != len(demanded_node_ids):
        reasons.append(
            "engagement history must contain exactly one commit per demanded "
            f"node; observed {len(commits)} commits for "
            f"{len(demanded_node_ids)} nodes"
        )
    malformed = [
        commit_sha
        for commit_sha, values in zip(commits, trailers, strict=True)
        if len(values) != 1
    ]
    if malformed:
        reasons.append(
            "every engagement commit must have exactly one GDDP-Node-Id "
            f"trailer; malformed commits {malformed!r}"
        )
    if node_ids != demanded_node_ids:
        reasons.append(
            "engagement commit trailers must match demanded node ids in "
            f"topological order; demanded {list(demanded_node_ids)!r}, "
            f"observed {list(node_ids)!r}"
        )
    reason = "; ".join(reasons) if reasons else None
    return EngagementHistoryVerification(
        base_sha=base_sha,
        engagement_branch=engagement_branch,
        demanded_node_ids=demanded_node_ids,
        commit_shas=commits,
        node_ids=node_ids,
        verified=reason is None,
        completion_quarantine_reason=reason,
    )


def _object_type(repo_path: Path, object_name: str) -> str | None:
    process = _run_git(repo_path, "cat-file", "-t", object_name)
    if process is None or process.returncode != 0:
        return None
    object_type = process.stdout.strip()
    return object_type or None


def _is_ancestor(repo_path: Path, base_sha: str, result_sha: str) -> bool:
    process = _run_git(
        repo_path, "merge-base", "--is-ancestor", base_sha, result_sha
    )
    return process is not None and process.returncode == 0


def _resolve_local_branch(repo_path: Path, branch_name: str) -> str | None:
    process = _run_git(
        repo_path,
        "rev-parse",
        "--verify",
        f"refs/heads/{branch_name}^{{commit}}",
    )
    if process is None or process.returncode != 0:
        return None
    commit = process.stdout.strip()
    return commit or None


def _remote_branches_containing(
    repo_path: Path, result_sha: str
) -> tuple[str, ...]:
    process = _run_git(
        repo_path,
        "branch",
        "-r",
        "--contains",
        result_sha,
        "--format=%(refname:short)",
    )
    if process is None or process.returncode != 0:
        return ()
    return tuple(
        line.strip()
        for line in process.stdout.splitlines()
        if line.strip()
    )


def _remote_branch_tip(
    repo_path: Path, remote: str, branch_name: str
) -> str | None:
    """True remote tip via ``git ls-remote`` (no local ref update).

    Returns None when offline / remote missing / empty. Does not fetch.
    """
    process = _run_git(
        repo_path,
        "ls-remote",
        remote,
        f"refs/heads/{branch_name}",
    )
    if process is None or process.returncode != 0:
        return None
    for line in process.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].endswith(f"refs/heads/{branch_name}"):
            tip = parts[0].strip()
            return tip or None
        if len(parts) >= 1 and parts[0].strip():
            # Single matching ref: "<sha>\trefs/heads/<branch>"
            return parts[0].strip()
    return None


def _commit_node_trailers(
    repo_path: Path, commit_sha: str
) -> tuple[str, ...]:
    process = _run_git(repo_path, "show", "-s", "--format=%B", commit_sha)
    if process is None or process.returncode != 0:
        return ()
    return tuple(
        match.group(1).strip()
        for match in _NODE_TRAILER.finditer(process.stdout)
    )


def _commits_in_range(
    repo_path: Path, base_sha: str, branch_tip: str
) -> tuple[str, ...]:
    process = _run_git(
        repo_path,
        "rev-list",
        "--reverse",
        f"{base_sha}..{branch_tip}",
    )
    if process is None or process.returncode != 0:
        return ()
    return tuple(
        line.strip()
        for line in process.stdout.splitlines()
        if line.strip()
    )


def _run_git(
    repo_path: Path, *args: str
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
