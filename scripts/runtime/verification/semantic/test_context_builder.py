"""Tests for the canonical context builder (criteria lane item 2.2)."""

from __future__ import annotations

from pathlib import Path

from scripts.runtime.verification.semantic.context_builder import build_canonical_pointers


def _write_project_yaml(
    config_root: Path,
    project_id: str,
    nodes: list[dict[str, str]],
) -> None:
    """Write a minimal project.yaml and per-node YAML files under config_root."""
    project_dir = config_root / "graphs" / project_id
    nodes_dir = project_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    nodes_block = "\n".join(f"  - id: {n['id']}" for n in nodes)
    (project_dir / "project.yaml").write_text(
        f"project_id: {project_id}\nproject_name: Test\nnodes:\n{nodes_block}\n",
        encoding="utf-8",
    )
    for n in nodes:
        (nodes_dir / f"{n['id']}.yaml").write_text(
            f"node_id: {n['id']}\ntitle: {n.get('title', n['id'])}\n",
            encoding="utf-8",
        )


def test_readme_and_project_brief_pointed_when_present(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    (repo / "PROJECT-BRIEF.md").write_text("brief\n", encoding="utf-8")

    pointers = build_canonical_pointers(
        node={"depends_on": [], "unlocks": []},
        graph={"project_id": "p"},
        repo=repo,
        config_root=None,
    )

    assert pointers["readme"] == str(repo / "README.md")
    assert pointers["project_brief"] == str(repo / "PROJECT-BRIEF.md")


def test_missing_docs_marked_unavailable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    pointers = build_canonical_pointers(
        node={},
        graph={"project_id": "p"},
        repo=repo,
        config_root=None,
    )

    assert pointers["readme"].startswith("UNAVAILABLE:")
    assert "README.md" in pointers["readme"]
    assert pointers["project_brief"].startswith("UNAVAILABLE:")
    assert "PROJECT-BRIEF.md" in pointers["project_brief"]


def test_invariants_pointed_when_present(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs" / "invariants").mkdir(parents=True)
    (repo / "docs" / "invariants" / "invariants.md").write_text(
        "inviolable rules\n", encoding="utf-8",
    )

    pointers = build_canonical_pointers(
        node={"depends_on": [], "unlocks": []},
        graph={"project_id": "p"},
        repo=repo,
        config_root=None,
    )

    assert pointers["invariants"] == str(repo / "docs" / "invariants" / "invariants.md")


def test_invariants_fallback_name_when_primary_absent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "INVARIANTS.md").write_text("rules\n", encoding="utf-8")

    pointers = build_canonical_pointers(
        node={"depends_on": [], "unlocks": []},
        graph={"project_id": "p"},
        repo=repo,
        config_root=None,
    )

    assert pointers["invariants"] == str(repo / "INVARIANTS.md")


def test_invariants_omitted_when_absent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    pointers = build_canonical_pointers(
        node={"depends_on": [], "unlocks": []},
        graph={"project_id": "p"},
        repo=repo,
        config_root=None,
    )

    # Optional per project: no key, no UNAVAILABLE marker.
    assert "invariants" not in pointers


def test_foundational_node_included(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    _write_project_yaml(config_root, "p", [{"id": "first"}, {"id": "second"}])

    pointers = build_canonical_pointers(
        node={"depends_on": [], "unlocks": []},
        graph={"project_id": "p", "nodes": [{"id": "first"}, {"id": "second"}]},
        repo=tmp_path / "repo",
        config_root=config_root,
    )

    expected = str(config_root / "graphs" / "p" / "nodes" / "first.yaml")
    assert pointers["foundational_node"] == expected


def test_dag_neighbors_included(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    _write_project_yaml(
        config_root,
        "p",
        [{"id": "root"}, {"id": "upstream"}, {"id": "downstream"}],
    )

    pointers = build_canonical_pointers(
        node={"depends_on": ["upstream"], "unlocks": ["downstream"]},
        graph={"project_id": "p", "nodes": [{"id": "root"}]},
        repo=tmp_path / "repo",
        config_root=config_root,
    )

    assert pointers["neighbor:upstream"] == str(
        config_root / "graphs" / "p" / "nodes" / "upstream.yaml"
    )
    assert pointers["neighbor:downstream"] == str(
        config_root / "graphs" / "p" / "nodes" / "downstream.yaml"
    )


def test_missing_neighbor_marked_unavailable(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    _write_project_yaml(config_root, "p", [{"id": "root"}])

    pointers = build_canonical_pointers(
        node={"depends_on": ["ghost"]},
        graph={"project_id": "p", "nodes": [{"id": "root"}]},
        repo=tmp_path / "repo",
        config_root=config_root,
    )

    assert pointers["neighbor:ghost"].startswith("UNAVAILABLE:")
    assert "ghost.yaml" in pointers["neighbor:ghost"]


def test_agents_md_never_included(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    (repo / "PROJECT-BRIEF.md").write_text("x\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("agent-only\n", encoding="utf-8")

    pointers = build_canonical_pointers(
        node={"depends_on": [], "unlocks": []},
        graph={"project_id": "p", "nodes": [{"id": "n"}]},
        repo=repo,
        config_root=tmp_path / "config",
    )

    # AGENTS.md must not appear as a key or value anywhere in the pointers.
    assert "agents_md" not in pointers
    assert "agents" not in pointers
    assert not any("AGENTS.md" in v for v in pointers.values())


def test_no_config_root_marks_graph_pointers_unavailable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("x\n", encoding="utf-8")

    pointers = build_canonical_pointers(
        node={"depends_on": ["upstream"], "unlocks": ["downstream"]},
        graph={"project_id": "p", "nodes": [{"id": "root"}]},
        repo=repo,
        config_root=None,
    )

    # README still resolves from the repo.
    assert pointers["readme"] == str(repo / "README.md")
    # Graph-derived pointers are all UNAVAILABLE.
    assert pointers["foundational_node"].startswith("UNAVAILABLE:")
    assert pointers["neighbor:upstream"].startswith("UNAVAILABLE:")
    assert pointers["neighbor:downstream"].startswith("UNAVAILABLE:")


def test_no_neighbors_yields_no_neighbor_keys(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("x\n", encoding="utf-8")

    pointers = build_canonical_pointers(
        node={"depends_on": [], "unlocks": []},
        graph={"project_id": "p", "nodes": [{"id": "root"}]},
        repo=repo,
        config_root=None,
    )

    assert not any(k.startswith("neighbor:") for k in pointers)
