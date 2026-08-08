from __future__ import annotations

import sqlite3

import pytest

from scripts import init_db as init_db_module


def _initialized_db(tmp_path, monkeypatch) -> sqlite3.Connection:
    db_path = tmp_path / "queue.db"
    monkeypatch.setattr(init_db_module, "DB_PATH", db_path)
    init_db_module.init_db()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _insert_session(
    connection: sqlite3.Connection,
    session_db_id: str,
    *,
    completion_id: str | None = None,
    completion_digest_sha256: str | None = None,
    completion_quarantine_reason: str | None = None,
    evidence_manifest_path: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO executor_sessions (
            session_db_id,
            job_id,
            executor,
            session_id,
            execution_attempt_id,
            attempt_index,
            created_at,
            updated_at,
            completion_id,
            completion_digest_sha256,
            completion_quarantine_reason,
            evidence_manifest_path
        ) VALUES (?, ?, 'factory_mission', ?, ?, 0, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_db_id,
            f"job-{session_db_id}",
            f"mission-{session_db_id}",
            f"attempt-{session_db_id}",
            "2026-08-07T00:00:00Z",
            "2026-08-07T00:00:00Z",
            completion_id,
            completion_digest_sha256,
            completion_quarantine_reason,
            evidence_manifest_path,
        ),
    )


def _column(connection: sqlite3.Connection, name: str) -> sqlite3.Row:
    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(executor_sessions)")
    }
    return columns[name]


def test_executor_sessions_completion_id_is_nullable_text(tmp_path, monkeypatch) -> None:
    connection = _initialized_db(tmp_path, monkeypatch)

    column = _column(connection, "completion_id")
    _insert_session(connection, "session-null-completion")
    connection.commit()

    assert column["type"] == "TEXT"
    assert column["notnull"] == 0
    assert connection.execute(
        "SELECT completion_id FROM executor_sessions"
    ).fetchone()[0] is None
    connection.close()


def test_executor_sessions_completion_digest_round_trips(tmp_path, monkeypatch) -> None:
    connection = _initialized_db(tmp_path, monkeypatch)
    digest = "a" * 64

    _insert_session(connection, "session-null-digest")
    _insert_session(
        connection,
        "session-digest",
        completion_digest_sha256=digest,
    )
    connection.commit()

    column = _column(connection, "completion_digest_sha256")
    values = [
        row[0]
        for row in connection.execute(
            "SELECT completion_digest_sha256 FROM executor_sessions "
            "ORDER BY session_db_id"
        )
    ]
    assert column["type"] == "TEXT"
    assert column["notnull"] == 0
    assert values == [digest, None]
    connection.close()


def test_executor_sessions_quarantine_reason_preserves_state(
    tmp_path, monkeypatch
) -> None:
    connection = _initialized_db(tmp_path, monkeypatch)
    reason = "receipt result does not match handoff commit"

    _insert_session(
        connection,
        "session-quarantined",
        completion_quarantine_reason=reason,
    )
    connection.commit()

    column = _column(connection, "completion_quarantine_reason")
    row = connection.execute(
        "SELECT state, completion_quarantine_reason FROM executor_sessions"
    ).fetchone()
    assert column["type"] == "TEXT"
    assert column["notnull"] == 0
    assert tuple(row) == ("dispatched", reason)
    connection.close()


def test_executor_sessions_evidence_manifest_path_round_trips(
    tmp_path, monkeypatch
) -> None:
    connection = _initialized_db(tmp_path, monkeypatch)
    manifest_path = "/evidence/engagement-1/node-a.json"

    _insert_session(
        connection,
        "session-evidence",
        evidence_manifest_path=manifest_path,
    )
    connection.commit()

    column = _column(connection, "evidence_manifest_path")
    stored_path = connection.execute(
        "SELECT evidence_manifest_path FROM executor_sessions"
    ).fetchone()[0]
    assert column["type"] == "TEXT"
    assert column["notnull"] == 0
    assert stored_path == manifest_path
    connection.close()


def test_completion_id_partial_unique_index_allows_nulls_only(
    tmp_path, monkeypatch
) -> None:
    connection = _initialized_db(tmp_path, monkeypatch)
    _insert_session(connection, "session-null-1")
    _insert_session(connection, "session-null-2")
    _insert_session(
        connection,
        "session-completion-1",
        completion_id="completion-1",
    )
    connection.commit()

    index_rows = connection.execute(
        "PRAGMA index_list(executor_sessions)"
    ).fetchall()
    unique_completion_indexes = []
    for index_row in index_rows:
        if not index_row["unique"] or not index_row["partial"]:
            continue
        index_name = index_row["name"]
        indexed_columns = [
            row["name"]
            for row in connection.execute(f"PRAGMA index_info({index_name})")
        ]
        if indexed_columns == ["completion_id"]:
            unique_completion_indexes.append(index_name)

    assert len(unique_completion_indexes) == 1
    index_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = ?",
        (unique_completion_indexes[0],),
    ).fetchone()[0]
    assert "WHERE completion_id IS NOT NULL" in index_sql

    with pytest.raises(sqlite3.IntegrityError):
        _insert_session(
            connection,
            "session-completion-2",
            completion_id="completion-1",
        )
    connection.close()


def test_init_db_migrates_records_discipline_columns_idempotently(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            attempt INTEGER DEFAULT 0
        );
        CREATE TABLE executor_sessions (
            session_db_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            executor TEXT NOT NULL,
            session_id TEXT NOT NULL,
            state TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO jobs (job_id, attempt) VALUES ('job-old', 0);
        INSERT INTO executor_sessions VALUES (
            'session-old',
            'job-old',
            'jules_cli',
            'remote-old',
            'collected',
            '2026-01-01T00:00:00Z',
            '2026-01-01T00:00:00Z'
        );
        """
    )
    legacy.commit()
    legacy.close()
    monkeypatch.setattr(init_db_module, "DB_PATH", db_path)

    init_db_module.init_db()
    init_db_module.init_db()

    migrated = sqlite3.connect(db_path)
    migrated.row_factory = sqlite3.Row
    columns = {
        row["name"]: row
        for row in migrated.execute("PRAGMA table_info(executor_sessions)")
    }
    records_columns = {
        "completion_id",
        "completion_digest_sha256",
        "completion_quarantine_reason",
        "evidence_manifest_path",
    }
    assert records_columns <= columns.keys()
    assert all(columns[name]["type"] == "TEXT" for name in records_columns)
    assert all(columns[name]["notnull"] == 0 for name in records_columns)
    migrated_row = migrated.execute(
        """
        SELECT state, completion_id, completion_digest_sha256,
               completion_quarantine_reason, evidence_manifest_path
          FROM executor_sessions
         WHERE session_db_id = 'session-old'
        """
    ).fetchone()
    assert tuple(migrated_row) == ("collected", None, None, None, None)
    migrated.close()
