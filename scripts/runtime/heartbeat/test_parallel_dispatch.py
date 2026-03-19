"""
test_parallel_dispatch.py — Verifies parallel dispatch with main-thread SQLite writes.
"""

import sqlite3
import sys
import threading
from itertools import count
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.runtime.heartbeat import job_factory, runner, state_recorder
from scripts.runtime.heartbeat.dispatcher import DispatchResult


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
            project_id              TEXT,
            project_node_candidates TEXT,
            scope_status            TEXT DEFAULT 'pending',
            priority                TEXT DEFAULT 'pending',
            risk_level              TEXT DEFAULT 'pending',
            raw_payload_path        TEXT,
            normalized_payload_path TEXT,
            classification          TEXT,
            routing                 TEXT,
            status                  TEXT DEFAULT 'received'
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


def _insert_event(db_path: Path, event_id: str) -> None:
    con = sqlite3.connect(db_path)
    con.execute(
        """
        INSERT INTO events (
            event_id, received_at, source, event_type, project_id, status
        ) VALUES (?, ?, 'github', 'issue.opened', 'parallel-test', 'received')
        """,
        (event_id, "2026-03-19T00:00:00+00:00"),
    )
    con.commit()
    con.close()


def _write_graph(config_root: Path) -> None:
    project_dir = config_root / "graphs" / "parallel-test"
    nodes_dir = project_dir / "nodes"
    nodes_dir.mkdir(parents=True)

    (project_dir / "project.yaml").write_text(
        dedent(
            """
            project_id: parallel-test
            project_name: Parallel Dispatch Test
            repo: owner/repo
            nodes:
              - id: alpha-node
                status: ready
              - id: beta-node
                status: ready
              - id: blocked-node
                status: ready
              - id: prerequisite-node
                status: pending
            execution_policy: {}
            """
        ).strip()
        + "\n"
    )

    node_template = """
    node_id: {node_id}
    title: {title}
    status: ready
    type: capability
    why: test node
    depends_on:{depends_on}
    acceptance:
      - test acceptance
    constraints:
      - test constraint
    allowed_execution_modes:
      - jules
    required_artifacts: []
    priority: normal
    unlocks: []
    """

    (nodes_dir / "alpha-node.yaml").write_text(
        dedent(node_template.format(node_id="alpha-node", title="Alpha", depends_on=" []")).strip()
        + "\n"
    )
    (nodes_dir / "beta-node.yaml").write_text(
        dedent(node_template.format(node_id="beta-node", title="Beta", depends_on=" []")).strip()
        + "\n"
    )
    (nodes_dir / "blocked-node.yaml").write_text(
        dedent(
            node_template.format(
                node_id="blocked-node",
                title="Blocked",
                depends_on="\n      - prerequisite-node",
            )
        ).strip()
        + "\n"
    )


