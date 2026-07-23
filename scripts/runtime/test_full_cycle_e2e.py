"""End-to-end test exercising both pathways (item 1.4).

Heartbeat creates job → mock dispatch → simulated merged PR → return_router →
bridge (mocked) → receipt attached → job in awaiting_review.

No real executors or LLM calls. SQLite only, using a temp runtime root.
"""

import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _init_db(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    con.executescript(
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
            required_artifacts  TEXT NOT NULL DEFAULT '[]',
            previous_findings   TEXT,
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

        CREATE TABLE executor_sessions (
            session_db_id              TEXT PRIMARY KEY,
            job_id                     TEXT NOT NULL,
            executor                   TEXT NOT NULL,
            session_id                 TEXT NOT NULL,
            state                      TEXT DEFAULT 'dispatched',
            execution_attempt_id       TEXT NOT NULL,
            attempt_index              INTEGER NOT NULL,
            expected_base_commit_sha   TEXT,
            result_commit_sha          TEXT,
            patch_path                 TEXT,
            error                      TEXT,
            created_at                 TEXT NOT NULL,
            updated_at                 TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(job_id)
        );

        CREATE TABLE results (
            result_id                   TEXT PRIMARY KEY,
            schema_version              TEXT NOT NULL DEFAULT '1.0',
            job_id                      TEXT NOT NULL,
            executor                    TEXT NOT NULL,
            received_at                 TEXT NOT NULL,
            execution_duration_seconds  INTEGER,
            outcome                     TEXT NOT NULL,
            status                      TEXT NOT NULL,
            changed_files               TEXT,
            patch_path                  TEXT,
            summary_path                TEXT,
            logs_path                   TEXT,
            acceptance_check            TEXT,
            risks                       TEXT,
            followup_candidates         TEXT,
            github_action               TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(job_id)
        );
        """
    )
    con.commit()
    con.close()


def _write_graph(config_root: Path, project_id: str, repo: str) -> None:
    project_dir = config_root / "graphs" / project_id
    nodes_dir = project_dir / "nodes"
    nodes_dir.mkdir(parents=True)
    (project_dir / "project.yaml").write_text(
        f"""
project_id: {project_id}
project_name: E2E Test
repo: {repo}
nodes:
  - id: auth-boundary
    status: ready
execution_policy:
  default_executor: jules
  max_concurrent_jobs: 2
"""
        .strip()
        + "\n"
    )
    (nodes_dir / "auth-boundary.yaml").write_text(
        """
node_id: auth-boundary
title: Implement auth boundary
status: ready
type: capability
why: Protected actions need auth
depends_on: []
acceptance_criteria:
  - id: auth-works
    criterion: auth works
constraints: []
allowed_execution_modes:
  - jules
required_artifacts: []
priority: high
unlocks: []
"""
        .strip()
        + "\n"
    )


@pytest.fixture
def e2e_env(tmp_path):
    """Set up a temp runtime root + config root with DB and graph."""
    runtime_root = tmp_path / "runtime"
    config_root = tmp_path / "config"
    db_path = runtime_root / "db" / "queue.db"
    db_path.parent.mkdir(parents=True)
    events_raw = runtime_root / "events" / "raw"
    events_raw.mkdir(parents=True)

    _init_db(db_path)
    _write_graph(config_root, "e2e-test", "skchaudr/e2e-test")

    env_overrides = {
        "GDDP_RUNTIME_ROOT": str(runtime_root),
        "GDDP_CONFIG_PATH": str(config_root),
    }
    saved = {}
    for k, v in env_overrides.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v

    yield {
        "runtime_root": runtime_root,
        "config_root": config_root,
        "db_path": db_path,
    }

    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


def test_full_cycle_dispatch_to_review(e2e_env):
    """Full cycle: heartbeat dispatches job → merged PR → return router → receipt."""
    from scripts.runtime.heartbeat import runner as heartbeat_runner
    from scripts.runtime.return_router import handle_merged_pr

    db = str(e2e_env["db_path"])
    repo = "skchaudr/e2e-test"

    # Step 1: Inject an issue.opened event
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.execute(
        """INSERT INTO events (
            event_id, received_at, source, event_type, project_id, status, url, branch
        ) VALUES (?, ?, 'github', 'issue.opened', 'e2e-test', 'received', ?, 'feature/node:auth-boundary')""",
        ("evt_e2e_001", _now(),
         "https://github.com/skchaudr/e2e-test/issues/1"),
    )
    con.commit()
    con.close()

    # Step 2: Run heartbeat _plan_dispatches with mock dispatcher
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row

    # Patch the DB path so the heartbeat runner uses our temp DB
    with patch.object(heartbeat_runner, "DB_PATH", e2e_env["db_path"]), \
         patch.object(heartbeat_runner, "RUNTIME_ROOT", e2e_env["runtime_root"]), \
         patch("scripts.runtime.heartbeat.runner.dispatch") as mock_dispatch:

        from scripts.runtime.heartbeat.dispatcher import DispatchResult
        mock_dispatch.return_value = DispatchResult(
            success=True, issue_url="https://github.com/skchaudr/e2e-test/issues/1"
        )

        reader = heartbeat_runner.GraphReader(config_path=str(e2e_env["config_root"]))
        ready_nodes = reader.get_ready_nodes("e2e-test")
        assert len(ready_nodes) == 1
        assert ready_nodes[0].node_id == "auth-boundary"

        planned = heartbeat_runner._plan_dispatches(
            con, "e2e-test", repo, ready_nodes, reader
        )

    assert len(planned) == 1
    job_id = planned[0].job["job_id"]
    assert planned[0].job["node_id"] == "auth-boundary"

    # Record outcomes (as the heartbeat would)
    heartbeat_runner._record_outcomes(
        con, planned,
        {job_id: heartbeat_runner.DispatchOutcome(
            planned=planned[0], success=True,
            issue_url="https://github.com/skchaudr/e2e-test/issues/1",
        )},
    )
    con.commit()
    con.close()

    # Verify job was created and is running
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    job = con.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    assert job is not None
    assert job["status"] == "running"
    assert job["node_id"] == "auth-boundary"
    con.close()

    # Step 3: Simulate a merged PR
    pr_payload = {
        "repository": {"full_name": "skchaudr/e2e-test"},
        "pull_request": {
            "number": 1,
            "body": f"Implemented auth boundary.\n\nnode: auth-boundary\njob: {job_id}",
            "merged_at": _now(),
            "html_url": "https://github.com/skchaudr/e2e-test/pull/1",
        },
    }
    pr_path = e2e_env["runtime_root"] / "events" / "raw" / "pr_e2e_001.json"
    pr_path.write_text(json.dumps(pr_payload))

    # Insert a merged-PR event
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.execute(
        """INSERT INTO events (
            event_id, received_at, source, event_type, project_id, status, url, raw_payload_path
        ) VALUES (?, ?, 'github', 'pull_request.closed', 'e2e-test', 'received', ?, ?)""",
        ("evt_e2e_pr_001", _now(),
         "https://github.com/skchaudr/e2e-test/pull/1", str(pr_path)),
    )
    con.commit()
    con.close()

    # Step 4: Run return router with bridge mocked
    # Patch DB_PATH in results_store and return_router so they use our temp DB
    fake_verification = {
        "verification_status": "ok",
        "receipt_path": "/tmp/e2e_receipt.json",
        "verdict": "pass",
        "criteria_confidence": 0.9,
        "completeness_status": "complete",
        "required_next_action": "Proceed to accept_node.",
    }

    with patch("scripts.runtime.return_router.DB_PATH", e2e_env["db_path"]), \
         patch("scripts.runtime.results_store.DB_PATH", e2e_env["db_path"]), \
         patch("scripts.runtime.return_router.verify_job_return",
               return_value=fake_verification), \
         patch("scripts.runtime.return_router._FALLBACK_ALLOWED_REPOS",
               ["skchaudr/e2e-test"]):

        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        pr_event = con.execute(
            "SELECT * FROM events WHERE event_id = 'evt_e2e_pr_001'"
        ).fetchone()
        con.close()

        result = handle_merged_pr(pr_event)

    # Step 5: Assert the return path worked
    assert result["status"] == "needs_review"
    assert result["job_id"] == job_id
    assert result["node_id"] == "auth-boundary"
    assert result["verification"]["verdict"] == "pass"

    # Verify job is now awaiting_review
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    job = con.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    assert job["status"] == "awaiting_review"
    assert job["queue_state"] == "awaiting_review"

    # Verify a result was written with the verification verdict
    res = con.execute("SELECT * FROM results WHERE job_id = ?", (job_id,)).fetchone()
    assert res is not None
    assert res["status"] == "needs_review"
    acceptance = json.loads(res["acceptance_check"])
    assert acceptance["verdict"] == "pass"
    con.close()
