"""Git-backed verification for one mission feature result boundary."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitVerification:
    """Observed git facts and the resulting human-review decision."""

    result_sha: str
    result_object_type: str | None
    commit_exists: bool
    ancestry_holds: bool
    reachable: bool
    review_required: bool
    completion_quarantine_reason: str | None

    @property
    def verified(self) -> bool:
        return self.commit_exists and self.ancestry_holds and self.reachable

    def to_manifest(self) -> dict[str, object]:
        return {**asdict(self), "verified": self.verified}


def verify_git_result(
    repo_path: str | Path,
    *,
    base_sha: str,
    result_sha: str,
    engagement_branch: str,
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

    quarantine_reason = "; ".join(reasons) if reasons else None
    return GitVerification(
        result_sha=result_sha,
        result_object_type=object_type,
        commit_exists=commit_exists,
        ancestry_holds=ancestry_holds,
        reachable=reachable,
        review_required=quarantine_reason is not None,
        completion_quarantine_reason=quarantine_reason,
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
