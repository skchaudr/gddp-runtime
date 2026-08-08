from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from scripts.runtime.heartbeat.completion_discipline import submit_completion


def _create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            queue_state TEXT NOT NULL
        );
        CREATE TABLE queue_records (
            job_id TEXT PRIMARY KEY,
            queue TEXT NOT NULL
        );
        CREATE TABLE executor_sessions (
            session_db_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            state TEXT NOT NULL,
            result_commit_sha TEXT,
            patch_path TEXT,
            completion_id TEXT,
            completion_digest_sha256 TEXT,
            completion_quarantine_reason TEXT,
            evidence_manifest_path TEXT,
            error TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX idx_executor_sessions_completion_id_unique
            ON executor_sessions(completion_id)
            WHERE completion_id IS NOT NULL;
        """
    )
    for suffix in ("one", "two"):
        connection.execute(
            "INSERT INTO jobs VALUES (?, 'running', 'running')",
            (f"job-{suffix}",),
        )
        connection.execute(
            "INSERT INTO queue_records VALUES (?, 'running')",
            (f"job-{suffix}",),
        )
        connection.execute(
            """
            INSERT INTO executor_sessions (
                session_db_id, job_id, state, updated_at
            ) VALUES (?, ?, 'running', '2026-08-07T00:00:00Z')
            """,
            (f"session-{suffix}", f"job-{suffix}"),
        )
    connection.commit()
    connection.close()


def _connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def _submit(
    connection: sqlite3.Connection,
    session_db_id: str,
    digest: str | None,
    *,
    completion_id: str | None = "completion-shared",
    result_sha: str = "a" * 40,
):
    return submit_completion(
        connection,
        session_db_id=session_db_id,
        completion_id=completion_id,
        completion_digest_sha256=digest,
        result_commit_sha=result_sha,
        evidence_manifest_path=f"/evidence/{session_db_id}.json",
    )


def test_null_completion_identity_proceeds_without_records_side_effects(
    tmp_path,
) -> None:
    database = tmp_path / "queue.db"
    _create_database(database)
    connection = _connection(database)

    decision = _submit(
        connection,
        "session-one",
        None,
        completion_id=None,
    )

    row = connection.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-one'"
    ).fetchone()
    assert decision.action == "proceed"
    assert row["state"] == "running"
    assert row["result_commit_sha"] is None
    assert row["completion_id"] is None
    connection.close()


def test_exact_duplicate_returns_existing_result_without_duplicate_side_effects(
    tmp_path,
) -> None:
    database = tmp_path / "queue.db"
    _create_database(database)
    connection = _connection(database)
    digest = "1" * 64

    first = _submit(connection, "session-one", digest, result_sha="a" * 40)
    before = connection.total_changes
    duplicate = _submit(
        connection,
        "session-one",
        digest,
        result_sha="b" * 40,
    )

    rows = connection.execute(
        """
        SELECT session_db_id, state, result_commit_sha, completion_id,
               completion_digest_sha256, completion_quarantine_reason
          FROM executor_sessions
         WHERE completion_id IS NOT NULL
        """
    ).fetchall()
    assert first.action == "stored"
    assert duplicate.action == "duplicate"
    assert duplicate.existing_session_db_id == "session-one"
    assert duplicate.result_commit_sha == "a" * 40
    assert connection.total_changes == before
    assert len(rows) == 1
    assert rows[0]["result_commit_sha"] == "a" * 40
    assert rows[0]["completion_quarantine_reason"] is None
    connection.close()


def test_digest_comparison_is_case_normalized(tmp_path) -> None:
    database = tmp_path / "queue.db"
    _create_database(database)
    connection = _connection(database)

    _submit(connection, "session-one", "A" * 64)
    duplicate = _submit(connection, "session-one", "a" * 64)

    row = connection.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-one'"
    ).fetchone()
    assert duplicate.action == "duplicate"
    assert row["completion_digest_sha256"] == "a" * 64
    assert row["completion_quarantine_reason"] is None
    connection.close()


def test_conflicting_duplicate_quarantines_both_envelopes_and_routes_review(
    tmp_path,
) -> None:
    database = tmp_path / "queue.db"
    _create_database(database)
    connection = _connection(database)
    existing_digest = "1" * 64
    incoming_digest = "2" * 64

    _submit(
        connection,
        "session-one",
        existing_digest,
        result_sha="a" * 40,
    )
    conflict = _submit(
        connection,
        "session-two",
        incoming_digest,
        result_sha="b" * 40,
    )

    sessions = {
        row["session_db_id"]: row
        for row in connection.execute(
            "SELECT * FROM executor_sessions ORDER BY session_db_id"
        )
    }
    assert conflict.action == "quarantined"
    assert sessions["session-one"]["completion_id"] == "completion-shared"
    assert sessions["session-one"]["completion_digest_sha256"] == existing_digest
    assert sessions["session-one"]["result_commit_sha"] == "a" * 40
    assert sessions["session-two"]["completion_id"] is None
    assert sessions["session-two"]["completion_digest_sha256"] == incoming_digest
    for session_id in ("session-one", "session-two"):
        row = sessions[session_id]
        assert row["state"] == "completion_quarantined"
        reason = row["completion_quarantine_reason"]
        assert "session-one" in reason
        assert "session-two" in reason
        assert "completion-shared" in reason
        assert existing_digest in reason
        assert incoming_digest in reason

    assert {
        tuple(row)
        for row in connection.execute(
            "SELECT status, queue_state FROM jobs ORDER BY job_id"
        )
    } == {("awaiting_review", "awaiting_review")}
    assert {
        row[0] for row in connection.execute("SELECT queue FROM queue_records")
    } == {"awaiting_review"}
    connection.close()


def test_exact_duplicate_on_second_session_reuses_first_result(tmp_path) -> None:
    database = tmp_path / "queue.db"
    _create_database(database)
    connection = _connection(database)
    digest = "1" * 64

    _submit(connection, "session-one", digest, result_sha="a" * 40)
    duplicate = _submit(
        connection,
        "session-two",
        digest,
        result_sha="b" * 40,
    )

    replay = connection.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-two'"
    ).fetchone()
    assert duplicate.action == "duplicate"
    assert duplicate.existing_session_db_id == "session-one"
    assert duplicate.result_commit_sha == "a" * 40
    assert replay["state"] == "completion_duplicate"
    assert replay["completion_id"] is None
    assert replay["completion_digest_sha256"] == digest
    assert replay["result_commit_sha"] == "a" * 40
    assert replay["completion_quarantine_reason"] is None
    connection.close()


def test_same_session_conflict_does_not_overwrite_first_completion(tmp_path) -> None:
    database = tmp_path / "queue.db"
    _create_database(database)
    connection = _connection(database)
    existing_digest = "1" * 64
    incoming_digest = "2" * 64

    _submit(
        connection,
        "session-one",
        existing_digest,
        result_sha="a" * 40,
    )
    decision = _submit(
        connection,
        "session-one",
        incoming_digest,
        result_sha="b" * 40,
    )

    row = connection.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = 'session-one'"
    ).fetchone()
    assert decision.action == "quarantined"
    assert row["completion_id"] == "completion-shared"
    assert row["completion_digest_sha256"] == existing_digest
    assert row["result_commit_sha"] == "a" * 40
    assert row["evidence_manifest_path"] == "/evidence/session-one.json"
    assert incoming_digest in row["completion_quarantine_reason"]
    connection.close()


def test_concurrent_conflicting_submissions_compare_atomically(tmp_path) -> None:
    database = tmp_path / "queue.db"
    _create_database(database)
    barrier = threading.Barrier(2)
    decisions = []
    failures = []

    def submit(session_id: str, digest: str, result_sha: str) -> None:
        connection = _connection(database)
        try:
            barrier.wait(timeout=2)
            decisions.append(
                _submit(
                    connection,
                    session_id,
                    digest,
                    result_sha=result_sha,
                )
            )
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)
        finally:
            connection.close()

    threads = [
        threading.Thread(
            target=submit,
            args=("session-one", "1" * 64, "a" * 40),
        ),
        threading.Thread(
            target=submit,
            args=("session-two", "2" * 64, "b" * 40),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not failures
    assert sorted(decision.action for decision in decisions) == [
        "quarantined",
        "stored",
    ]
    connection = _connection(database)
    rows = connection.execute(
        """
        SELECT state, completion_id, completion_quarantine_reason
          FROM executor_sessions
         ORDER BY session_db_id
        """
    ).fetchall()
    assert sum(row["completion_id"] is not None for row in rows) == 1
    assert {row["state"] for row in rows} == {"completion_quarantined"}
    assert all(row["completion_quarantine_reason"] for row in rows)
    connection.close()
