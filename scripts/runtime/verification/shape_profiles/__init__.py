"""Read-only shape profile loader for the semantic verification agent."""

from __future__ import annotations

from pathlib import Path

import yaml

_PROFILE_DIR = Path(__file__).resolve().parent


def load_shape_profile(project_type: str) -> dict | None:
    """Load ``<project_type>.yaml`` from this package directory, or return None."""
    path = _PROFILE_DIR / f"{project_type}.yaml"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
