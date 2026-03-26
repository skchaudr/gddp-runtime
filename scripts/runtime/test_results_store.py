import sqlite3
import sys
from pathlib import Path
import pytest

# Add the parent directory to sys.path to allow importing from the current package
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.runtime import results_store
from scripts.runtime.results_store import init_db, write_result

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Fixture to provide a temporary database path and monkeypatch DB_PATH."""
    db_file = tmp_path / "test_queue.db"
    monkeypatch.setattr(results_store, "DB_PATH", db_file)
    return db_file

def test_init_db(temp_db):
    """Verify that init_db correctly creates the return_results table."""
    init_db()

    con = sqlite3.connect(temp_db)
    try:
        cur = con.cursor()
        # Check if table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='return_results'")
        assert cur.fetchone() is not None

        # Check columns
        cur.execute("PRAGMA table_info(return_results)")
        columns = {row[1]: row[2] for row in cur.fetchall()}
        expected_columns = {
            "id": "TEXT",
            "repo_name": "TEXT",
            "node_id": "TEXT",
            "pr_number": "INTEGER",
            "merged_at": "TEXT",
            "status": "TEXT",
            "reason": "TEXT",
            "commit_sha": "TEXT",
            "created_at": "TEXT"
        }
        for col, col_type in expected_columns.items():
            assert col in columns
            assert columns[col] == col_type
    finally:
        con.close()

def test_write_result_update_ignores_none(temp_db):
    """Verify that passing None during update does not overwrite existing values."""
    result_id = "res_none"
    repo_name = "test/repo"

    # Initial insert with values
    write_result(
        result_id=result_id,
        repo_name=repo_name,
        status="pending",
        node_id="initial-node",
        pr_number=100
    )

    # Update only status, others are None
    write_result(
        result_id=result_id,
        repo_name=repo_name,
        status="completed",
        node_id=None,
        pr_number=None
    )

    con = sqlite3.connect(temp_db)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM return_results WHERE id = ?", (result_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["status"] == "completed"
        assert row["node_id"] == "initial-node"  # Should NOT be None
        assert row["pr_number"] == 100           # Should NOT be None
    finally:
        con.close()

def test_write_result_update(temp_db):
    """Verify that write_result correctly updates an existing record."""
    result_id = "res_update"
    repo_name = "test/repo"

    # Insert initial record
    write_result(result_id=result_id, repo_name=repo_name, status="pending")

    # Update status and reason
    write_result(result_id=result_id, repo_name=repo_name, status="completed", reason="Updated")

    con = sqlite3.connect(temp_db)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM return_results WHERE id = ?", (result_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["status"] == "completed"
        assert row["reason"] == "Updated"
    finally:
        con.close()

def test_write_result_insert(temp_db):
    """Verify that write_result correctly inserts a new record."""
    result_id = "res_123"
    repo_name = "test/repo"
    status = "completed"
    node_id = "auth-node"
    pr_number = 42
    merged_at = "2024-01-01T00:00:00Z"
    reason = "Success"
    commit_sha = "abc123"

    write_result(
        result_id=result_id,
        repo_name=repo_name,
        status=status,
        node_id=node_id,
        pr_number=pr_number,
        merged_at=merged_at,
        reason=reason,
        commit_sha=commit_sha
    )

    con = sqlite3.connect(temp_db)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM return_results WHERE id = ?", (result_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["id"] == result_id
        assert row["repo_name"] == repo_name
        assert row["status"] == status
        assert row["node_id"] == node_id
        assert row["pr_number"] == pr_number
        assert row["merged_at"] == merged_at
        assert row["reason"] == reason
        assert row["commit_sha"] == commit_sha
        assert row["created_at"] is not None  # Should be set by _now()
    finally:
        con.close()

def test_write_result_minimal(temp_db):
    """Verify write_result works with minimal parameters."""
    result_id = "res_min"
    repo_name = "test/repo"
    status = "pending"

    write_result(result_id=result_id, repo_name=repo_name, status=status)

    con = sqlite3.connect(temp_db)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM return_results WHERE id = ?", (result_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["id"] == result_id
        assert row["repo_name"] == repo_name
        assert row["status"] == status
        assert row["created_at"] is not None
    finally:
        con.close()
