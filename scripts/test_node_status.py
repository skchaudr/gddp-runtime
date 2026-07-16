import argparse
import sqlite3

from scripts import node_status


def test_set_uses_shared_job_lifecycle_vocabulary(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            node_id TEXT,
            project_id TEXT,
            queue_state TEXT,
            status TEXT,
            created_at TEXT
        );
        CREATE TABLE queue_records (job_id TEXT, queue TEXT);
        CREATE TABLE decision_results (
            result_id TEXT PRIMARY KEY,
            action TEXT,
            node_id TEXT,
            project_id TEXT,
            reason TEXT,
            created_at TEXT
        );
        INSERT INTO jobs VALUES (
            'job_1', 'node-1', 'project-1', 'running', 'running',
            '2026-07-16T00:00:00+00:00'
        );
        INSERT INTO queue_records VALUES ('job_1', 'running');
        """
    )
    con.commit()
    con.close()
    monkeypatch.setattr(node_status, "DB_PATH", db_path)

    node_status.cmd_set(argparse.Namespace(
        ref="job_1",
        state="deferred",
        reason="operator pause",
        yes=True,
    ))

    con = sqlite3.connect(db_path)
    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = 'job_1'"
    ).fetchone()
    queue = con.execute(
        "SELECT queue FROM queue_records WHERE job_id = 'job_1'"
    ).fetchone()[0]
    con.close()

    assert job == ("deferred", "deferred")
    assert queue == "deferred"
