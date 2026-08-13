"""Tests for integrity_runner graph access: neighbor pointers into the prompt."""

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from scripts.runtime.verification.schemas import LaneExecutionStatus
from scripts.runtime.verification.semantic import integrity_runner, pi_runner
from scripts.runtime.verification.semantic.integrity_runner import (
    IntegrityHarnessRunner,
    _build_integrity_prompt,
    _neighbor_pointers,
)

NODE = {"node_id": "node-b", "depends_on": ["node-a"], "unlocks": ["node-c"]}
GRAPH = {"project_id": "proj"}


def _config_root(tmp_path: Path) -> Path:
    nodes_dir = tmp_path / "graphs" / "proj" / "nodes"
    nodes_dir.mkdir(parents=True)
    (nodes_dir / "node-a.yaml").write_text("node_id: node-a\nwhy: zz-neighbor-body-sentinel\n")
    return tmp_path


def test_pointers_map_existing_and_mark_missing(tmp_path: Path) -> None:
    pointers = _neighbor_pointers(NODE, GRAPH, _config_root(tmp_path))
    assert pointers["node-a"].endswith("nodes/node-a.yaml")
    assert Path(pointers["node-a"]).exists()
    assert "UNAVAILABLE" in pointers["node-c"]  # unlocks node not on disk


def test_no_config_root_marks_all_unavailable() -> None:
    pointers = _neighbor_pointers(NODE, GRAPH, None)
    assert set(pointers) == {"node-a", "node-c"}
    assert all("UNAVAILABLE" in v for v in pointers.values())


def test_no_neighbors_is_empty() -> None:
    assert _neighbor_pointers({"node_id": "solo"}, GRAPH, None) == {}


def test_prompt_includes_pointers_not_contents(tmp_path: Path) -> None:
    root = _config_root(tmp_path)
    pointers = _neighbor_pointers(NODE, GRAPH, root)
    prompt = _build_integrity_prompt(NODE, GRAPH, None, pointers, root)
    assert "neighbor_node_files" in prompt
    assert "node-a.yaml" in prompt
    assert str(root) in prompt
    assert "zz-neighbor-body-sentinel" not in prompt  # contents stay on disk; the agent reads them


def test_prompt_includes_canonical_context_block(tmp_path: Path) -> None:
    """Phase 2: integrity prompt includes the shared canonical context block."""
    root = _config_root(tmp_path)
    pointers = _neighbor_pointers(NODE, GRAPH, root)
    canonical = {
        "readme": str(tmp_path / "README.md"),
        "project_brief": str(tmp_path / "PROJECT-BRIEF.md"),
        "foundational_node": str(root / "graphs" / "proj" / "nodes" / "node-a.yaml"),
        "neighbor:node-a": str(root / "graphs" / "proj" / "nodes" / "node-a.yaml"),
    }
    prompt = _build_integrity_prompt(NODE, GRAPH, None, pointers, root, canonical)
    assert "Canonical Context" in prompt
    assert "README.md" in prompt
    assert "PROJECT-BRIEF.md" in prompt


def test_empty_integrity_accepts_tool_trace() -> None:
    """Phase 2: _empty_integrity accepts and carries a tool_trace."""
    from scripts.runtime.verification.semantic.integrity_runner import _empty_integrity

    trace = [{"tool": "read", "path": "/some/file.py", "blocked": False}]
    result = _empty_integrity("test reason", tool_trace=trace)
    assert result.tool_trace == trace

    result_no_trace = _empty_integrity("test reason")
    assert result_no_trace.tool_trace is None


def test_empty_integrity_accepts_lane_status_and_harness_error() -> None:
    """Phase 4: _empty_integrity accepts lane_status and harness_error."""
    from scripts.runtime.verification.semantic.integrity_runner import _empty_integrity
    result = _empty_integrity(
        "pi crashed",
        lane_status=LaneExecutionStatus.CRASHED,
        harness_error="pi exited with code 1",
    )
    assert result.lane_status == LaneExecutionStatus.CRASHED
    assert result.harness_error == "pi exited with code 1"

    result_clean = _empty_integrity("ok")
    assert result_clean.lane_status is None
    assert result_clean.harness_error is None


