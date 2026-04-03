import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.runtime import results_store
from scripts.runtime.results_store import init_db, write_result


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_queue.db"
    monkeypatch.setattr(results_store, "DB_PATH", db_file)
    return db_file


def test_init_db_creates_results_table(temp_db):
    init_db()

    con = sqlite3.connect(temp_db)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='results'")
    assert cur.fetchone() is not None

    cur.execute("PRAGMA table_info(results)")
    columns = {row[1]: row[2] for row in cur.fetchall()}
    con.close()

    assert columns["result_id"] == "TEXT"
    assert columns["job_id"] == "TEXT"
    assert columns["executor"] == "TEXT"
    assert columns["received_at"] == "TEXT"
    assert columns["outcome"] == "TEXT"
    assert columns["status"] == "TEXT"


def test_write_result_insert(temp_db):
    write_result(
        result_id="res_123",
        job_id="job_123",
        executor="jules",
        outcome="success",
        status="needs_review",
        received_at="2026-04-03T00:00:00+00:00",
        acceptance_check={"criterion": "pass"},
        risks=["manual review required"],
        github_action={"source": "merged_pr"},
    )

    con = sqlite3.connect(temp_db)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM results WHERE result_id = ?", ("res_123",)).fetchone()
    con.close()

    assert row["job_id"] == "job_123"
    assert row["executor"] == "jules"
    assert row["outcome"] == "success"
    assert row["status"] == "needs_review"
    assert json.loads(row["acceptance_check"]) == {"criterion": "pass"}
    assert json.loads(row["risks"]) == ["manual review required"]
    assert json.loads(row["github_action"]) == {"source": "merged_pr"}


def test_write_result_update_replaces_existing_receipt(temp_db):
    write_result(
        result_id="res_update",
        job_id="job_123",
        executor="jules",
        outcome="success",
        status="needs_review",
        received_at="2026-04-03T00:00:00+00:00",
        summary_path="/tmp/summary-1.md",
    )
    write_result(
        result_id="res_update",
        job_id="job_123",
        executor="jules",
        outcome="success",
        status="needs_review",
        received_at="2026-04-03T01:00:00+00:00",
        summary_path="/tmp/summary-2.md",
        followup_candidates=["node-2"],
    )

    con = sqlite3.connect(temp_db)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM results WHERE result_id = ?", ("res_update",)).fetchone()
    con.close()

    assert row["received_at"] == "2026-04-03T01:00:00+00:00"
    assert row["summary_path"] == "/tmp/summary-2.md"
    assert json.loads(row["followup_candidates"]) == ["node-2"]
