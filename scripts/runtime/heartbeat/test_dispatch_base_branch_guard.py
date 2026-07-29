"""test_dispatch_base_branch_guard.py — Preflight guard on base-branch drift.

Remote Jules executors branch from a fixed remote branch while the runner binds
each job to local HEAD. On 2026-07-29 a rig dispatched five nodes from an
unmerged feature branch; Jules built every patch on main, and all of them were
rejected at reconcile hours later for base-SHA mismatch. Dispatch must refuse
up front instead.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.runtime.heartbeat.dispatcher import executor_preflight_error


def _repo_on_branch(tmp_path, branch):
    repo = tmp_path / "checkout"
    repo.mkdir()

    def git(*args):
        subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True
        )

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (repo / "f.txt").write_text("x")
    git("add", "f.txt")
    git("commit", "-qm", "init")
    if branch != "main":
        git("checkout", "-q", "-b", branch)
    return str(repo)


@pytest.mark.parametrize("executor", ["jules_api", "jules_cli", "jules"])
def test_remote_executor_refuses_non_main_checkout(tmp_path, monkeypatch, executor):
    monkeypatch.delenv("GDDP_EXECUTOR_OVERRIDE", raising=False)
    monkeypatch.delenv("GDDP_JULES_STARTING_BRANCH", raising=False)
    monkeypatch.setenv("JULES_API_KEY", "test-key")
    repo_path = _repo_on_branch(tmp_path, "feat/some-branch")

    error = executor_preflight_error(executor, "owner/repo", repo_path)

    assert error is not None
    assert "feat/some-branch" in error
    assert "main" in error


def test_remote_executor_allows_main_checkout(tmp_path, monkeypatch):
    monkeypatch.delenv("GDDP_EXECUTOR_OVERRIDE", raising=False)
    monkeypatch.delenv("GDDP_JULES_STARTING_BRANCH", raising=False)
    monkeypatch.setenv("JULES_API_KEY", "test-key")
    repo_path = _repo_on_branch(tmp_path, "main")

    assert executor_preflight_error("jules_api", "owner/repo", repo_path) is None


def test_guard_honors_configured_starting_branch(tmp_path, monkeypatch):
    """A rig deliberately running off another branch configures it, not drifts."""
    monkeypatch.delenv("GDDP_EXECUTOR_OVERRIDE", raising=False)
    monkeypatch.setenv("GDDP_JULES_STARTING_BRANCH", "develop")
    monkeypatch.setenv("JULES_API_KEY", "test-key")
    repo_path = _repo_on_branch(tmp_path, "develop")

    assert executor_preflight_error("jules_api", "owner/repo", repo_path) is None


def test_local_executor_is_unaffected(tmp_path, monkeypatch):
    """local_subprocess runs in a worktree off local HEAD; branch is irrelevant."""
    monkeypatch.delenv("GDDP_EXECUTOR_OVERRIDE", raising=False)
    monkeypatch.setenv("GDDP_LOCAL_SUBPROCESS_ARGV", '["/bin/true"]')
    monkeypatch.setenv("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR", str(tmp_path / "spool"))
    repo_path = _repo_on_branch(tmp_path, "feat/some-branch")

    assert (
        executor_preflight_error("local_subprocess", "owner/repo", repo_path)
        is None
    )


def test_missing_repo_path_does_not_block_dispatch(monkeypatch):
    """Reconcile is already optional without a local path; do not regress it."""
    monkeypatch.delenv("GDDP_EXECUTOR_OVERRIDE", raising=False)
    monkeypatch.delenv("GDDP_JULES_STARTING_BRANCH", raising=False)
    monkeypatch.setenv("JULES_API_KEY", "test-key")

    assert executor_preflight_error("jules_api", "owner/repo", None) is None
