"""Graph dependency status checks — ported from verify_node.py."""

from __future__ import annotations


def dependency_status(project_yaml: dict, depends_on: list[str]) -> dict[str, str]:
    """Return {dep_id: status} from the project graph index."""
    nodes = {
        n["id"]: n
        for n in project_yaml.get("nodes", [])
        if isinstance(n, dict) and "id" in n
    }
    return {d: nodes.get(d, {}).get("status", "unknown") for d in depends_on}