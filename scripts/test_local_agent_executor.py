"""Tests for the worktree-only local agent executor."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import local_agent_executor as lae  # noqa: E402


def _init_repo(path: Path) -> str:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "README").write_text("base\n")
    subprocess.run(["git", "add", "README"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _packet(base_sha: str) -> str:
    return json.dumps(
        {
            "job_id": "job-abc",
            "goal": "Preserve this raw packet",
            "constraints": ["do not decompose me"],
            "expected_base_commit_sha": base_sha,
        },
        indent=2,
    )


def test_load_packet_requires_expected_base_commit_sha():
    with pytest.raises(ValueError, match="not valid JSON"):
        lae.load_packet("not-json")
    with pytest.raises(ValueError, match="must be an object"):
        lae.load_packet("[]")
    with pytest.raises(ValueError, match="expected_base_commit_sha"):
        lae.load_packet("{}")

    assert lae.load_packet('{"expected_base_commit_sha":"abc"}') == {
        "expected_base_commit_sha": "abc"
    }


def test_run_pipes_raw_packet_in_expected_detached_worktree(tmp_path, capsys):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    packet_raw = _packet(base_sha)
    observed: dict[str, object] = {}

    def fake_agent(argv, raw, worktree):
        observed.update(argv=argv, raw=raw, worktree=worktree)
        actual_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        detached = subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"],
            cwd=worktree,
            capture_output=True,
        ).returncode
        assert actual_head == base_sha
        assert detached == 1
        (worktree / "agent-change.txt").write_text("worktree only\n")
        return 0

    assert lae.run(
        packet_raw,
        ["chosen-agent", "--batch"],
        repo=repo,
        run_agent_fn=fake_agent,
    ) == 0

    captured = capsys.readouterr()
    worktree = observed["worktree"]
    assert observed["argv"] == ["chosen-agent", "--batch"]
    assert observed["raw"] == packet_raw
    assert "diff --git a/agent-change.txt b/agent-change.txt" in captured.out
    assert "worktree only" in captured.out
    assert not Path(worktree).exists()
    assert not (repo / "agent-change.txt").exists()


def test_run_agent_sends_agent_output_to_stderr(tmp_path, capfd):
    script = (
        "import pathlib,sys; "
        "pathlib.Path('change.txt').write_text(sys.stdin.read()); "
        "print('agent log')"
    )

    assert lae.run_agent(
        [sys.executable, "-c", script],
        '{"raw": true}\n',
        tmp_path,
    ) == 0

    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == "agent log\n"
    assert (tmp_path / "change.txt").read_text() == '{"raw": true}\n'


def test_run_removes_worktree_when_agent_fails(tmp_path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    worktrees: list[Path] = []

    def failing_agent(argv, raw, worktree):
        worktrees.append(worktree)
        raise RuntimeError("agent crashed")

    with pytest.raises(RuntimeError, match="agent crashed"):
        lae.run(
            _packet(base_sha),
            ["chosen-agent"],
            repo=repo,
            run_agent_fn=failing_agent,
        )

    assert len(worktrees) == 1
    assert not worktrees[0].exists()
    listing = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert str(worktrees[0]) not in listing


def test_run_returns_agent_failure_after_emitting_partial_diff(tmp_path, capsys):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)

    def failing_agent(argv, raw, worktree):
        (worktree / "partial.txt").write_text("salvage me\n")
        return 7

    assert lae.run(
        _packet(base_sha),
        ["chosen-agent"],
        repo=repo,
        run_agent_fn=failing_agent,
    ) == 7
    assert "partial.txt" in capsys.readouterr().out


def test_main_uses_agent_cli_from_its_argv(monkeypatch):
    run = MagicMock(return_value=0)
    monkeypatch.setattr(lae, "run", run)
    monkeypatch.setattr(lae.sys.stdin, "read", lambda: '{"packet":true}')

    assert lae.main(["--", "codex", "exec", "-"]) == 0

    run.assert_called_once_with(
        '{"packet":true}',
        ["codex", "exec", "-"],
    )
