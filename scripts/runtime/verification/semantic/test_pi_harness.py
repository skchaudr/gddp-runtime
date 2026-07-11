import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.runtime.verification.semantic.pi_runner import PiHarnessRunner
from scripts.runtime.verification.semantic.integrity_runner import IntegrityHarnessRunner
from scripts.runtime.verification.schemas import SemanticOutput, IntegrityOutput

@patch("subprocess.run")
@patch("shutil.which", return_value="/usr/bin/pi")
def test_pi_harness_runner_builds_correct_command(mock_which, mock_run, tmp_path):
    runner = PiHarnessRunner(provider="deepseek", thinking="medium")
    repo = tmp_path / "repo"
    repo.mkdir()

    # Mock verdict file creation and write
    def side_effect(cmd, env, **kwargs):
        verdict_path = env["GDDP_VERDICT_OUT"]
        with open(verdict_path, "w") as f:
            json.dump({
                "judgments": [],
                "overall_reasoning": "Mocked",
                "risks": None,
                "followup_candidates": None,
                "budget_exhausted": False
            }, f)
        return MagicMock(returncode=0)

    mock_run.side_effect = side_effect

    node = {"node_id": "test-node"}
    graph = {"project_id": "test-project"}
    det_result = MagicMock()

    runner.run(node=node, graph=graph, deterministic_result=det_result, repo=repo)

    args, kwargs = mock_run.call_args
    cmd = args[0]

    assert cmd[0] == "pi"
    assert "--exclude-tools" in cmd
    # Find index of --exclude-tools and check the next element
    idx = cmd.index("--exclude-tools")
    assert "bash" in cmd[idx+1]
    assert "edit" in cmd[idx+1]
    assert "--provider" in cmd
    assert "deepseek" in cmd

@patch("subprocess.run")
@patch("shutil.which", return_value="/usr/bin/pi")
def test_integrity_harness_runner_builds_correct_command(mock_which, mock_run, tmp_path):
    runner = IntegrityHarnessRunner(provider="zai", thinking="high")
    repo = tmp_path / "repo"
    repo.mkdir()

    def side_effect(cmd, env, **kwargs):
        verdict_path = env["GDDP_INTEGRITY_OUT"]
        with open(verdict_path, "w") as f:
            json.dump({
                "verdict": "pass",
                "intent_preserved": True,
                "graph_integrity_preserved": True,
                "required_human_review": False,
                "confidence": 0.9,
                "findings": [],
                "reasoning": "Mocked integrity"
            }, f)
        return MagicMock(returncode=0)

    mock_run.side_effect = side_effect

    node = {"node_id": "test-node"}
    graph = {"project_id": "test-project"}
    det_result = MagicMock()

    runner.run(node=node, graph=graph, deterministic_result=det_result, repo=repo)

    args, kwargs = mock_run.call_args
    cmd = args[0]

    assert cmd[0] == "pi"
    assert "--exclude-tools" in cmd
    assert "--provider" in cmd
    assert "zai" in cmd
