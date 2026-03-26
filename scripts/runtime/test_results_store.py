import sqlite3
import pytest
from scripts.runtime import results_store

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_queue.db"
    # Ensure the directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(results_store, "DB_PATH", db_path)
    return db_path

def test_init_db(temp_db):
    """Verify that init_db creates the table correctly."""
    results_store.init_db()

    with sqlite3.connect(temp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='return_results'")
        assert cur.fetchone() is not None

        # Check columns
        cur.execute("PRAGMA table_info(return_results)")
        columns = [row[1] for row in cur.fetchall()]
        expected_columns = [
            "id", "repo_name", "node_id", "pr_number", "merged_at",
            "status", "reason", "commit_sha", "created_at"
        ]
        for col in expected_columns:
            assert col in columns

def test_write_result_insert(temp_db):
    """Verify that write_result inserts a new record."""
    results_store.write_result(
        result_id="res_123",
        repo_name="org/repo",
        status="completed",
        node_id="node_a",
        pr_number=42,
        merged_at="2023-10-01T12:00:00Z",
        reason="Success",
        commit_sha="abc1234"
    )

    with sqlite3.connect(temp_db) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT * FROM return_results WHERE id = ?", ("res_123",))
        row = cur.fetchone()

    assert row is not None
    assert row["repo_name"] == "org/repo"
    assert row["status"] == "completed"
    assert row["node_id"] == "node_a"
    assert row["pr_number"] == 42
    assert row["merged_at"] == "2023-10-01T12:00:00Z"
    assert row["reason"] == "Success"
    assert row["commit_sha"] == "abc1234"
    assert row["created_at"] is not None

def test_write_result_update(temp_db):
    """Verify that write_result updates an existing record."""
    # First insert
    results_store.write_result(
        result_id="res_update",
        repo_name="org/repo",
        status="pending",
        created_at="2023-10-01T10:00:00Z"
    )

    # Then update status and add reason
    results_store.write_result(
        result_id="res_update",
        repo_name="org/repo",
        status="failed",
        reason="Some error"
    )

    with sqlite3.connect(temp_db) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT * FROM return_results WHERE id = ?", ("res_update",))
        row = cur.fetchone()

    assert row["status"] == "failed"
    assert row["reason"] == "Some error"
    assert row["created_at"] == "2023-10-01T10:00:00Z" # Should not have changed

def test_write_result_full_update(temp_db):
    """Verify that all fields can be updated in an existing record."""
    # First insert
    results_store.write_result(
        result_id="res_full_update",
        repo_name="org/repo",
        status="pending"
    )

    # Then update everything
    results_store.write_result(
        result_id="res_full_update",
        repo_name="org/repo",
        status="completed",
        node_id="new_node",
        pr_number=99,
        merged_at="2023-10-01T13:00:00Z",
        reason="Final reason",
        commit_sha="def5678"
    )

    with sqlite3.connect(temp_db) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT * FROM return_results WHERE id = ?", ("res_full_update",))
        row = cur.fetchone()

    assert row["status"] == "completed"
    assert row["node_id"] == "new_node"
    assert row["pr_number"] == 99
    assert row["merged_at"] == "2023-10-01T13:00:00Z"
    assert row["reason"] == "Final reason"
    assert row["commit_sha"] == "def5678"

def test_write_result_no_updates(temp_db):
    """Verify behavior when no fields are provided for update."""
    results_store.write_result(
        result_id="res_no_up",
        repo_name="org/repo",
        status="pending"
    )

    # Update with status as None to avoid adding to updates list
    results_store.write_result(
        result_id="res_no_up",
        repo_name="org/repo",
        status=None
    )

    with sqlite3.connect(temp_db) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT * FROM return_results WHERE id = ?", ("res_no_up",))
        row = cur.fetchone()

    assert row["status"] == "pending"

def test_write_result_default_created_at(temp_db):
    """Verify that created_at defaults to current time."""
    results_store.write_result(
        result_id="res_now",
        repo_name="org/repo",
        status="pending"
    )

    with sqlite3.connect(temp_db) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT created_at FROM return_results WHERE id = ?", ("res_now",))
        row = cur.fetchone()

    assert row["created_at"] is not None
    assert "T" in row["created_at"]
