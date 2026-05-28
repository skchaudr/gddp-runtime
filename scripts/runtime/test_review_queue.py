"""
test_review_queue.py — Tests for the review queue (verification job management).

Uses a temporary SQLite database for each test. No mocking needed.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.runtime import results_store
from scripts.runtime import review_queue


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Set up a temporary results database and patch DB_PATH."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(results_store, "DB_PATH", db_file)
    monkeypatch.setattr(review_queue, "DB_PATH", db_file)
    results_store.init_db()
    return db_file


def _insert_result(db_file, result_id, status="needs_review", **extra):
    """Helper to insert a result row directly."""
    con = sqlite3.connect(db_file)
    try:
        con.execute(
            "INSERT INTO results (result_id, job_id, executor, received_at, outcome, status, github_action) "
            "VALUES (?, ?, ?, datetime('now'), ?, ?, ?)",
            (
                result_id,
                extra.get("job_id", "job_001"),
                extra.get("executor", "jules"),
                extra.get("outcome", "success"),
                status,
                json.dumps(extra.get("github_action", {"node_id": "n1", "repo_name": "owner/repo", "pr_number": 42})),
            ),
        )
        con.commit()
    finally:
        con.close()


def _load_row(db_file, result_id):
    """Helper to read a result row."""
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT * FROM results WHERE result_id = ?", (result_id,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


# ---- Poll tests ----

class TestPollAwaitingReview:

    def test_poll_returns_needs_review(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="needs_review")
        _insert_result(tmp_db, "res_002", status="needs_review")

        results = review_queue.poll_awaiting_review()

        ids = [r["result_id"] for r in results]
        assert "res_001" in ids
        assert "res_002" in ids

    def test_poll_excludes_other_statuses(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="needs_review")
        _insert_result(tmp_db, "res_002", status="verified_accept")
        _insert_result(tmp_db, "res_003", status="verifying")
        _insert_result(tmp_db, "res_004", status="escalated")

        results = review_queue.poll_awaiting_review()

        ids = [r["result_id"] for r in results]
        assert ids == ["res_001"]

    def test_poll_returns_empty_when_nothing_awaiting(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="verified_accept")

        results = review_queue.poll_awaiting_review()

        assert results == []


# ---- Claim tests ----

class TestClaimForVerification:

    def test_claim_succeeds_for_needs_review(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="needs_review")

        ok = review_queue.claim_for_verification("res_001")

        assert ok is True
        row = _load_row(tmp_db, "res_001")
        assert row["status"] == "verifying"

    def test_claim_fails_for_wrong_status(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="verified_accept")

        ok = review_queue.claim_for_verification("res_001")

        assert ok is False

    def test_claim_fails_for_nonexistent(self, tmp_db):
        ok = review_queue.claim_for_verification("res_nonexistent")

        assert ok is False

    def test_claim_prevents_double_claim(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="needs_review")

        first = review_queue.claim_for_verification("res_001")
        second = review_queue.claim_for_verification("res_001")

        assert first is True
        assert second is False


# ---- Complete verification tests ----

class TestCompleteVerification:

    def test_complete_writes_verdict_to_acceptance_check(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="needs_review")
        review_queue.claim_for_verification("res_001")

        review_queue.complete_verification(
            result_id="res_001",
            verdict="ACCEPT",
            reason="skipped",
            severity=None,
            matrix_row=2,
            structural_passed=True,
            structural_results=[],
        )

        row = _load_row(tmp_db, "res_001")
        check = json.loads(row["acceptance_check"])
        assert check["verdict"] == "ACCEPT"
        assert check["matrix_row"] == 2
        assert check["structural_passed"] is True
        assert "verified_at" in check

    def test_complete_updates_status_to_verified_accept(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="needs_review")
        review_queue.claim_for_verification("res_001")

        review_queue.complete_verification(
            result_id="res_001",
            verdict="ACCEPT",
            reason="skipped",
            severity=None,
            matrix_row=2,
            structural_passed=True,
            structural_results=[],
        )

        row = _load_row(tmp_db, "res_001")
        assert row["status"] == "verified_accept"

    def test_complete_updates_status_to_verified_fail(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="needs_review")
        review_queue.claim_for_verification("res_001")

        review_queue.complete_verification(
            result_id="res_001",
            verdict="FAIL",
            reason="structural failure",
            severity="blocking",
            matrix_row=1,
            structural_passed=False,
            structural_results=[{"check": "files_in_scope", "passed": False, "evidence": "out of scope"}],
        )

        row = _load_row(tmp_db, "res_001")
        assert row["status"] == "verified_fail"

    def test_complete_updates_status_to_escalated(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="needs_review")
        review_queue.claim_for_verification("res_001")

        review_queue.complete_verification(
            result_id="res_001",
            verdict="NEEDS_REVIEW",
            reason="operator_review_flagged",
            severity="warning",
            matrix_row=8,
            structural_passed=True,
            structural_results=[],
        )

        row = _load_row(tmp_db, "res_001")
        assert row["status"] == "escalated"

    def test_complete_writes_structural_results_to_risks(self, tmp_db):
        _insert_result(tmp_db, "res_001", status="needs_review")
        review_queue.claim_for_verification("res_001")

        struct_results = [
            {"check": "graph_legality", "passed": True, "evidence": "ok"},
            {"check": "files_in_scope", "passed": False, "evidence": "out of scope: secret.py"},
        ]

        review_queue.complete_verification(
            result_id="res_001",
            verdict="FAIL",
            reason="structural failure",
            severity="blocking",
            matrix_row=1,
            structural_passed=False,
            structural_results=struct_results,
        )

        row = _load_row(tmp_db, "res_001")
        risks = json.loads(row["risks"])
        assert len(risks) == 2
        assert risks[0]["check"] == "graph_legality"
        assert risks[1]["passed"] is False

    def test_complete_raises_for_missing_result(self, tmp_db):
        with pytest.raises(ValueError, match="Result not found"):
            review_queue.complete_verification(
                result_id="res_nonexistent",
                verdict="FAIL",
                reason="not found",
                severity="blocking",
                matrix_row=1,
                structural_passed=False,
                structural_results=[],
            )

    def test_complete_preserves_github_action(self, tmp_db):
        gh = {"node_id": "n1", "repo_name": "owner/repo", "pr_number": 42}
        _insert_result(tmp_db, "res_001", status="needs_review", github_action=gh)
        review_queue.claim_for_verification("res_001")

        review_queue.complete_verification(
            result_id="res_001",
            verdict="ACCEPT",
            reason="skipped",
            severity=None,
            matrix_row=2,
            structural_passed=True,
            structural_results=[],
        )

        row = _load_row(tmp_db, "res_001")
        preserved = json.loads(row["github_action"])
        assert preserved["node_id"] == "n1"
        assert preserved["pr_number"] == 42
