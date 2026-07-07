"""Canonical context builder for evaluator prompts.

Assembles file pointers (paths, not embedded contents) for the canonical
project docs and DAG neighborhood. The evaluator reads what it decides it
needs; the tool trace then records which files were actually read — a read
call is evidence, an embedded blob is not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_canonical_pointers(
    *,
    node: dict[str, Any],
    graph: dict[str, Any],
    repo: Path,
    config_root: Path | None,
) -> dict[str, str]:
    """Return a dict of canonical context file pointers.

    Keys:
      - "readme": path to the project README in the target repo (if it exists)
      - "project_brief": path to PROJECT-BRIEF.md in the target repo (if it exists)
      - "foundational_node": path to the first/oldest node YAML in the graph
      - "neighbor:<node_id>": path to each depends_on/unlocks neighbor node YAML

    Missing files are reported as "UNAVAILABLE: <path> does not exist" rather
    than silently dropped. The target repo's AGENTS.md is NEVER included.
    """
    pointers: dict[str, str] = {}

    # 1. Canonical docs from the target repo
    for name, filename in [("readme", "README.md"), ("project_brief", "PROJECT-BRIEF.md")]:
        # Try common variants (uppercase, lowercase, .md extension)
        for variant in [filename, filename.upper(), filename.lower()]:
            path = repo / variant
            if path.exists():
                pointers[name] = str(path)
                break
        else:
            pointers[name] = f"UNAVAILABLE: {repo / filename} does not exist"

    # 2. Foundational/first node from the graph
    project_id = graph.get("project_id", "")
    if config_root and project_id:
        nodes_dir = config_root / "graphs" / project_id / "nodes"
        # The foundational node is the first node listed in project.yaml
        graph_nodes = graph.get("nodes", [])
        if graph_nodes:
            first_node_id = (
                graph_nodes[0].get("id", "")
                if isinstance(graph_nodes[0], dict)
                else str(graph_nodes[0])
            )
            if first_node_id:
                path = nodes_dir / f"{first_node_id}.yaml"
                pointers["foundational_node"] = (
                    str(path) if path.exists() else f"UNAVAILABLE: {path} does not exist"
                )
            else:
                pointers["foundational_node"] = "UNAVAILABLE: no first node id in project.yaml"
        else:
            pointers["foundational_node"] = "UNAVAILABLE: no nodes in project.yaml"
    else:
        pointers["foundational_node"] = "UNAVAILABLE: no config_root or project_id"

    # 3. DAG neighborhood: depends_on + unlocks neighbor node YAMLs
    neighbor_ids = list(node.get("depends_on") or []) + list(node.get("unlocks") or [])
    if neighbor_ids:
        if config_root and project_id:
            nodes_dir = config_root / "graphs" / project_id / "nodes"
            for nid in neighbor_ids:
                path = nodes_dir / f"{nid}.yaml"
                pointers[f"neighbor:{nid}"] = (
                    str(path) if path.exists() else f"UNAVAILABLE: {path} does not exist"
                )
        else:
            for nid in neighbor_ids:
                pointers[f"neighbor:{nid}"] = "UNAVAILABLE: no config_root provided"
    # If no neighbors, simply don't add any neighbor keys

    return pointers
