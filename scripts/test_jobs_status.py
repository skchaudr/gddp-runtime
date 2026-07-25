"""Focused coverage for the public runtime jobs backend."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import jobs_status


class JobsStatusTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "queue.db"
        con = sqlite3.connect(self.db_path)
        con.executescript(
            """
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT,
                node_id TEXT,
                queue_state TEXT,
                status TEXT,
                created_at TEXT,
                title TEXT,
                executor TEXT,
                job_type TEXT,
                attempt INTEGER,
                max_attempts INTEGER,
                artifacts_dir TEXT
            );
            CREATE TABLE queue_records (job_id TEXT, queue TEXT);
            CREATE TABLE results (
                job_id TEXT,
                received_at TEXT,
                outcome TEXT,
                status TEXT,
                acceptance_check TEXT
            );
            CREATE TABLE decision_results (
                result_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                node_id TEXT,
                project_id TEXT,
                reason TEXT,
                created_at TEXT NOT NULL
            );
            INSERT INTO jobs
                (job_id, project_id, node_id, queue_state, status, created_at,
                 title, executor, job_type, attempt, max_attempts, artifacts_dir)
            VALUES
                ('job-1', 'demo', 'node-1', 'running', 'running',
                 '2026-07-24T00:00:00+00:00', 'Demo job', 'codex',
                 'implementation', 0, 3, '/tmp/demo');
            INSERT INTO queue_records (job_id, queue)
            VALUES ('job-1', 'running');
            """
        )
        con.commit()
        con.close()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_public_set_command_updates_job_state_and_audit(self):
        with patch.object(jobs_status, "DB_PATH", self.db_path):
            jobs_status.main([
                "set",
                "job-1",
                "failed",
                "--reason",
                "executor failed",
                "--yes",
            ])

        con = sqlite3.connect(self.db_path)
        job = con.execute(
            "SELECT queue_state, status FROM jobs WHERE job_id = 'job-1'"
        ).fetchone()
        queue = con.execute(
            "SELECT queue FROM queue_records WHERE job_id = 'job-1'"
        ).fetchone()
        audit = con.execute(
            "SELECT action, reason FROM decision_results"
        ).fetchone()
        con.close()
        self.assertEqual(job, ("failed", "failed"))
        self.assertEqual(queue, ("failed",))
        self.assertEqual(audit, ("manual_status_change", "executor failed"))

    def test_show_accepts_unique_node_id(self):
        with patch.object(jobs_status, "DB_PATH", self.db_path):
            jobs_status.main(["show", "node-1"])


if __name__ == "__main__":
    unittest.main()
