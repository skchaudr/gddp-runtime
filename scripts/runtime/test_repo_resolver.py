"""Tests for the shared repo-checkout resolver.

The resolver is the single policy for mapping a graph project to a local
git checkout. These tests pin the candidate chain, the .git validity check,
and — as a regression pin for 2026-08-02 — resolution when a graph id
differs from the checkout directory name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.runtime.repo_resolver import (
    project_resolution_candidates,
    resolve_project_repo_checkout,
    resolve_repo_checkout,
)


@pytest.fixture(autouse=True)
def _clear_repo_env(monkeypatch):
    monkeypatch.delenv("GDDP_REPO_ROOT", raising=False)
    monkeypatch.delenv("GDDP_REPOS_ROOT", raising=False)


def _make_checkout(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / ".git").mkdir()
    return path


def _write_project(config_root: Path, project_id: str, repo: str) -> None:
    graph_root = config_root / "graphs" / project_id
    graph_root.mkdir(parents=True)
    (graph_root / "project.yaml").write_text(
        f"project_id: {project_id}\nrepo: {repo}\n",
        encoding="utf-8",
    )


def test_explicit_path_wins(tmp_path: Path) -> None:
    repo = _make_checkout(tmp_path / "explicit-repo")
    assert resolve_repo_checkout("owner/other", explicit=str(repo)) == repo


def test_absolute_repo_value_resolves(tmp_path: Path) -> None:
    repo = _make_checkout(tmp_path / "absolute-repo")
    assert resolve_repo_checkout(str(repo), config_root=tmp_path / "config") == repo


def test_gddp_repo_root_basename(tmp_path: Path, monkeypatch) -> None:
    repo = _make_checkout(tmp_path / "repo-root" / "source-repo")
    monkeypatch.setenv("GDDP_REPO_ROOT", str(tmp_path / "repo-root"))
    assert resolve_repo_checkout("owner/source-repo", config_root=tmp_path / "c") == repo


def test_gddp_repos_root_basename(tmp_path: Path, monkeypatch) -> None:
    repo = _make_checkout(tmp_path / "repos-root" / "source-repo")
    monkeypatch.setenv("GDDP_REPOS_ROOT", str(tmp_path / "repos-root"))
    assert resolve_repo_checkout("owner/source-repo", config_root=tmp_path / "c") == repo


def test_config_sibling_basename(tmp_path: Path) -> None:
    config_root = tmp_path / "gddp-config"
    config_root.mkdir()
    repo = _make_checkout(tmp_path / "source-repo")
    resolved = resolve_repo_checkout("owner/source-repo", config_root=config_root)
    assert resolved is not None
    assert resolved.resolve() == repo


def test_directory_without_git_entry_never_wins(tmp_path: Path) -> None:
    """A same-named directory that is not a checkout is not a candidate hit."""
    config_root = tmp_path / "gddp-config"
    config_root.mkdir()
    (tmp_path / "source-repo").mkdir()  # no .git inside
    assert resolve_repo_checkout("owner/source-repo", config_root=config_root) is None


def test_linked_worktree_gitdir_file_counts(tmp_path: Path) -> None:
    """Worktrees carry a .git *file*, not a directory — both are checkouts."""
    worktree = tmp_path / "worktree-repo"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    assert resolve_repo_checkout(str(worktree)) == worktree


def test_unresolved_returns_none(tmp_path: Path) -> None:
    config_root = tmp_path / "gddp-config"
    config_root.mkdir()
    assert resolve_repo_checkout("owner/source-repo", config_root=config_root) is None


def test_empty_repo_value_returns_none(tmp_path: Path) -> None:
    assert resolve_repo_checkout("", config_root=tmp_path) is None


def test_project_resolves_via_repo_field_when_id_differs_from_dirname(
    tmp_path: Path,
) -> None:
    """Regression pin, 2026-08-02: graph id skc-portfolio-migration, checkout
    directory my-little-app. The evaluator bridge previously resolved
    repos_root/project_id and errorred "repo not found"; the declared `repo:`
    field is the mapping."""
    config_root = tmp_path / "gddp-config"
    _write_project(config_root, "skc-portfolio-migration", "skchaudr/my-little-app")
    repo = _make_checkout(tmp_path / "my-little-app")
    resolved = resolve_project_repo_checkout(
        "skc-portfolio-migration", config_root=config_root
    )
    assert resolved is not None
    assert resolved.resolve() == repo


def test_project_falls_back_to_project_id_without_repo_field(tmp_path: Path) -> None:
    config_root = tmp_path / "gddp-config"
    _write_project(config_root, "gddp-runtime", "")
    repo = _make_checkout(tmp_path / "gddp-runtime")
    resolved = resolve_project_repo_checkout("gddp-runtime", config_root=config_root)
    assert resolved is not None
    assert resolved.resolve() == repo


def test_project_unreadable_yaml_falls_back_to_project_id(tmp_path: Path) -> None:
    config_root = tmp_path / "gddp-config"
    config_root.mkdir()  # no graphs/ at all — read fails
    repo = _make_checkout(tmp_path / "vault-doctor")
    resolved = resolve_project_repo_checkout("vault-doctor", config_root=config_root)
    assert resolved is not None
    assert resolved.resolve() == repo


def test_candidates_name_repo_field_paths_for_loud_errors(tmp_path: Path) -> None:
    config_root = tmp_path / "gddp-config"
    _write_project(config_root, "skc-portfolio-migration", "skchaudr/my-little-app")
    candidates = project_resolution_candidates(
        "skc-portfolio-migration", config_root=config_root
    )
    assert candidates == [tmp_path / "my-little-app"]
