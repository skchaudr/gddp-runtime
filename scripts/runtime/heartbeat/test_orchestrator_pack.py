"""Tests for the orchestrator wake pack.

The pack is the whole memory of a stateless orchestrator, so the properties
pinned here are the ones whose absence would silently mislead a wake: the
human gate staying distinct from in-flight work, a dead process being visible
as dead, plumbing anomalies surfacing as anomalies, and the render staying
small enough to be a delta zone.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from .graph_reader import GraphReader
from .orchestrator_pack import (
    assemble_pack,
    render_pack,
    spool_roots,
)

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


def _ago(seconds: int) -> str:
    return (NOW - timedelta(seconds=seconds)).isoformat()


@pytest.fixture
def config(tmp_path: Path) -> Path:
    """A three-node graph: one ready, one ready-but-gated, one blocked."""
    graphs = tmp_path / "graphs" / "demo"
    (graphs / "nodes").mkdir(parents=True)
    (graphs / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "project_id": "demo",
                "project_name": "Demo",
                "repo": "owner/demo",
                "execution_policy": {"max_concurrent_jobs": 3},
                "nodes": [
                    {"id": "alpha", "title": "Alpha", "status": "ready"},
                    {"id": "beta", "title": "Beta", "status": "ready"},
                    {"id": "gamma", "title": "Gamma", "status": "ready"},
                    {"id": "delta", "title": "Delta", "status": "pending"},
                ],
            }
        )
    )
    for node_id, depends in (
        ("alpha", []),
        ("beta", []),
        ("gamma", []),
        ("delta", ["alpha"]),
    ):
        (graphs / "nodes" / f"{node_id}.yaml").write_text(
            yaml.safe_dump(
                {
                    "node_id": node_id,
                    "title": node_id.title(),
                    "status": "pending" if node_id == "delta" else "ready",
                    "depends_on": depends,
                    "allowed_execution_modes": ["agent"],
                }
            )
        )
    return tmp_path


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(tmp_path / "queue.db")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY, project_id TEXT, repo TEXT, node_id TEXT,
            status TEXT, queue_state TEXT, attempt INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3, created_at TEXT
        );
        CREATE TABLE executor_sessions (
            session_db_id TEXT PRIMARY KEY, job_id TEXT, executor TEXT,
            session_id TEXT, state TEXT, created_at TEXT, updated_at TEXT,
            attempt_index INTEGER
        );
        CREATE TABLE results (
            result_id TEXT PRIMARY KEY, job_id TEXT, outcome TEXT,
            received_at TEXT
        );
        """
    )
    return con


def _job(con, job_id, node_id, status, *, created_s=100, queue_state=None):
    con.execute(
        "INSERT INTO jobs (job_id, project_id, repo, node_id, status,"
        " queue_state, attempt, max_attempts, created_at)"
        " VALUES (?,'demo','owner/demo',?,?,?,1,3,?)",
        (job_id, node_id, status, queue_state or status, _ago(created_s)),
    )


def _session(con, session_db_id, job_id, attempt_id, state, *, created_s=100):
    con.execute(
        "INSERT INTO executor_sessions (session_db_id, job_id, executor,"
        " session_id, state, created_at, updated_at, attempt_index)"
        " VALUES (?,?,'cursor_cli',?,?,?,?,1)",
        (session_db_id, job_id, attempt_id, state, _ago(created_s), _ago(created_s)),
    )


def _attempt(spool: Path, attempt_id: str, **files) -> Path:
    directory = spool / attempt_id
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (directory / name.replace("__", ".")).write_text(content)
    return directory


def _pack(con, config, spool, **kwargs):
    reader = GraphReader(str(config))
    return assemble_pack(
        con,
        reader,
        "demo",
        now=NOW,
        roots={"cursor_cli": spool},
        **kwargs,
    )


# ---------------------------------------------------------------------------


def test_human_gate_stays_distinct_from_in_flight(db, config, tmp_path):
    """A node held at review reads as gated, never as a worker to watch.

    Real state on gddp-runtime had five ready nodes whose jobs all sat in
    awaiting_review. Reporting those as in-flight would have every wake
    watching for progress on work that finished weeks earlier.
    """
    _job(db, "j1", "alpha", "running")
    _job(db, "j2", "beta", "awaiting_review")
    pack = _pack(db, config, tmp_path / "spool")

    assert pack.graph.ready_in_flight == ["alpha"]
    assert pack.graph.ready_at_gate == ["beta"]
    assert pack.graph.dispatchable == ["gamma"]
    assert [row["node_id"] for row in pack.human_gate] == ["beta"]


def test_blocked_node_names_the_dependency_it_waits_on(db, config, tmp_path):
    pack = _pack(db, config, tmp_path / "spool")

    assert pack.graph.blocked == [{"node_id": "delta", "waiting_on": ["alpha"]}]


def test_dead_process_without_terminal_record_reads_as_gone(db, config, tmp_path):
    """The pid is gone and exit.json never landed — worker gone, pipe broken."""
    spool = tmp_path / "spool"
    _attempt(spool, "att-1", events__jsonl='{"type":"turn_started"}\n', pid="999999")
    _job(db, "j1", "alpha", "running")
    _session(db, "s1", "j1", "att-1", "running")

    pack = _pack(db, config, spool)

    assert pack.workers[0].verdict == "gone"
    assert pack.plumbing[0].anomaly == (
        "process gone with the terminal record still missing"
    )


