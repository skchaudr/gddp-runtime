"""Required-artifact presence checks — ported from verify_node.py."""

from __future__ import annotations

from pathlib import Path


def check_artifacts(node_yaml: dict, repo: Path) -> dict[str, bool]:
    """Look for required_artifacts in repo root and a few likely spots.

    merged_pr needs network and is treated as not-present in this harness.
    """
    required = node_yaml.get("required_artifacts", [])
    present: dict[str, bool] = {}
    for a in required:
        if a == "merged_pr":
            present[a] = False
            continue
        spots = [repo / a, repo / ".gddp" / a, repo / "docs" / a]
        present[a] = any(s.is_file() for s in spots)
    return present