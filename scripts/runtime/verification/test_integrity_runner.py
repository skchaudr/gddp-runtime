"""Tests for integrity_runner graph access: neighbor YAML loading into the prompt."""

from pathlib import Path

from scripts.runtime.verification.semantic.integrity_runner import (
    _build_integrity_prompt,
    _load_neighbor_nodes,
)

NODE = {"node_id": "node-b", "depends_on": ["node-a"], "unlocks": ["node-c"]}
GRAPH = {"project_id": "proj"}


def _config_root(tmp_path: Path) -> Path:
    nodes_dir = tmp_path / "graphs" / "proj" / "nodes"
    nodes_dir.mkdir(parents=True)
    (nodes_dir / "node-a.yaml").write_text("node_id: node-a\nwhy: upstream\n")
    return tmp_path


def test_loads_neighbor_yaml_and_marks_missing(tmp_path: Path) -> None:
    neighbors = _load_neighbor_nodes(NODE, GRAPH, _config_root(tmp_path))
    assert neighbors["node-a"]["why"] == "upstream"
    assert "UNAVAILABLE" in neighbors["node-c"]  # unlocks node not on disk


def test_no_config_root_marks_all_unavailable() -> None:
    neighbors = _load_neighbor_nodes(NODE, GRAPH, None)
    assert set(neighbors) == {"node-a", "node-c"}
    assert all("UNAVAILABLE" in v for v in neighbors.values())


def test_no_neighbors_is_empty() -> None:
    assert _load_neighbor_nodes({"node_id": "solo"}, GRAPH, None) == {}


def test_prompt_includes_neighbors_and_config_root(tmp_path: Path) -> None:
    root = _config_root(tmp_path)
    neighbors = _load_neighbor_nodes(NODE, GRAPH, root)
    prompt = _build_integrity_prompt(NODE, GRAPH, None, neighbors, root)
    assert "neighbor_nodes" in prompt
    assert "upstream" in prompt
    assert str(root) in prompt