def test_live_process_with_recent_events_reads_as_progressing(db, config, tmp_path):
    spool = tmp_path / "spool"
    directory = _attempt(spool, "att-1", events__jsonl='{"type":"tool_started"}\n')
    (directory / "pid").write_text(str(os.getpid()))
    now = datetime.now(timezone.utc)
    _job(db, "j1", "alpha", "running")
    _session(db, "s1", "j1", "att-1", "running")

    reader = GraphReader(str(config))
    pack = assemble_pack(
        db, reader, "demo", now=now, roots={"cursor_cli": spool}, stall_s=600
    )

    assert pack.workers[0].verdict == "progressing"
    assert pack.workers[0].event_count == 1
    assert pack.plumbing[0].anomaly is None


def test_silent_worker_past_the_stall_threshold_reads_as_quiet(db, config, tmp_path):
    spool = tmp_path / "spool"
    directory = _attempt(spool, "att-1", events__jsonl="{}\n")
    (directory / "pid").write_text(str(os.getpid()))
    old = (NOW - timedelta(seconds=3600)).timestamp()
    os.utime(directory / "events.jsonl", (old, old))
    _job(db, "j1", "alpha", "running")
    _session(db, "s1", "j1", "att-1", "running")

    pack = _pack(db, config, spool, stall_s=600)

    assert pack.workers[0].verdict == "quiet"


def test_missing_spool_for_a_live_session_is_a_plumbing_anomaly(db, config, tmp_path):
    _job(db, "j1", "alpha", "running")
    _session(db, "s1", "j1", "att-missing", "dispatched")

    pack = _pack(db, config, tmp_path / "spool")

    assert pack.plumbing[0].spool_present is False
    assert pack.plumbing[0].anomaly == "spool directory is absent for a live session"


def test_capacity_reports_free_slots_against_the_policy_cap(db, config, tmp_path):
    _job(db, "j1", "alpha", "running")
    _job(db, "j2", "beta", "ready")

    pack = _pack(db, config, tmp_path / "spool")

    assert pack.capacity.max_concurrent_jobs == 3
    assert pack.capacity.active_jobs == 2
    assert pack.capacity.free_slots == 1


def test_evaluator_pending_is_separate_from_the_human_gate(db, config, tmp_path):
    """Collected work waiting on a verdict and accepted work waiting on Sab
    are different stalls with different owners."""
    _job(db, "j1", "alpha", "running")
    _session(db, "s1", "j1", "att-1", "collected", created_s=300)
    _job(db, "j2", "beta", "awaiting_review")

    pack = _pack(db, config, tmp_path / "spool")

    assert [row["node_id"] for row in pack.evaluator.pending] == ["alpha"]
    assert pack.evaluator.pending[0]["waiting_s"] == 300
    assert [row["node_id"] for row in pack.human_gate] == ["beta"]


def test_operator_steer_surfaces_as_a_pointer(db, config, tmp_path):
    spool = tmp_path / "spool"
    _attempt(spool, "att-1", steer__jsonl='{"message":"narrow scope"}\n', pid="1")
    _job(db, "j1", "alpha", "running")
    _session(db, "s1", "j1", "att-1", "running")

    pack = _pack(db, config, spool)

    assert len(pack.steer) == 1
    assert pack.steer[0]["attempt_id"] == "att-1"
    assert pack.steer[0]["path"].endswith("att-1/steer.jsonl")
    # A pointer, so the message body stays on disk.
    assert "narrow scope" not in json.dumps(pack.to_json_value())


def test_render_stays_within_the_delta_budget(db, config, tmp_path):
    """Pointer-and-count discipline holds the pack far under the 50k target."""
    spool = tmp_path / "spool"
    for index in range(6):
        _attempt(spool, f"att-{index}", events__jsonl="{}\n", pid="1")
        _job(db, f"j{index}", "alpha", "running")
        _session(db, f"s{index}", f"j{index}", f"att-{index}", "running")

    rendered = render_pack(_pack(db, config, spool))

    assert len(rendered) // 4 < 2000
    assert "PLUMBING" in rendered and "HUMAN GATE" in rendered


def test_attempt_id_with_a_path_separator_resolves_to_nothing(db, config, tmp_path):
    """Traversal stays contained: a crafted session id finds no directory."""
    _job(db, "j1", "alpha", "running")
    _session(db, "s1", "j1", "../escape", "running")

    pack = _pack(db, config, tmp_path / "spool")

    assert pack.plumbing[0].spool_present is False


def test_spool_roots_use_the_canonical_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GDDP_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("GDDP_ATTEMPT_SPOOL_DIR", str(tmp_path / "attempts"))
    monkeypatch.setenv("GDDP_CURSOR_CLI_SPOOL_DIR", str(tmp_path / "cursor"))
    monkeypatch.setenv("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR", str(tmp_path / "shared"))

    roots = spool_roots()

    assert roots["canonical"] == (tmp_path / "attempts").resolve()
    assert "cursor_cli" not in roots


def test_pack_locates_a_recorded_attempt_dir(db, config, tmp_path):
    recorded = tmp_path / "elsewhere" / "att-recorded"
    recorded.mkdir(parents=True)
    (recorded / "events.jsonl").write_text('{"type":"turn_started"}\n')
    (recorded / "pid").write_text("999999")
    _job(db, "j1", "alpha", "running")
    db.execute(
        "ALTER TABLE executor_sessions ADD COLUMN attempt_dir TEXT"
    )
    db.execute(
        "INSERT INTO executor_sessions (session_db_id, job_id, executor,"
        " session_id, state, created_at, updated_at, attempt_index, attempt_dir)"
        " VALUES ('s1','j1','cursor_cli','att-recorded','running',?,?,1,?)",
        (_ago(100), _ago(100), str(recorded)),
    )

    pack = _pack(db, config, tmp_path / "unused-spool")

    assert pack.plumbing[0].spool_present is True
    assert pack.workers[0].verdict == "gone"
