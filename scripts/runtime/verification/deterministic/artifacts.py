"""Required-artifact presence checks — ported from verify_node.py."""

from __future__ import annotations

from pathlib import Path


def _has_artifact_heading(receipt_path: Path, artifact_name: str) -> bool:
    """Check if receipt_path contains H2 heading matching artifact_name.

    Match exactly: `## <artifact_name>` with optional trailing whitespace.
    """
    if not receipt_path.is_file():
        return False
    try:
        content = receipt_path.read_text()
        target = f"## {artifact_name}"
        for line in content.splitlines():
            if line.rstrip() == target:
                return True
    except (OSError, UnicodeDecodeError):
        pass
    return False


def check_artifacts(node_yaml: dict, repo: Path) -> dict[str, bool]:
    """Look for required_artifacts in repo root and a few likely spots.

    An artifact is present if:
    1. Found as an individual file in repo, repo/.gddp/, or repo/docs/, OR
    2. executor-receipt.md exists in one of those spots and contains an H2 heading
       matching the artifact name exactly (e.g., `## decision.md`).

    merged_pr is always treated as not-present (needs network).
    """
    required = node_yaml.get("required_artifacts", [])
    present: dict[str, bool] = {}
    spots = [repo, repo / ".gddp", repo / "docs"]

    for a in required:
        if a == "merged_pr":
            present[a] = False
            continue

        # Check for individual file
        found_individual = any((s / a).is_file() for s in spots)
        if found_individual:
            present[a] = True
            continue

        # Check for condensed receipt
        found_in_receipt = any(
            _has_artifact_heading(s / "executor-receipt.md", a) for s in spots
        )
        present[a] = found_in_receipt

    return present
