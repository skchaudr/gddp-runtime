"""
test_conductor.py — Tests for the verification conductor.

All external calls (gh CLI, gddp-config reads, graph_updater) are mocked.
The conductor's own logic is tested through run_verification().
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.runtime import conductor, results_store, review_queue


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Set up a temporary results database."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(results_store, "DB_PATH", db_file)
    monkeypatch.setattr(review_queue, "DB_PATH", db_file)
    monkeypatch.setattr(conductor, "DB_PATH", db_file)
    results_store.init_db()
    return db_file


@pytest.fixture
def tmp_config(tmp_path):
    """Create a minimal gddp-config directory structure."""
    project_dir = tmp_path / "graphs" / "test-project" / "nodes"
    project_dir.mkdir(parents=True)

    # project.yaml with inline nodes
    project_yaml = tmp_path / "graphs" / "test-project" / "project.yaml"
    project_yaml.write_text(json.dumps({
        "repo": "owner/repo",
        "nodes": [
            {
                "id": "node-1",
                "status": "in_progress",
                "acceptance": ["tests pass", "code works"],
                "artifacts": ["src/main.py"],
                "allowed_paths": ["src/"],
            },
        ],
    }))

    return tmp_path


def _seed_result(db_file, result_id="res_001", node_id="node-1",
                  repo_name="owner/repo", pr_number=42):
    """Insert a needs_review result with full github_action metadata."""
    con = sqlite3.connect(db_file)
    try:
        con.execute(
            "INSERT INTO results "
            "(result_id, job_id, executor, received_at, outcome, status, github_action) "
            "VALUES (?, ?, ?, datetime('now'), ?, ?, ?)",
            (
                result_id,
                "job_001",
                "jules",
                "success",
                "needs_review",
                json.dumps({
                    "source": "merged_pr",
                    "event_id": "evt_001",
                    "repo_name": repo_name,
                    "pr_number": pr_number,
                    "merged_at": "2026-05-28T00:00:00Z",
                    "merged_pr_url": "https://github.com/owner/repo/pull/42",
                    "node_id": node_id,
                    "review_required": True,
                }),
            ),
        )
        con.commit()
    finally:
        con.close()


# ---- Conductor flow tests ----

class TestRunVerification:

    def test_accept_flow(self, tmp_db, tmp_config):
        """ACCEPT: verdict stored, graph_updater.open_evidence_pr called."""
        _seed_result(tmp_db)

        with patch.object(conductor, "gather_changed_files", return_value=["src/main.py"]), \
             patch.object(conductor, "open_evidence_pr") as mock_pr:
            result = conductor.run_verification("res_001", config_path=str(tmp_config))

        assert result["ok"] is True
        assert result["verdict"] == "ACCEPT"
        assert result["matrix_row"] == 2  # semantic skipped
        mock_pr.assert_called_once()

        # Verify the DB was updated
        con = sqlite3.connect(tmp_db)
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM results WHERE result_id = ?", ("res_001",)).fetchone()
        con.close()
        assert row["status"] == "verified_accept"
        check = json.loads(row["acceptance_check"])
        assert check["verdict"] == "ACCEPT"

    def test_fail_flow(self, tmp_db, tmp_config):
        """FAIL: verdict stored, NO graph mutation."""
        _seed_result(tmp_db)

        # Use changed_files that are out of scope to force structural failure
        with patch.object(conductor, "gather_changed_files", return_value=["secret.env"]), \
             patch.object(conductor, "open_evidence_pr") as mock_pr:
            result = conductor.run_verification("res_001", config_path=str(tmp_config))

        assert result["ok"] is True
        assert result["verdict"] == "FAIL"
        assert result["matrix_row"] == 1  # structural failure
        mock_pr.assert_not_called()

    def test_needs_review_flow(self, tmp_db, tmp_config):
        """NEEDS_REVIEW: verdict stored, escalated."""
        _seed_result(tmp_db)

        # Structural passes with in-scope files, but we mock decide to return NEEDS_REVIEW
        with patch.object(conductor, "gather_changed_files", return_value=["src/main.py"]), \
             patch.object(conductor, "open_evidence_pr") as mock_pr, \
             patch("scripts.runtime.conductor.decide") as mock_decide:
            from scripts.runtime.verification.verdict_schema import DecisionOutput
            mock_decide.return_value = DecisionOutput(
                verdict="NEEDS_REVIEW", reason="operator_review_flagged",
                severity="warning", matrix_row=8,
            )
            result = conductor.run_verification("res_001", config_path=str(tmp_config))

        assert result["ok"] is True
        assert result["verdict"] == "NEEDS_REVIEW"
        mock_pr.assert_not_called()

        con = sqlite3.connect(tmp_db)
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM results WHERE result_id = ?", ("res_001",)).fetchone()
        con.close()
        assert row["status"] == "escalated"

    def test_invalid_flow(self, tmp_db, tmp_config):
        """INVALID: verdict stored, NO graph mutation."""
        _seed_result(tmp_db)

        with patch.object(conductor, "gather_changed_files", return_value=["src/main.py"]), \
             patch.object(conductor, "open_evidence_pr") as mock_pr, \
             patch("scripts.runtime.conductor.decide") as mock_decide:
            from scripts.runtime.verification.verdict_schema import DecisionOutput
            mock_decide.return_value = DecisionOutput(
                verdict="INVALID", reason="contradicted",
                severity="blocking", matrix_row=6,
            )
            result = conductor.run_verification("res_001", config_path=str(tmp_config))

        assert result["ok"] is True
        assert result["verdict"] == "INVALID"
        mock_pr.assert_not_called()

    def test_incomplete_flow(self, tmp_db, tmp_config):
        """INCOMPLETE: verdict stored, verified_incomplete status."""
        _seed_result(tmp_db)

        with patch.object(conductor, "gather_changed_files", return_value=["src/main.py"]), \
             patch.object(conductor, "open_evidence_pr") as mock_pr, \
             patch("scripts.runtime.conductor.decide") as mock_decide:
            from scripts.runtime.verification.verdict_schema import DecisionOutput
            mock_decide.return_value = DecisionOutput(
                verdict="INCOMPLETE", reason="insufficient",
                severity="warning", matrix_row=7,
            )
            result = conductor.run_verification("res_001", config_path=str(tmp_config))

        assert result["ok"] is True
        assert result["verdict"] == "INCOMPLETE"

        con = sqlite3.connect(tmp_db)
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM results WHERE result_id = ?", ("res_001",)).fetchone()
        con.close()
        assert row["status"] == "verified_incomplete"

    def test_missing_result(self, tmp_db, tmp_config):
        """Nonexistent result_id -> ok=False."""
        result = conductor.run_verification("res_nonexistent", config_path=str(tmp_config))

        assert result["ok"] is False
        assert "Result not found" in result["error"]

    def test_missing_pr_data(self, tmp_db, tmp_config):
        """Result with no github_action -> ok=False."""
        con = sqlite3.connect(tmp_db)
        con.execute(
            "INSERT INTO results (result_id, job_id, executor, received_at, outcome, status) "
            "VALUES (?, ?, ?, datetime('now'), ?, ?)",
            ("res_empty", "job_002", "jules", "success", "needs_review"),
        )
        con.commit()
        con.close()

        result = conductor.run_verification("res_empty", config_path=str(tmp_config))

        assert result["ok"] is False
        assert "No github_action" in result["error"]

    def test_missing_config_path(self, tmp_db, monkeypatch):
        """No gddp-config found -> ok=False."""
        _seed_result(tmp_db)
        # Remove env var and ensure no sibling
        monkeypatch.delenv("GDDP_CONFIG_PATH", raising=False)

        with patch.object(conductor, "_resolve_config_path", return_value=None):
            result = conductor.run_verification("res_001", config_path=None)

        assert result["ok"] is False
        assert "gddp-config path not resolved" in result["error"]


# ---- Helper function tests ----

class TestLoadNodeSpec:

    def test_load_from_node_yaml(self, tmp_config):
        """Load node spec from individual YAML file."""
        node_dir = tmp_config / "graphs" / "test-project" / "nodes"
        node_file = node_dir / "my-node.yaml"
        node_file.write_text(json.dumps({
            "id": "my-node",
            "acceptance": ["tests pass"],
            "artifacts": ["src/foo.py"],
        }))

        spec = conductor.load_node_spec("test-project", "my-node", str(tmp_config))

        assert spec["id"] == "my-node"
        assert "tests pass" in spec["acceptance"]

    def test_load_from_project_yaml_inline(self, tmp_config):
        """Load node spec from inline node in project.yaml."""
        spec = conductor.load_node_spec("test-project", "node-1", str(tmp_config))

        assert spec["id"] == "node-1"
        assert spec["acceptance"] == ["tests pass", "code works"]

    def test_load_missing_returns_empty(self, tmp_config):
        """Missing node -> returns empty dict."""
        spec = conductor.load_node_spec("test-project", "nonexistent", str(tmp_config))

        assert spec == {}


class TestGatherChangedFiles:

    def test_success(self):
        """gh CLI returns file list correctly."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/main.py\nsrc/utils.py\n"

        with patch("scripts.runtime.conductor.subprocess.run", return_value=mock_result):
            files = conductor.gather_changed_files("owner/repo", "42")

        assert files == ["src/main.py", "src/utils.py"]

    def test_failure_returns_empty(self):
        """gh CLI fails -> returns empty list."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "not found"

        with patch("scripts.runtime.conductor.subprocess.run", return_value=mock_result):
            files = conductor.gather_changed_files("owner/repo", "42")

        assert files == []

    def test_timeout_returns_empty(self):
        """gh CLI times out -> returns empty list."""
        import subprocess

        with patch("scripts.runtime.conductor.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30)):
            files = conductor.gather_changed_files("owner/repo", "42")

        assert files == []
