"""
Tests for OpenClaw v0 — context reader, dispatch blocking, and escalation.
"""

import sqlite3
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from .context_reader import read_project_state, read_recent_activity, ProjectState, RecentActivity
from .schema import DispatchResult, EscalateResult, NoOpResult, OpenClawResult
from .powers.escalate import run as escalate


# --- Fixtures ---

@pytest.fixture
def mock_graph_reader():
    """A GraphReader that returns a simple 3-node project."""
    reader = MagicMock()

    project = MagicMock()
    project.project_id = "test-project"
    project.repo = "skchaudr/test-project"
    project.nodes = [
        {"id": "node-a", "status": "complete"},
        {"id": "node-b", "status": "pending"},
        {"id": "node-c", "status": "pending"},
    ]
    reader.load_project.return_value = project

    def load_node(project_id, node_id):
        nodes = {
            "node-a": MagicMock(
                node_id="node-a", status="complete", depends_on=[], priority="normal",
                title="Node A", why="", acceptance=[], constraints=[],
                allowed_execution_modes=["jules"], required_artifacts=[], unlocks=["node-b"],
                type="capability",
            ),
            "node-b": MagicMock(
                node_id="node-b", status="pending", depends_on=["node-a"], priority="high",
                title="Node B", why="", acceptance=[], constraints=[],
                allowed_execution_modes=["jules"], required_artifacts=[], unlocks=["node-c"],
                type="capability",
            ),
            "node-c": MagicMock(
                node_id="node-c", status="pending", depends_on=["node-b"], priority="normal",
                title="Node C", why="", acceptance=[], constraints=[],
                allowed_execution_modes=["jules"], required_artifacts=[], unlocks=[],
                type="capability",
            ),
        }
        if node_id not in nodes:
            raise FileNotFoundError(f"No node: {node_id}")
        return nodes[node_id]

    reader.load_node.side_effect = load_node
    return reader


@pytest.fixture
def in_memory_db():
    """SQLite in-memory DB with the tables OpenClaw needs."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row

    con.execute("""
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            node_id TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    con.execute("""
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    con.execute("""
        CREATE TABLE return_results (
            id TEXT PRIMARY KEY,
            repo_name TEXT NOT NULL,
            node_id TEXT,
            pr_number INTEGER,
            merged_at TEXT,
            status TEXT NOT NULL,
            reason TEXT,
            commit_sha TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    return con


# --- Test context_reader ---

def test_read_project_state_categorizes_nodes(mock_graph_reader):
    state = read_project_state(mock_graph_reader, "test-project")

    assert isinstance(state, ProjectState)
    assert len(state.complete_nodes) == 1
    assert len(state.pending_nodes) == 2
    assert state.complete_nodes[0].node_id == "node-a"


def test_read_recent_activity_shape(in_memory_db):
    activity = read_recent_activity(in_memory_db, "test-project")

    assert isinstance(activity, RecentActivity)
    assert activity.active_jobs == []
    assert activity.stale_jobs == []
    assert activity.stale_events == []
    assert activity.recent_results == []


def test_read_recent_activity_finds_active_jobs(in_memory_db):
    in_memory_db.execute(
        "INSERT INTO jobs (job_id, node_id, status, created_at) VALUES (?, ?, ?, datetime('now'))",
        ("job_001", "node-b", "running",),
    )
    in_memory_db.commit()

    activity = read_recent_activity(in_memory_db, "test-project")
    assert len(activity.active_jobs) == 1
    assert activity.active_jobs[0]["job_id"] == "job_001"


# --- Test dispatch blocking ---

def test_dispatch_blocked_when_job_active(mock_graph_reader, in_memory_db):
    """dispatch_next should escalate if a job is already active."""
    from .context_reader import read_context

    # Insert an active job
    in_memory_db.execute(
        "INSERT INTO jobs (job_id, node_id, status, created_at) VALUES (?, ?, ?, datetime('now'))",
        ("job_active", "node-b", "running",),
    )
    in_memory_db.commit()

    ctx = read_context(mock_graph_reader, in_memory_db, "test-project", {"event": "cron"})

    from .powers.dispatch_next import run as dispatch_run
    result = dispatch_run(ctx)

    assert isinstance(result, EscalateResult)
    assert "active job" in result.reason


# --- Test escalate writes result ---

def test_escalate_returns_valid_schema():
    result = escalate(reason="test_reason", node_id="node-x", project_id="test")

    assert isinstance(result, EscalateResult)
    assert result.action == "escalate"
    assert result.reason == "test_reason"
    assert result.node_id == "node-x"
    assert result.ok is True


# --- Test Pydantic schema enforcement ---

def test_dispatch_result_rejects_bad_data():
    """Pydantic should reject a DispatchResult with missing fields."""
    with pytest.raises(Exception):
        DispatchResult(action="dispatch_next", node_id="x")  # missing issue_number, etc.


def test_dispatch_result_accepts_good_data():
    result = DispatchResult(
        action="dispatch_next",
        node_id="node-b",
        project_id="test-project",
        issue_number=42,
        issue_url="https://github.com/skchaudr/test-project/issues/42",
        ok=True,
    )
    assert result.issue_number == 42
    assert result.model_dump()["action"] == "dispatch_next"