def test_runner_argv0_uses_pinned_real_bin(monkeypatch, tmp_path: Path) -> None:
    real_pi = tmp_path / "real-pi"
    real_pi.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    real_pi.chmod(0o755)
    captured: dict[str, object] = {}

    def fake_tee(cmd, env, *args, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = env

        class Proc:
            returncode = 1

        return Proc()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PI_REAL_BIN", str(real_pi))
    monkeypatch.setattr(pi_runner, "_tee_subprocess", fake_tee)

    pi_runner.PiHarnessRunner(provider="deepseek").run(
        node={"node_id": "node-a"},
        graph={"project_id": "project-a"},
        deterministic_result={},
        repo=tmp_path,
    )

    assert captured["cmd"][0] == str(real_pi)
    assert captured["env"]["PI_REAL_BIN"] == str(real_pi)


def test_integrity_timeout_returns_typed_output(monkeypatch, tmp_path: Path) -> None:
    """A timed-out integrity subprocess becomes receipt evidence, not a crash."""
    real_pi = tmp_path / "real-pi"
    real_pi.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    real_pi.chmod(0o755)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PI_REAL_BIN", str(real_pi))
    monkeypatch.setattr(
        integrity_runner,
        "_tee_subprocess",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("pi", 1)),
    )

    result = IntegrityHarnessRunner(provider="deepseek").run(
        node={"node_id": "node-a"}, graph={"project_id": "project-a"},
        deterministic_result={}, repo=tmp_path,
    )

    assert result.lane_status == LaneExecutionStatus.TIMED_OUT
    assert result.harness_error.startswith("pi timed out after 1200s")
    # Failure path: log files are preserved and their paths linked into harness_error.
    assert "stdout=" in result.harness_error
    assert "stderr=" in result.harness_error


def test_semantic_timeout_returns_typed_output(monkeypatch, tmp_path: Path) -> None:
    """The criteria lane uses the same typed timeout contract."""
    real_pi = tmp_path / "real-pi"
    real_pi.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    real_pi.chmod(0o755)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PI_REAL_BIN", str(real_pi))
    monkeypatch.setattr(
        pi_runner,
        "_tee_subprocess",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("pi", 1)),
    )

    result = pi_runner.PiHarnessRunner(provider="deepseek").run(
        node={"node_id": "node-a"}, graph={"project_id": "project-a"},
        deterministic_result={}, repo=tmp_path,
    )

    assert result.lane_status == LaneExecutionStatus.TIMED_OUT
    assert result.harness_error.startswith("pi timed out after 1200s")
    # Failure path: log files are preserved and their paths linked into harness_error.
    assert "stdout=" in result.harness_error
    assert "stderr=" in result.harness_error


def test_timeout_kills_stubborn_descendant_after_group_leader_exits(tmp_path: Path) -> None:
    """A descendant that ignores SIGTERM cannot outlive its terminated leader."""
    child_pid_path = tmp_path / "child.pid"
    program = (
        "import subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)']); "
        "open(sys.argv[1], 'w').write(str(child.pid)); time.sleep(30)"
    )
    with patch.object(sys, "stdout"), patch.object(sys, "stderr"):
        try:
            pi_runner._tee_subprocess(
                [sys.executable, "-c", program, str(child_pid_path)],
                dict(os.environ), str(tmp_path), str(tmp_path / "out.log"), str(tmp_path / "err.log"), 0.2,
            )
        except subprocess.TimeoutExpired:
            pass
        else:
            raise AssertionError("expected timeout")

    child_pid = int(child_pid_path.read_text())
    time.sleep(0.1)
    try:
        os.kill(child_pid, 0)
    except ProcessLookupError:
        return
    raise AssertionError(f"timed-out pi child {child_pid} is still running")
