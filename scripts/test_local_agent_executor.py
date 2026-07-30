"""Tests for the worktree-only local agent executor (commit-ref handoff)."""

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


def _packet(base_sha: str, **extra) -> str:
    body = {
        "job_id": "job-abc",
        "execution_attempt_id": "job-abc:attempt:1",
        "goal": "Preserve this raw packet",
        "constraints": ["do not decompose me"],
        "expected_base_commit_sha": base_sha,
    }
    body.update(extra)
    return json.dumps(body, indent=2)


def _parse_handoff(stdout: str) -> dict:
    text = stdout.strip()
    assert text, "expected commit-ref handoff on stdout"
    # last non-empty line is the JSON object
    line = [ln for ln in text.splitlines() if ln.strip()][-1]
    payload = json.loads(line)
    assert payload["schema"] == lae.HANDOFF_SCHEMA
    return payload


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
    assert "diff --git" not in captured.out
    handoff = _parse_handoff(captured.out)
    assert handoff["result_commit_sha"]
    assert handoff["result_ref"] == "gddp/attempt-job-abc-attempt-1"
    assert handoff["expected_base_commit_sha"] == base_sha
    assert handoff["worktree_path"] is None

    # Object identity lives in the main repo via the durable ref.
    resolved = subprocess.run(
        ["git", "rev-parse", handoff["result_ref"]],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert resolved == handoff["result_commit_sha"]
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, handoff["result_commit_sha"]],
        cwd=repo,
        check=False,
    )
    assert ancestor.returncode == 0
    assert not Path(worktree).exists()
    assert not (repo / "agent-change.txt").exists()


def test_run_defaults_to_the_checkout_that_launched_it(tmp_path, capsys, monkeypatch):
    target_repo = tmp_path / "MyAPI"
    base_sha = _init_repo(target_repo)
    monkeypatch.chdir(target_repo)

    def fake_agent(argv, raw, worktree):
        (worktree / "agent-change.txt").write_text("target checkout\n")
        return 0

    assert lae.run(
        _packet(base_sha),
        ["chosen-agent"],
        run_agent_fn=fake_agent,
    ) == 0

    handoff = _parse_handoff(capsys.readouterr().out)
    resolved = subprocess.run(
        ["git", "rev-parse", handoff["result_ref"]],
        cwd=target_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert resolved == handoff["result_commit_sha"]


def test_persist_result_creates_ref_before_cleanup(tmp_path, capsys):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)

    def fake_agent(argv, raw, worktree):
        (worktree / "change.txt").write_text("saved\n")
        return 0

    assert lae.run(
        _packet(base_sha),
        ["chosen-agent"],
        repo=repo,
        run_agent_fn=fake_agent,
    ) == 0
    handoff = _parse_handoff(capsys.readouterr().out)
    assert handoff["result_commit_sha"]
    assert (
        subprocess.run(
            ["git", "cat-file", "-t", handoff["result_commit_sha"]],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == "commit"
    )
    assert (
        subprocess.run(
            ["git", "rev-parse", handoff["result_ref"]],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == handoff["result_commit_sha"]
    )


def test_persist_result_refuses_to_overwrite_a_reused_attempt_ref(tmp_path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    packet = json.loads(_packet(base_sha))

    first_wt = lae.create_worktree(repo, base_sha)
    (first_wt / "first.txt").write_text("first attempt\n")
    first = lae.persist_result(first_wt, packet)
    assert first["result_commit_sha"]
    lae.remove_worktree(repo, first_wt)

    # Same execution_attempt_id → same ref name → must not clobber attempt one.
    second_wt = lae.create_worktree(repo, base_sha)
    (second_wt / "second.txt").write_text("second attempt\n")
    second = lae.persist_result(second_wt, packet)

    assert second["result_commit_sha"] is None
    assert second["worktree_path"] == str(second_wt)
    assert second["error"]
    assert first["result_ref"] in second["error"]

    resolved = subprocess.run(
        ["git", "rev-parse", first["result_ref"]],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert resolved == first["result_commit_sha"]

    lae.remove_worktree(repo, second_wt)


def test_persist_failure_keeps_worktree_and_records_path(tmp_path, capsys, monkeypatch):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    observed: dict[str, Path] = {}

    def fake_agent(argv, raw, worktree):
        observed["worktree"] = worktree
        (worktree / "partial.txt").write_text("keep me\n")
        return 0

    def boom(worktree, packet):
        return {
            "schema": lae.HANDOFF_SCHEMA,
            "result_commit_sha": None,
            "result_ref": None,
            "expected_base_commit_sha": packet["expected_base_commit_sha"],
            "worktree_path": str(worktree),
            "error": "forced persist failure",
        }

    monkeypatch.setattr(lae, "persist_result", boom)

    assert lae.run(
        _packet(base_sha),
        ["chosen-agent"],
        repo=repo,
        run_agent_fn=fake_agent,
    ) == 1

    handoff = _parse_handoff(capsys.readouterr().out)
    assert handoff["result_commit_sha"] is None
    assert handoff["worktree_path"] == str(observed["worktree"])
    assert handoff["error"] == "forced persist failure"
    assert Path(handoff["worktree_path"]).exists()
    assert (Path(handoff["worktree_path"]) / "partial.txt").read_text() == "keep me\n"


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


def test_run_returns_agent_failure_after_persisting_partial_result(tmp_path, capsys):
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
    handoff = _parse_handoff(capsys.readouterr().out)
    assert handoff["result_commit_sha"]
    assert handoff["result_ref"]
    # Partial evidence is durable even though agent failed.
    tree = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", handoff["result_commit_sha"]],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "partial.txt" in tree


def test_main_uses_agent_cli_from_its_argv(monkeypatch):
    run = MagicMock(return_value=0)
    monkeypatch.setattr(lae, "run", run)
    monkeypatch.setattr(lae.sys.stdin, "read", lambda: '{"packet":true}')

    assert lae.main(["--", "codex", "exec", "-"]) == 0

    run.assert_called_once_with(
        '{"packet":true}',
        ["codex", "exec", "-"],
    )
