"""Focused coverage for the public runtime jobs backend."""

from __future__ import annotations

import json
import os
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
            CREATE TABLE executor_sessions (
                session_db_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                executor TEXT NOT NULL,
                session_id TEXT NOT NULL,
                state TEXT,
                expected_base_commit_sha TEXT,
                result_commit_sha TEXT,
                patch_path TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                execution_attempt_id TEXT,
                attempt_index INTEGER
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

    def test_retry_command_audits_human_rejection_and_redispatch(self):
        con = sqlite3.connect(self.db_path)
        con.execute(
            "UPDATE jobs SET status = 'awaiting_review', queue_state = 'awaiting_review' "
            "WHERE job_id = 'job-1'"
        )
        con.execute(
            "UPDATE queue_records SET queue = 'awaiting_review' WHERE job_id = 'job-1'"
        )
        con.commit()
        con.close()

        with patch.object(jobs_status, "DB_PATH", self.db_path), patch(
            "scripts.runtime.return_router.retry_reviewed_job",
            return_value={"status": "redispatched", "dispatch_success": True},
        ) as retry:
            jobs_status.main([
                "retry",
                "job-1",
                "--reason",
                "new clean user is ready",
                "--yes",
            ])

        retry.assert_called_once_with("job-1", "new clean user is ready")
        con = sqlite3.connect(self.db_path)
        audit = con.execute(
            "SELECT action, reason FROM decision_results"
        ).fetchone()
        con.close()
        self.assertEqual(
            audit,
            ("reject_and_retry", "new clean user is ready"),
        )

    def test_show_accepts_unique_node_id(self):
        with patch.object(jobs_status, "DB_PATH", self.db_path):
            jobs_status.main(["show", "node-1"])

    def test_list_highlights_queue_state_on_tty(self):
        import io
        from contextlib import redirect_stdout

        with patch.object(jobs_status, "DB_PATH", self.db_path), \
                patch.object(jobs_status, "_stdout_is_tty", return_value=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                jobs_status.main(["list"])
            out = buf.getvalue()
        self.assertIn("\033[1;35m", out)  # running → bold magenta
        self.assertIn("running", out)
        self.assertIn("job-1", out)

    def test_list_plain_when_not_tty(self):
        import io
        from contextlib import redirect_stdout

        with patch.object(jobs_status, "DB_PATH", self.db_path), \
                patch.object(jobs_status, "_stdout_is_tty", return_value=False):
            buf = io.StringIO()
            with redirect_stdout(buf):
                jobs_status.main(["list"])
            out = buf.getvalue()
        self.assertNotIn("\033[", out)
        self.assertIn("running", out)

    def test_show_prints_executor_attempt_evidence_for_local_subprocess(self):
        con = sqlite3.connect(self.db_path)
        con.execute(
            """
            INSERT INTO executor_sessions
                (session_db_id, job_id, executor, session_id, state, error,
                 result_commit_sha, expected_base_commit_sha,
                 created_at, updated_at, execution_attempt_id, attempt_index)
            VALUES
                ('ses-1', 'job-1', 'local_subprocess',
                 'job-1-node-1-attempt-0-abc', 'failed',
                 'worker exited rc=1',
                 'db292014490aecba5f157bc9d31f28b1810164cb',
                 '3d530ad76b4f2e00d858e967d88c6af50314c86e',
                 '2026-07-26T04:50:20+00:00', '2026-07-26T04:50:25+00:00',
                 'job-1:attempt:0', 0)
            """
        )
        con.commit()
        con.close()

        with patch.object(jobs_status, "DB_PATH", self.db_path), \
             patch.object(jobs_status, "_read_local_subprocess_status",
                          return_value=("failed", "Codex error: Unsupported parameter: session_id")):
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                jobs_status.main(["show", "job-1"])
            out = buf.getvalue()

        self.assertIn("executor attempt: idx=0", out)
        self.assertIn("db_state=failed", out)
        self.assertIn("result sha: db292014490aecba5f157bc9d31f28b1810164cb", out)
        self.assertIn("db error:   worker exited rc=1", out)
        self.assertIn("adapter:    failed  (ok)", out)
        self.assertIn("adapter err: Codex error: Unsupported parameter: session_id", out)
        self.assertIn("base sha:   3d530ad76b4f2e00d858e967d88c6af50314c86e", out)

    def test_show_surfaces_db_vs_adapter_divergence(self):
        con = sqlite3.connect(self.db_path)
        con.execute(
            """
            INSERT INTO executor_sessions
                (session_db_id, job_id, executor, session_id, state, error,
                 created_at, updated_at, execution_attempt_id, attempt_index)
            VALUES
                ('ses-2', 'job-1', 'local_subprocess',
                 'job-1-node-1-attempt-0-div', 'dispatched', NULL,
                 '2026-07-26T05:00:00+00:00', '2026-07-26T05:00:00+00:00',
                 'job-1:attempt:0', 0)
            """
        )
        con.commit()
        con.close()

        with patch.object(jobs_status, "DB_PATH", self.db_path), \
             patch.object(jobs_status, "_read_local_subprocess_status",
                          return_value=("failed", "exited without durable exit state")):
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                jobs_status.main(["show", "job-1"])
            out = buf.getvalue()

        self.assertIn("db_state=dispatched", out)
        self.assertIn("adapter:    failed  (DIVERGENT)", out)
        self.assertIn("adapter err: exited without durable exit state", out)

    def test_show_handles_missing_executor_sessions(self):
        with patch.object(jobs_status, "DB_PATH", self.db_path):
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                jobs_status.main(["show", "job-1"])
            out = buf.getvalue()
        self.assertIn("executor attempt: (none on record)", out)

    def test_show_reads_local_subprocess_status_with_no_dispatch_env(self):
        """A normal operator shell (no GDDP_* dispatch env) can still see
        the durable adapter state for a terminal local_subprocess session."""
        import contextlib
        import io

        # Build a real terminal spool: exit.json with rc=1 and a stderr line.
        spool_root = Path(self.tempdir.name) / "spool"
        session_id = "job-1-node-1-attempt-0-noenv"
        attempt_dir = spool_root / session_id
        attempt_dir.mkdir(parents=True)
        (attempt_dir / "exit.json").write_text(
            json.dumps({"returncode": 1, "cancelled": False})
        )
        (attempt_dir / "stderr").write_text("Codex error: Unsupported parameter: session_id\n")

        # Record an executor_session pointing at the spool. DB row says
        # 'dispatched' so a divergence is visible.
        con = sqlite3.connect(self.db_path)
        con.execute(
            """
            INSERT INTO executor_sessions
                (session_db_id, job_id, executor, session_id, state, error,
                 created_at, updated_at, execution_attempt_id, attempt_index)
            VALUES
                ('ses-noenv', 'job-1', 'local_subprocess', ?, 'dispatched', NULL,
                 '2026-07-26T06:00:00+00:00', '2026-07-26T06:00:00+00:00',
                 'job-1:attempt:0', 0)
            """,
            (session_id,),
        )
        con.commit()
        con.close()

        # Run show with no dispatch env, and SPOOL env pointing at our temp dir.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("GDDP_LOCAL_SUBPROCESS_")}
        env["GDDP_LOCAL_SUBPROCESS_SPOOL_DIR"] = str(spool_root)
        buf = io.StringIO()
        with patch.object(jobs_status, "DB_PATH", self.db_path), \
             patch.dict(os.environ, env, clear=True), \
             contextlib.redirect_stdout(buf):
            jobs_status.main(["show", "job-1"])
        out = buf.getvalue()

        self.assertIn("db_state=dispatched", out)
        self.assertIn("adapter:    failed  (DIVERGENT)", out)
        self.assertIn("Codex error: Unsupported parameter: session_id", out)
        # The legacy probe-failure message must NOT appear anymore.
        self.assertNotIn("GDDP_LOCAL_SUBPROCESS_ARGV", out)


if __name__ == "__main__":
    unittest.main()
