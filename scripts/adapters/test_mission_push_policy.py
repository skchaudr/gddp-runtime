from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.adapters.mission_push_policy import (
    install_push_guard,
    read_push_audit,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _repo_with_remote(tmp_path: Path) -> tuple[Path, Path, str]:
    remote = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(tmp_path, "init", "-b", "main", str(repo))
    _git(repo, "config", "user.name", "Push Policy Test")
    _git(repo, "config", "user.email", "push-policy@example.invalid")
    _git(repo, "remote", "add", "origin", str(remote))
    (repo / "tracked.txt").write_text("base\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "base")
    _git(repo, "push", "origin", "main")
    _git(repo, "switch", "-c", "gddp/engagement")
    return repo, remote, _git(repo, "rev-parse", "HEAD")


def _guarded_git(
    repo: Path,
    guard_dir: Path,
    audit_path: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{guard_dir}{os.pathsep}{env['PATH']}"
    env["GDDP_ENGAGEMENT_BRANCH"] = "gddp/engagement"
    env["GDDP_PUSH_AUDIT_PATH"] = str(audit_path)
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_guard_allows_only_explicit_engagement_refspec_and_audits_push(tmp_path):
    repo, remote, _base = _repo_with_remote(tmp_path)
    (repo / "tracked.txt").write_text("feature\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "feature")
    head = _git(repo, "rev-parse", "HEAD")
    audit_path = tmp_path / "push-audit.jsonl"
    guard_dir = install_push_guard(tmp_path / "guard")

    pushed = _guarded_git(
        repo,
        guard_dir,
        audit_path,
        "push",
        "origin",
        "HEAD:refs/heads/gddp/engagement",
    )

    assert pushed.returncode == 0
    assert _git(remote, "rev-parse", "refs/heads/gddp/engagement") == head
    assert _git(repo, "branch", "-r", "--contains", head) == (
        "origin/gddp/engagement"
    )
    records = read_push_audit(audit_path)
    assert len(records) == 1
    assert records[0]["allowed"] is True
    assert records[0]["destination"] == "refs/heads/gddp/engagement"
    assert records[0]["head"] == head
    assert records[0]["returncode"] == 0


@pytest.mark.parametrize(
    "args",
    [
        ("push", "origin", "HEAD:refs/heads/main"),
        ("push", "origin", "HEAD:refs/heads/release/1.0"),
        ("push", "origin", "--force", "HEAD:refs/heads/gddp/engagement"),
        ("push", "-f", "origin", "HEAD:refs/heads/gddp/engagement"),
        (
            "push",
            "--force-with-lease",
            "origin",
            "HEAD:refs/heads/gddp/engagement",
        ),
        ("push", "origin", "+HEAD:refs/heads/gddp/engagement"),
        ("push", "origin", "gddp/engagement"),
    ],
)
def test_guard_rejects_shared_force_and_ambiguous_pushes(tmp_path, args):
    repo, remote, _base = _repo_with_remote(tmp_path)
    guard_dir = install_push_guard(tmp_path / "guard")
    audit_path = tmp_path / "push-audit.jsonl"
    main_before = _git(remote, "rev-parse", "refs/heads/main")

    attempted = _guarded_git(repo, guard_dir, audit_path, *args)

    assert attempted.returncode != 0
    assert "push policy rejected" in attempted.stderr
    assert _git(remote, "rev-parse", "refs/heads/main") == main_before
    records = read_push_audit(audit_path)
    assert records[-1]["allowed"] is False
    assert records[-1]["returncode"] is None


def test_push_audit_is_valid_jsonl_after_multiple_invocations(tmp_path):
    repo, _remote, _base = _repo_with_remote(tmp_path)
    guard_dir = install_push_guard(tmp_path / "guard")
    audit_path = tmp_path / "push-audit.jsonl"

    _guarded_git(
        repo,
        guard_dir,
        audit_path,
        "push",
        "origin",
        "HEAD:refs/heads/gddp/engagement",
    )
    _guarded_git(repo, guard_dir, audit_path, "push", "origin", "main")

    assert len(audit_path.read_text().splitlines()) == 2
    assert all(
        isinstance(json.loads(line), dict)
        for line in audit_path.read_text().splitlines()
    )
