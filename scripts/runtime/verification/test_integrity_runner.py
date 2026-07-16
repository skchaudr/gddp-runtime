"""Tests for integrity_runner graph access: neighbor pointers into the prompt."""

from pathlib import Path

from scripts.runtime.verification.semantic.integrity_runner import (
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
    from scripts.runtime.verification.schemas import LaneExecutionStatus

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
