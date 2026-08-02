"""
repo_resolver.py — One canonical policy for mapping a graph project to its
local git checkout.

The runtime grew four divergent resolvers, and the evaluator bridge's
(repos_root / project_id) broke the moment a graph id differed from the
repo directory name — skc-portfolio-migration vs my-little-app, background
evaluation erroring with "repo not found" on 2026-08-02 while dispatch
(which honors project.yaml's `repo:` field) worked fine.

This module ports the proven manual-path policy from gddp-config
scripts/gddp.py::_resolve_project_repo so every runtime caller resolves
identically. The graph's `repo:` field is the declared mapping between a
project and its checkout; the graph id is never assumed to be a directory
name (it is only a fallback when no repo field is readable).

Candidate chain (first valid match wins):
  1. explicit caller-provided path
  2. repo_value itself, when absolute
  3. $GDDP_REPO_ROOT / basename
  4. $GDDP_REPOS_ROOT / basename
  5. config_root.parent / basename   (sibling checkout)

A candidate is valid only when it contains a .git entry (directory, or the
gitdir file of a linked worktree) — a same-named directory that is not a
checkout never wins.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


def resolution_candidates(
    repo_value: str,
    *,
    config_root: Path | None = None,
    explicit: str | None = None,
) -> list[Path]:
    """The ordered candidate checkouts for a `repo:` value, valid or not.

    Exposed so callers can fail loudly with the full list of paths tried —
    an error naming what was attempted is what made the 2026-08-02 seam
    diagnosable from one receipt line.
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    value = Path(repo_value)
    if value.is_absolute():
        candidates.append(value)
    basename = repo_value.rstrip("/").split("/")[-1]
    if basename:
        for env_name in ("GDDP_REPO_ROOT", "GDDP_REPOS_ROOT"):
            env_root = os.environ.get(env_name)
            if env_root:
                candidates.append(Path(env_root).expanduser() / basename)
        if config_root is not None:
            candidates.append(Path(config_root).parent / basename)
    return candidates


def _is_checkout(candidate: Path) -> bool:
    """True when the path holds a git checkout (.git dir or worktree file)."""
    try:
        return (candidate / ".git").exists()
    except OSError:
        return False


def resolve_repo_checkout(
    repo_value: str,
    *,
    config_root: Path | None = None,
    explicit: str | None = None,
) -> Path | None:
    """Resolve a graph `repo:` value (owner/name or path) to a local checkout.

    Returns the first candidate containing a .git entry, or None. Callers
    own the failure policy — build the error message with
    ``resolution_candidates`` so the miss names what was tried.
    """
    if not repo_value:
        return None
    for candidate in resolution_candidates(
        repo_value, config_root=config_root, explicit=explicit
    ):
        if _is_checkout(candidate):
            return candidate
    return None


def _project_repo_value(project_id: str, config_root: Path) -> str:
    """The project's declared `repo:` field, or project_id as fallback.

    Falling back to the graph id as a directory basename is correct for
    self-named projects (gddp-runtime) and no worse than pre-resolver
    behavior for graphs that declare no repo at all.
    """
    project_yaml = Path(config_root) / "graphs" / project_id / "project.yaml"
    try:
        doc = yaml.safe_load(project_yaml.read_text()) or {}
    except (OSError, yaml.YAMLError):
        doc = {}
    raw = doc.get("repo", "")
    return str(raw) if raw else project_id


def project_resolution_candidates(
    project_id: str,
    *,
    config_root: Path,
    explicit: str | None = None,
) -> list[Path]:
    """Candidates for a graph project, resolved through its `repo:` field."""
    return resolution_candidates(
        _project_repo_value(project_id, config_root),
        config_root=config_root,
        explicit=explicit,
    )


def resolve_project_repo_checkout(
    project_id: str,
    *,
    config_root: Path,
    explicit: str | None = None,
) -> Path | None:
    """Resolve a graph project to its local checkout via project.yaml."""
    for candidate in project_resolution_candidates(
        project_id, config_root=config_root, explicit=explicit
    ):
        if _is_checkout(candidate):
            return candidate
    return None
