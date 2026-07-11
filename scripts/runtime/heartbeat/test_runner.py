"""test_runner.py — Tests for heartbeat runner event routing.

Verifies that merged PR events route to the return router (handle_merged_pr)
while issue.opened events go through the classifier, and that the
_is_merged_pr_event helper correctly distinguishes merged PRs from other events.
"""

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.runtime.heartbeat import runner
from scripts.runtime.heartbeat.runner import _is_merged_pr_event


def _init_db(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript(
        """
        PRAGMA foreign_keys=ON;

        CREATE TABLE events (
            event_id                TEXT PRIMARY KEY,
            schema_version          TEXT NOT NULL DEFAULT '1.0',
            received_at             TEXT NOT NULL,
            source                  TEXT NOT NULL,
            event_type              TEXT NOT NULL,
            actor                   TEXT,
            branch                  TEXT,
            base_branch             TEXT,
            pr_number               INTEGER,
            issue_number            INTEGER,
            commit_sha              TEXT,
            url                     TEXT,
            repo                    TEXT,
            project_id              TEXT,
            project_node_candidates TEXT,
            scope_status            TEXT DEFAULT 'pending',
            priority                TEXT DEFAULT 'pending',
            risk_level              TEXT DEFAULT 'pending',
            raw_payload_path        TEXT,
            normalized_payload_path TEXT,
            classification          TEXT,
            routing                 TEXT,
            status                  TEXT DEFAULT 'received',
            claimed_at              TEXT
        );

        CREATE TABLE jobs (
            job_id              TEXT PRIMARY KEY,
            schema_version      TEXT NOT NULL DEFAULT '1.0',
            created_at          TEXT NOT NULL,
            event_id            TEXT,
            project_id          TEXT,
            repo                TEXT,
            node_id             TEXT NOT NULL,
            job_type            TEXT NOT NULL,
            executor            TEXT NOT NULL,
            queue_state         TEXT DEFAULT 'ready',
            title               TEXT NOT NULL,
            goal                TEXT NOT NULL,
            why                 TEXT,
            source_context      TEXT,
            constraints         TEXT,
            acceptance_criteria TEXT,
            dependencies        TEXT,
            priority            TEXT DEFAULT 'medium',
            risk_level          TEXT DEFAULT 'low',
            estimated_effort    TEXT DEFAULT 'medium',
            status              TEXT DEFAULT 'ready',
            attempt             INTEGER DEFAULT 0,
            max_attempts        INTEGER DEFAULT 3,
            artifacts_dir       TEXT,
            result_summary_path TEXT,
            FOREIGN KEY(event_id) REFERENCES events(event_id)
        );

        CREATE TABLE queue_records (
            queue_item_id    TEXT PRIMARY KEY,
            schema_version   TEXT NOT NULL DEFAULT '1.0',
            job_id           TEXT NOT NULL,
            queue            TEXT NOT NULL,
            available_at     TEXT NOT NULL,
            lease_owner      TEXT,
            lease_expires_at TEXT,
            retry_count      INTEGER DEFAULT 0,
            last_error       TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(job_id)
        );
        """
    )
    con.commit()
    con.close()


class TestIsMergedPrEvent:
    """Tests for the _is_merged_pr_event helper."""

    def test_pr_event_with_merged_at_returns_true(self, tmp_path):
        payload_file = tmp_path / "payload.json"
        payload_file.write_text(
            json.dumps({"pull_request": {"merged_at": "2024-03-20T10:00:00Z"}})
        )
        event = {
            "event_type": "pull_request.closed",
            "raw_payload_path": str(payload_file),
        }
        assert _is_merged_pr_event(event) is True

    def test_pr_event_without_merged_at_returns_false(self, tmp_path):
        payload_file = tmp_path / "payload.json"
        payload_file.write_text(
            json.dumps({"pull_request": {"merged_at": None}})
        )
        event = {
            "event_type": "pull_request.closed",
            "raw_payload_path": str(payload_file),
        }
        assert _is_merged_pr_event(event) is False

    def test_issue_opened_returns_false(self):
        event = {
            "event_type": "issue.opened",
            "raw_payload_path": "/tmp/whatever.json",
        }
        assert _is_merged_pr_event(event) is False

    def test_unreadable_payload_returns_false(self):
        event = {
            "event_type": "pull_request.closed",
            "raw_payload_path": "/nonexistent/path/payload.json",
        }
        assert _is_merged_pr_event(event) is False


class TestEventRouting:
    """Tests that events route to the correct handler in _plan_dispatches."""

    @pytest.fixture
    def test_db(self, tmp_path):
        db_path = tmp_path / "queue.db"
        _init_db(db_path)
        return db_path

    def test_merged_pr_routes_to_handle_merged_pr(self, test_db, tmp_path, monkeypatch):
        # Create a raw payload file with merged_at set
        payload_file = tmp_path / "merged_pr.json"
        payload_file.write_text(
            json.dumps({"pull_request": {"merged_at": "2024-03-20T10:00:00Z"}})
        )

        con = sqlite3.connect(test_db)
        con.row_factory = sqlite3.Row
        con.execute(
            "INSERT INTO events (event_id, received_at, source, event_type, "
            "project_id, status, raw_payload_path) "
            "VALUES (?, ?, 'github', 'pull_request.closed', 'test-project', "
            "'received', ?)",
            ("evt_merged", "2024-03-20T09:00:00Z", str(payload_file)),
        )
        con.commit()

        mock_handle = MagicMock(return_value={"status": "redispatched"})
        monkeypatch.setattr(runner, "handle_merged_pr", mock_handle)

        mock_classify = MagicMock(return_value=None)
        monkeypatch.setattr(runner, "classify", mock_classify)

        planned = runner._plan_dispatches(
            con, "test-project", "owner/repo", [], None
        )

        # handle_merged_pr was called
        mock_handle.assert_called_once()
        # Event was marked as mapped
        row = con.execute(
            "SELECT status FROM events WHERE event_id = ?", ("evt_merged",)
        ).fetchone()
        assert row["status"] == "mapped"
        # Classifier was NOT called
        mock_classify.assert_not_called()
        # No jobs planned (merged PR goes through return router, not dispatch)
        assert planned == []
        con.close()

    def test_issue_opened_goes_through_classifier(self, test_db, monkeypatch):
        con = sqlite3.connect(test_db)
        con.row_factory = sqlite3.Row
        con.execute(
            "INSERT INTO events (event_id, received_at, source, event_type, "
            "project_id, status) "
            "VALUES (?, ?, 'github', 'issue.opened', 'test-project', 'received')",
            ("evt_issue", "2024-03-20T09:00:00Z"),
        )
        con.commit()

        mock_handle = MagicMock(return_value={"status": "needs_review"})
        monkeypatch.setattr(runner, "handle_merged_pr", mock_handle)

        mock_classify = MagicMock(return_value=None)
        monkeypatch.setattr(runner, "classify", mock_classify)

        planned = runner._plan_dispatches(
            con, "test-project", "owner/repo", [], None
        )

        # handle_merged_pr was NOT called
        mock_handle.assert_not_called()
        # Classifier WAS called
        mock_classify.assert_called_once()
        # No jobs planned (classify returned None → event ignored)
        assert planned == []
        con.close()
