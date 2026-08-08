from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.adapters.mission_push_guard import (
    install_git_push_guard,
    run_guarded_git,
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
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        text=True,
        capture_output=True,
        check=True,
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Push Guard Test")
    _git(repo, "config", "user.email", "push-guard@example.invalid")
    _git(repo, "remote", "add", "origin", str(remote))
    (repo / "tracked.txt").write_text("feature\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "feature result")
    _git(repo, "switch", "-c", "gddp/engagement")
    return repo, remote, _git(repo, "rev-parse", "HEAD")


def test_guard_allows_only_engagement_refspec_and_audits_origin_reachability(
    tmp_path, monkeypatch
):
    repo, remote, result_sha = _repo_with_remote(tmp_path)
    audit_path = tmp_path / "push-audit.jsonl"
    monkeypatch.chdir(repo)

    returncode = run_guarded_git(
        ["push", "origin", "HEAD:refs/heads/gddp/engagement"],
        env={
            "GDDP_REAL_GIT": subprocess.run(
                ["which", "git"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip(),
            "GDDP_ENGAGEMENT_BRANCH": "gddp/engagement",
            "GDDP_PUSH_AUDIT_PATH": str(audit_path),
        },
    )

    assert returncode == 0
    assert _git(remote, "rev-parse", "refs/heads/gddp/engagement") == result_sha
    audit = json.loads(audit_path.read_text())
    assert audit["argv"] == [
        "git",
        "push",
        "origin",
        "HEAD:refs/heads/gddp/engagement",
    ]
    assert audit["allowed"] is True
    assert audit["commit_sha"] == result_sha
    assert audit["returncode"] == 0
    assert audit["origin_containing_refs"] == ["origin/gddp/engagement"]


@pytest.mark.parametrize(
    "push_arguments",
    [
        ["origin", "HEAD:refs/heads/main"],
        ["origin", "HEAD:refs/heads/release/2026"],
        ["--force", "origin", "HEAD:refs/heads/gddp/engagement"],
        ["-f", "origin", "HEAD:refs/heads/gddp/engagement"],
        ["--force-with-lease", "origin", "HEAD:refs/heads/gddp/engagement"],
        ["origin", "+HEAD:refs/heads/gddp/engagement"],
    ],
)
def test_guard_rejects_shared_destinations_and_every_force_push_form(
    tmp_path, monkeypatch, push_arguments
):
    repo, remote, _result_sha = _repo_with_remote(tmp_path)
    audit_path = tmp_path / "push-audit.jsonl"
    monkeypatch.chdir(repo)

    returncode = run_guarded_git(
        ["push", *push_arguments],
        env={
            "GDDP_REAL_GIT": subprocess.run(
                ["which", "git"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip(),
            "GDDP_ENGAGEMENT_BRANCH": "gddp/engagement",
            "GDDP_PUSH_AUDIT_PATH": str(audit_path),
        },
    )

    assert returncode != 0
    refs = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/heads"],
        cwd=remote,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert refs == ""
    audit = json.loads(audit_path.read_text())
    assert audit["argv"] == ["git", "push", *push_arguments]
    assert audit["allowed"] is False
    assert audit["returncode"] != 0
    assert audit["origin_containing_refs"] == []


@pytest.mark.parametrize(
    "push_arguments",
    [
        ["origin", "HEAD:refs/heads/main"],
        ["--force", "origin", "HEAD:refs/heads/gddp/engagement"],
    ],
)
def test_absolute_git_path_cannot_bypass_push_guard(
    tmp_path, push_arguments
):
    repo, remote, _result_sha = _repo_with_remote(tmp_path)
    audit_path = tmp_path / "push-audit.jsonl"
    guarded_env = install_git_push_guard(
        tmp_path / "git-guard",
        engagement_branch="gddp/engagement",
        audit_path=audit_path,
        base_env=os.environ,
    )

    process = subprocess.run(
        [guarded_env["GDDP_REAL_GIT"], "push", *push_arguments],
        cwd=repo,
        env=guarded_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert process.returncode != 0
    assert "mission push rejected" in process.stderr
    refs = _git(remote, "for-each-ref", "--format=%(refname)", "refs/heads")
    assert refs == ""
    audit = json.loads(audit_path.read_text())
    assert audit["allowed"] is False
    assert audit["returncode"] != 0
