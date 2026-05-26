"""
test_graph_updater.py — Verifies the evidence PR proposal model.

File is excluded from main test runs because open_evidence_pr requires a real
gddp-config repo and gh CLI. Run manually in a development environment:
  GDDP_CONFIG_PATH=/path/to/gddp-config pytest scripts/runtime/test_graph_updater.py -v
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.runtime.graph_updater import (
    open_evidence_pr,
    update_graph_node_complete,
    _format_evidence_block,
    _mark_node_complete_in_yaml,
)


def test_legacy_stub_returns_disabled():
    """The legacy function still exists and returns disabled."""
    result = update_graph_node_complete("p1", "n1", "pr123", "2023-10-27")
    assert result["ok"] is False
    assert "use_open_evidence_pr" in result["reason"]


class TestFormatEvidenceBlock:
    """Unit tests for evidence block formatting — no git or gh required."""

    def test_formats_with_dict_acceptance(self):
        evidence = {
            "acceptance_check": [
                {"criterion": "form accepts name", "passed": True},
                {"criterion": "no duplicate records", "passed": True},
            ],
            "scope_verification": {
                "in_scope": ["src/auth.py"],
                "out_of_scope": [],
            },
            "test_status": {"passed": True},
            "risks": "None identified",
        }
        block = _format_evidence_block(
            node_id="auth-boundary",
            project_id="vault-doctor",
            source_pr_number=51,
            source_pr_url="https://github.com/skchaudr/vault-doctor/pull/51",
            evidence=evidence,
        )

        assert "auth-boundary" in block
        assert "vault-doctor" in block
        assert "#51" in block
        assert "form accepts name" in block
        assert "PASS" in block
        assert "src/auth.py" in block
        assert "None identified" in block
        assert "human approves" in block

    def test_formats_with_string_acceptance(self):
        """When acceptance_check is a plain string, render it as-is."""
        evidence = {
            "acceptance_check": "All criteria look good per manual review.",
            "scope_verification": {},
            "test_status": {},
            "risks": "",
        }
        block = _format_evidence_block(
            node_id="node-x",
            project_id="test",
            source_pr_number=1,
            source_pr_url="https://example.com/pr/1",
            evidence=evidence,
        )
        assert "All criteria look good" in block

    def test_formats_empty_evidence(self):
        """Empty evidence should produce a valid PR body."""
        block = _format_evidence_block(
            node_id="n", project_id="p",
            source_pr_number=1, source_pr_url="https://x.com",
            evidence={},
        )
        assert "Evidence Packet" in block
        assert "Acceptance Criteria" in block


class TestMarkNodeComplete:
    """Unit test for the YAML-update helper."""

    def test_updates_status_line(self, tmp_path):
        graphs_dir = tmp_path / "graphs" / "test-project"
        graphs_dir.mkdir(parents=True)
        project_yaml = graphs_dir / "project.yaml"
        project_yaml.write_text("""nodes:
  - id: node-a
    status: complete
    type: infrastructure
  - id: node-b
    status: pending
    type: capability
  - id: node-c
    status: pending
    type: capability
""")

        _mark_node_complete_in_yaml(tmp_path, "test-project", "node-b", 42)

        content = project_yaml.read_text()
        assert "status: complete  # evidence PR: #42" in content
        assert "status: pending" in content  # node-c still pending

    def test_does_not_touch_already_complete_node(self, tmp_path):
        graphs_dir = tmp_path / "graphs" / "test-project"
        graphs_dir.mkdir(parents=True)
        project_yaml = graphs_dir / "project.yaml"
        project_yaml.write_text("""nodes:
  - id: node-a
    status: complete
    type: infrastructure
""")
        _mark_node_complete_in_yaml(tmp_path, "test-project", "node-a", 1)
        content = project_yaml.read_text()
        # Should have exactly one "status: complete" line, no duplicate
        assert content.count("status: complete") == 1


class TestOpenEvidencePr:
    """Integration-level tests for open_evidence_pr — mock git and gh."""

    def test_returns_disabled_when_config_path_unset(self, monkeypatch):
        monkeypatch.delenv("GDDP_CONFIG_PATH", raising=False)
        with pytest.raises(FileNotFoundError, match="GDDP_CONFIG_PATH"):
            open_evidence_pr(
                node_id="n", project_id="p",
                source_pr_number=1, source_pr_url="https://x.com",
                evidence={},
            )

    @patch("subprocess.run")
    def test_opens_pr_successfully(self, mock_run, monkeypatch, tmp_path):
        monkeypatch.setenv("GDDP_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("GDDP_CONFIG_REPO", "test-org/test-config")

        # Simulate a real config repo at tmp_path
        (tmp_path / ".git").mkdir()
        (tmp_path / "graphs" / "test-project").mkdir(parents=True)
        (tmp_path / "graphs" / "test-project" / "project.yaml").write_text(
            "nodes:\n  - id: n1\n    status: pending\n    type: infrastructure\n"
        )

        # Mock subprocess calls: git status clean, git checkout ok, push, pr create
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),       # git status clean
            MagicMock(returncode=0, stdout="", stderr=""),       # git checkout main
            MagicMock(returncode=0, stdout="", stderr=""),       # git branch -D
            MagicMock(returncode=0, stdout="", stderr=""),       # git checkout -b
            MagicMock(returncode=0, stdout="", stderr=""),       # git add
            MagicMock(returncode=0, stdout="", stderr=""),       # git commit
            MagicMock(returncode=0, stdout="", stderr=""),       # git push
            MagicMock(                                # gh pr create
                returncode=0,
                stdout="https://github.com/test-org/test-config/pull/5\n",
                stderr="",
            ),
            MagicMock(returncode=0, stdout="", stderr=""),       # git checkout main
        ]

        result = open_evidence_pr(
            node_id="n1",
            project_id="test-project",
            source_pr_number=42,
            source_pr_url="https://github.com/org/repo/pull/42",
            evidence={"acceptance_check": [], "scope_verification": {}, "test_status": {}},
        )

        assert result["ok"] is True
        assert result["evidence_pr_number"] == 5

    def test_ensure_config_repo_clean_raises_on_dirty(self, monkeypatch, tmp_path):
        """_ensure_config_repo_clean should raise when git status returns output."""
        from scripts.runtime.graph_updater import _ensure_config_repo_clean

        monkeypatch.setenv("GDDP_CONFIG_PATH", str(tmp_path))

        # Simulate a real config repo with a dirty working tree by actually
        # running git status inside a temp repo that has untracked changes.
        # Since we can't rely on subprocess mocking, we test the raise path
        # by creating a git repo, making it dirty, and calling the function.
        subprocess.run(["git", "-C", str(tmp_path), "init"], capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "test"],
            capture_output=True,
        )
        (tmp_path / "README.md").write_text("hello")

        with pytest.raises(RuntimeError, match="dirty"):
            _ensure_config_repo_clean(tmp_path)

    def test_returns_false_when_dirty_working_tree(self, monkeypatch, tmp_path):
        """open_evidence_pr catches the RuntimeError and returns ok=False."""
        monkeypatch.setenv("GDDP_CONFIG_PATH", str(tmp_path))

        # Create a real git repo with unstaged changes
        subprocess.run(["git", "-C", str(tmp_path), "init"], capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "test"],
            capture_output=True,
        )
        (tmp_path / "README.md").write_text("hello")

        result = open_evidence_pr(
            node_id="n", project_id="p",
            source_pr_number=1, source_pr_url="https://x.com",
            evidence={},
        )

        assert result["ok"] is False
        assert "dirty" in result["reason"]
