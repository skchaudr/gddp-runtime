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