def test_parallel_dispatch_records_results_and_blocks_dependencies(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    opclaw_root = tmp_path / "opclaw"
    opclaw_root.mkdir()
    config_root = tmp_path / "config"

    _init_db(db_path)
    _insert_event(db_path, "evt-alpha")
    _insert_event(db_path, "evt-beta")
    _insert_event(db_path, "evt-blocked")
    _write_graph(config_root)

    monkeypatch.setattr(runner, "DB_PATH", db_path)
    monkeypatch.setattr(runner, "OPCLAW_ROOT", opclaw_root)

    job_ids = count(1)
    queue_ids = count(1)
    monkeypatch.setattr(job_factory, "now", lambda: "2026-03-19T00:00:00+00:00")
    monkeypatch.setattr(job_factory, "ts_id", lambda: f"{next(job_ids):017d}")
    monkeypatch.setattr(state_recorder, "now", lambda: "2026-03-19T00:00:00+00:00")
    monkeypatch.setattr(state_recorder, "ts_id", lambda: f"{next(queue_ids):017d}")

    node_map = {
        "evt-alpha": "alpha-node",
        "evt-beta": "beta-node",
        "evt-blocked": "blocked-node",
    }

    def fake_classify(event, ready_nodes):
        node_id = node_map[event["event_id"]]
        assert any(node.node_id == node_id for node in ready_nodes)
        return {
            "category": "implementation_request",
            "intent": "advance_existing_node",
            "in_scope": True,
            "matched_node_id": node_id,
            "executor_recommendation": "jules",
            "requires_code_execution": True,
            "requires_human_review": False,
        }

    barrier = threading.Barrier(2, timeout=2)
    call_lock = threading.Lock()
    dispatched_nodes = []
    dispatch_threads = set()

    def fake_dispatch(job, repo):
        assert repo == "owner/repo"
        assert job["node_id"] in {"alpha-node", "beta-node"}

        check_con = sqlite3.connect(db_path)
        job_row = check_con.execute(
            "SELECT status, queue_state FROM jobs WHERE job_id = ?",
            (job["job_id"],),
        ).fetchone()
        queue_row = check_con.execute(
            "SELECT queue FROM queue_records WHERE job_id = ?",
            (job["job_id"],),
        ).fetchone()
        check_con.close()

        assert job_row == ("ready", "ready")
        assert queue_row == ("ready",)

        with call_lock:
            dispatched_nodes.append(job["node_id"])
            dispatch_threads.add(threading.get_ident())

        barrier.wait()

        if job["node_id"] == "beta-node":
            return DispatchResult(success=False, error="simulated failure")
        return DispatchResult(
            success=True,
            issue_url=f"https://example.test/{job['job_id']}",
        )

    monkeypatch.setattr(runner, "classify", fake_classify)
    monkeypatch.setattr(runner, "dispatch", fake_dispatch)

    runner.run_heartbeat(
        project_id="parallel-test",
        repo="owner/repo",
        config_path=str(config_root),
    )

    assert set(dispatched_nodes) == {"alpha-node", "beta-node"}
    assert len(dispatch_threads) == 2

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    events = {
        row["event_id"]: row
        for row in con.execute(
            "SELECT event_id, status, scope_status, classification FROM events"
        ).fetchall()
    }
    jobs = {
        row["node_id"]: row
        for row in con.execute(
            "SELECT job_id, node_id, status, queue_state FROM jobs ORDER BY node_id"
        ).fetchall()
    }
    queue_records = {
        row["job_id"]: row["queue"]
        for row in con.execute("SELECT job_id, queue FROM queue_records").fetchall()
    }
    con.close()

    assert events["evt-alpha"]["status"] == "mapped"
    assert events["evt-beta"]["status"] == "classified"
    assert events["evt-blocked"]["status"] == "scope_blocked"
    assert "prerequisite-node" in events["evt-blocked"]["classification"]

    assert set(jobs) == {"alpha-node", "beta-node"}
    assert jobs["alpha-node"]["status"] == "running"
    assert jobs["alpha-node"]["queue_state"] == "running"
    assert jobs["beta-node"]["status"] == "failed"
    assert jobs["beta-node"]["queue_state"] == "failed"
    assert queue_records[jobs["alpha-node"]["job_id"]] == "running"
    assert queue_records[jobs["beta-node"]["job_id"]] == "failed"


def test_cross_project_event_filtering(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    opclaw_root = tmp_path / "opclaw"
    opclaw_root.mkdir()
    config_root = tmp_path / "config"

    _init_db(db_path)
    _insert_event(db_path, "evt-target")

    con = sqlite3.connect(db_path)
    con.execute(
        """
        INSERT INTO events (
            event_id, received_at, source, event_type, project_id, status
        ) VALUES (?, ?, 'github', 'issue.opened', 'other-project', 'received')
        """,
        ("evt-other", "2026-03-19T00:00:00+00:00"),
    )
    con.commit()
    con.close()

    _write_graph(config_root)

    monkeypatch.setattr(runner, "DB_PATH", db_path)
    monkeypatch.setattr(runner, "OPCLAW_ROOT", opclaw_root)

    seen_events = []
    def fake_classify(event, ready_nodes):
        seen_events.append(event["event_id"])
        return None

    monkeypatch.setattr(runner, "classify", fake_classify)

    runner.run_heartbeat(
        project_id="parallel-test",
        repo="owner/repo",
        config_path=str(config_root),
    )

    assert "evt-target" in seen_events
    assert "evt-other" not in seen_events
