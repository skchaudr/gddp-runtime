import sqlite3

from scripts import dry_run, init_db
from scripts.runtime import results_store, return_router


def test_main_replaces_only_stale_dry_run_state(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    db_path = runtime_root / "db" / "queue.db"
    db_path.parent.mkdir(parents=True)

    monkeypatch.setattr(init_db, "DB_PATH", db_path)
    monkeypatch.setattr(dry_run, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(dry_run, "DB_PATH", db_path)
    monkeypatch.setattr(return_router, "DB_PATH", db_path)
    monkeypatch.setattr(results_store, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(results_store, "DB_PATH", db_path)
    monkeypatch.setattr(return_router, "_refresh_evaluations_export", lambda: None)

    init_db.init_db()
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO events (event_id, received_at, source, event_type) "
            "VALUES ('evt_sentinel', '2026-07-18T00:00:00+00:00', 'manual', 'sentinel')"
        )
        con.execute(
            """
            INSERT INTO jobs (
                job_id, created_at, event_id, node_id, job_type, executor, title, goal
            ) VALUES (
                'job_sentinel', '2026-07-18T00:00:00+00:00', 'evt_sentinel',
                'sentinel-node', 'reasoning', 'human', 'Sentinel', 'Survive dry-run cleanup'
            )
            """
        )

    dry_run.main()

    with sqlite3.connect(db_path) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            """
            INSERT INTO artifact_verifications (
                verification_id, job_id, node_id, artifact_type, validation_method
            ) VALUES ('verification_stale', 'job_dry_001', 'auth-boundary', 'patch.diff', 'file_exists')
            """
        )
        con.execute(
            """
            INSERT INTO executor_sessions (
                session_db_id, job_id, executor, session_id,
                execution_attempt_id, attempt_index, created_at, updated_at
            ) VALUES (
                'session_stale', 'job_dry_001', 'jules_cli', 'stale-session',
                'job_dry_001:attempt:0', 0,
                '2026-07-18T00:00:00+00:00', '2026-07-18T00:00:00+00:00'
            )
            """
        )

    dry_run.main()

    with sqlite3.connect(db_path) as con:
        assert con.execute(
            "SELECT count(*) FROM events WHERE event_id LIKE 'evt_dry_%'"
        ).fetchone()[0] == 2
        assert con.execute(
            "SELECT count(*) FROM jobs WHERE event_id LIKE 'evt_dry_%'"
        ).fetchone()[0] == 1
        assert con.execute(
            """
            SELECT count(*) FROM queue_records
            WHERE job_id IN (SELECT job_id FROM jobs WHERE event_id LIKE 'evt_dry_%')
            """
        ).fetchone()[0] == 1
        assert con.execute(
            """
            SELECT count(*) FROM results
            WHERE job_id IN (SELECT job_id FROM jobs WHERE event_id LIKE 'evt_dry_%')
            """
        ).fetchone()[0] == 2
        assert con.execute(
            "SELECT count(*) FROM artifact_verifications WHERE verification_id = 'verification_stale'"
        ).fetchone()[0] == 0
        assert con.execute(
            "SELECT count(*) FROM executor_sessions WHERE session_db_id = 'session_stale'"
        ).fetchone()[0] == 0
        assert con.execute(
            "SELECT count(*) FROM events WHERE event_id = 'evt_sentinel'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT count(*) FROM jobs WHERE job_id = 'job_sentinel' AND event_id = 'evt_sentinel'"
        ).fetchone()[0] == 1
