"""Tests for scripts/local_agent_executor.py — packet, prompt, diff emission."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import local_agent_executor as lae  # noqa: E402


def _sample_packet(**overrides) -> dict:
    packet = {
        "job_id": "job-abc",
        "execution_attempt_id": "job-abc:attempt:0",
        "node_id": "job-state-consistency",
        "title": "Make jobs.status and jobs.queue_state agree",
        "goal": "Fix mismatched status/queue_state writers",
        "why": "Dashboard lied about running count",
        "constraints": [
            "do not change receipt semantics",
            {"scope": "column semantics only"},
        ],
        "acceptance_criteria": [
            {
                "id": "root-cause-documented",
                "criterion": "decision.md names the write path",
            },
            "suite-green",
        ],
        "required_artifacts": ["decision.md", "result-summary.md", "patch.diff"],
        "attempt_index": 0,
        "previous_findings": None,
        "expected_base_commit_sha": "deadbeef",
    }
    packet.update(overrides)
    return packet


def test_load_packet_requires_fields():
    with pytest.raises(ValueError, match="missing required"):
        lae.load_packet("{}")
    with pytest.raises(ValueError, match="not valid JSON"):
        lae.load_packet("not-json")
    data = lae.load_packet(json.dumps(_sample_packet()))
    assert data["job_id"] == "job-abc"
    assert data["expected_base_commit_sha"] == "deadbeef"


def test_build_prompt_includes_goal_criteria_db_and_worktree(tmp_path):
    packet = _sample_packet()
    wt = tmp_path / "wt"
    db = tmp_path / "queue.db"
    prompt = lae.build_prompt(packet, worktree=wt, queue_db=db)

    assert "Fix mismatched status/queue_state writers" in prompt
    assert "decision.md names the write path" in prompt
    assert "do not change receipt semantics" in prompt
    assert "suite-green" in prompt
    assert str(wt) in prompt
    assert str(db) in prompt
    assert "READ-ONLY" in prompt
    assert "never execute" in prompt.lower() or "NOT run UPDATE" in prompt
    assert "job-state-consistency" in prompt
    assert "job-abc" in prompt
    assert "decision.md" in prompt


def test_build_prompt_includes_previous_findings():
    packet = _sample_packet(
        previous_findings={
            "verdict": "fail",
            "reasoning": "missing decision.md root cause",
        }
    )
    prompt = lae.build_prompt(
        packet, worktree=Path("/tmp/wt"), queue_db=Path("/tmp/db")
    )
    assert "Previous Attempt Findings" in prompt
    assert "missing decision.md root cause" in prompt


def test_agent_argv_default_is_pinned_grok(tmp_path):
    argv = lae.agent_argv(tmp_path, tmp_path / "prompt.md")
    assert argv[0] == "grok"
    assert "--cwd" in argv
    assert str(tmp_path) in argv
    assert "--prompt-file" in argv
    assert str(tmp_path / "prompt.md") in argv
    assert "--always-approve" in argv


def test_agent_argv_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(
        lae._AGENT_ARGV_ENV,
        json.dumps(["echo", "agent", "{worktree}", "{prompt_file}"]),
    )
    argv = lae.agent_argv(tmp_path, tmp_path / "p.md")
    assert argv == ["echo", "agent", str(tmp_path), str(tmp_path / "p.md")]


def test_resolve_base_commit_prefers_packet_then_env(monkeypatch, tmp_path):
    monkeypatch.setenv(lae._BASE_ENV, "from-env")
    assert (
        lae.resolve_base_commit({"expected_base_commit_sha": "from-packet"}, tmp_path)
        == "from-packet"
    )
    assert lae.resolve_base_commit({}, tmp_path) == "from-env"


def test_resolve_base_commit_falls_back_to_head(tmp_path, monkeypatch):
    monkeypatch.delenv(lae._BASE_ENV, raising=False)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "f").write_text("x")
    subprocess.run(["git", "add", "f"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert lae.resolve_base_commit({}, tmp_path) == head


def test_emit_diff_captures_new_file(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "seed").write_text("seed\n")
    subprocess.run(["git", "add", "seed"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "seed"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "decision.md").write_text("# root cause\n")
    patch = lae.emit_diff(tmp_path)
    assert "decision.md" in patch
    assert "root cause" in patch
    assert patch.startswith("diff --git")


def test_run_pipeline_with_fake_agent_emits_diff(tmp_path, monkeypatch, capsys):
    """End-to-end without calling a real agent CLI."""
    # Isolated repo
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README").write_text("base\n")
    subprocess.run(["git", "add", "README"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    def fake_agent(argv, worktree: Path) -> int:
        # Agent "works" only in the worktree.
        (worktree / "decision.md").write_text("root cause: expiry path\n")
        (worktree / "result-summary.md").write_text("fixed writers\n")
        return 0

    packet = _sample_packet(expected_base_commit_sha=head)
    code = lae.run(json.dumps(packet), repo=repo, run_agent_fn=fake_agent)
    captured = capsys.readouterr()
    assert code == 0
    assert "decision.md" in captured.out
    assert "root cause: expiry path" in captured.out
    assert "result-summary.md" in captured.out
    # prompt file must not leak into the patch
    assert ".gddp-agent-prompt.md" not in captured.out
    # live repo tree untouched
    assert not (repo / "decision.md").exists()
