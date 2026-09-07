"""
test_scope_checker.py — Tests for check_scope duplicate dispatch and dependency guards.

Guards:
1. Active job guard scoped to project_id AND node_id (ready, running, awaiting_review).
   Active jobs for the same node in another project must NOT suppress this project.
2. Dependency check — all depends_on nodes must be complete or provisional in project graph.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from scripts.runtime.heartbeat.graph_reader import NodeData
from scripts.runtime.heartbeat.scope_checker import check_scope


def _mem_con() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )
    return con


def _reader(statuses: dict[str, str] | None = None):
    statuses = statuses or {}
    nodes = [{"id": nid, "status": s} for nid, s in statuses.items()]
    return SimpleNamespace(
        load_project=lambda project_id: SimpleNamespace(nodes=nodes)
    )


def _node(node_id: str = "node-a", *deps: str) -> NodeData:
    return NodeData(
        node_id=node_id,
        title="Node A",
        status="pending",
        type="task",
        why="test",
        depends_on=list(deps),
        acceptance_criteria=[],
        constraints=[],
        allowed_execution_modes=["agent"],
        required_artifacts=[],
        priority="normal",
        unlocks=[],
    )


def test_no_dependencies_and_no_jobs_is_safe():
    con = _mem_con()
    result = check_scope(_node("node-a"), "proj-1", con, _reader())
    assert result.safe is True
    assert bool(result) is True


@pytest.mark.parametrize("status", ["ready", "running", "awaiting_review"])
def test_active_job_in_same_project_blocks_dispatch(status: str):
    con = _mem_con()
    con.execute(
        "INSERT INTO jobs (job_id, project_id, node_id, status) VALUES (?, ?, ?, ?)",
        ("job-1", "proj-1", "node-a", status),
    )
    result = check_scope(_node("node-a"), "proj-1", con, _reader())
    assert result.safe is False
    assert "job-1" in result.reason
    assert "node-a" in result.reason


@pytest.mark.parametrize("status", ["done", "failed", "completed", "cancelled"])
def test_terminal_job_in_same_project_does_not_block(status: str):
    con = _mem_con()
    con.execute(
        "INSERT INTO jobs (job_id, project_id, node_id, status) VALUES (?, ?, ?, ?)",
        ("job-1", "proj-1", "node-a", status),
    )
    result = check_scope(_node("node-a"), "proj-1", con, _reader())
    assert result.safe is True


def test_cross_project_active_job_does_not_suppress_this_project():
    con = _mem_con()
    # Another project has an active job for the exact same node_id
    con.execute(
        "INSERT INTO jobs (job_id, project_id, node_id, status) VALUES (?, ?, ?, ?)",
        ("job-other", "proj-other", "node-a", "running"),
    )
    result = check_scope(_node("node-a"), "proj-1", con, _reader())
    assert result.safe is True


def test_same_project_active_job_blocks_even_with_cross_project_jobs():
    con = _mem_con()
    con.execute(
        "INSERT INTO jobs (job_id, project_id, node_id, status) VALUES (?, ?, ?, ?)",
        ("job-other", "proj-other", "node-a", "running"),
    )
    con.execute(
        "INSERT INTO jobs (job_id, project_id, node_id, status) VALUES (?, ?, ?, ?)",
        ("job-ours", "proj-1", "node-a", "ready"),
    )
    result = check_scope(_node("node-a"), "proj-1", con, _reader())
    assert result.safe is False
    assert "job-ours" in result.reason


def test_missing_graph_blocks_with_reason():
    con = _mem_con()

    class _MissingReader:
        def load_project(self, project_id: str):
            raise FileNotFoundError(f"Project graph {project_id} not found")

    result = check_scope(_node("node-a", "dep-1"), "proj-1", con, _MissingReader())
    assert result.safe is False
    assert "not found" in result.reason


def test_unsatisfied_dependency_blocks_dispatch():
    con = _mem_con()
    reader = _reader({"dep-1": "pending"})
    result = check_scope(_node("node-a", "dep-1"), "proj-1", con, reader)
    assert result.safe is False
    assert "Dependency 'dep-1' is not satisfied" in result.reason


def test_satisfied_dependency_complete_allows_dispatch():
    con = _mem_con()
    reader = _reader({"dep-1": "complete"})
    result = check_scope(_node("node-a", "dep-1"), "proj-1", con, reader)
    assert result.safe is True


def test_satisfied_dependency_provisional_allows_dispatch():
    con = _mem_con()
    reader = _reader({"dep-1": "provisional"})
    result = check_scope(_node("node-a", "dep-1"), "proj-1", con, reader)
    assert result.safe is True


def test_legacy_jobs_table_without_project_id_supported():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE jobs (job_id TEXT, node_id TEXT, status TEXT)")
    con.execute(
        "INSERT INTO jobs VALUES ('legacy-job', 'node-a', 'running')"
    )
    result = check_scope(_node("node-a"), "proj-1", con, _reader())
    assert result.safe is False
    assert "legacy-job" in result.reason
