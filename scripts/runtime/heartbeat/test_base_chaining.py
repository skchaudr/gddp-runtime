"""
test_base_chaining.py — Provisional base-chaining at dispatch.

A node whose dependency is provisional must build on that dependency's
recorded result commit, not on HEAD — the dependency's work is not merged
yet. Multiple provisional deps refuse; complete deps leave base at HEAD.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from scripts.runtime.heartbeat.runner import _chained_base

HEAD = "h" * 40
RESULT_A = "a" * 40
RESULT_B = "b" * 40


@pytest.fixture()
def con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE jobs (job_id TEXT PRIMARY KEY, node_id TEXT NOT NULL);
        CREATE TABLE executor_sessions (
            session_db_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            result_commit_sha TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )
    yield con
    con.close()


def _reader(statuses: dict[str, str]):
    nodes = [{"id": nid, "status": s} for nid, s in statuses.items()]
    return SimpleNamespace(
        load_project=lambda project_id: SimpleNamespace(nodes=nodes)
    )


def _node(*deps: str):
    return SimpleNamespace(depends_on=list(deps))


def _record_result(con, node_id: str, result_sha: str, when: str = "2026-07-30T00:00:00"):
    job_id = f"job_{node_id}_{result_sha[:4]}"
    con.execute("INSERT INTO jobs (job_id, node_id) VALUES (?, ?)", (job_id, node_id))
    con.execute(
        "INSERT INTO executor_sessions (session_db_id, job_id, result_commit_sha, updated_at)"
        " VALUES (?, ?, ?, ?)",
        (f"ses_{job_id}", job_id, result_sha, when),
    )


def test_no_deps_uses_head(con):
    base, reason = _chained_base(con, _node(), "proj", _reader({}), HEAD)
    assert base == HEAD and reason is None


def test_complete_dep_uses_head(con):
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "complete"}), HEAD
    )
    assert base == HEAD and reason is None


def test_provisional_dep_chains_to_its_result(con):
    _record_result(con, "dep-a", RESULT_A)
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}), HEAD
    )
    assert base == RESULT_A and reason is None


def test_latest_result_wins(con):
    _record_result(con, "dep-a", RESULT_A, when="2026-07-29T00:00:00")
    _record_result(con, "dep-a", RESULT_B, when="2026-07-30T00:00:00")
    base, _ = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}), HEAD
    )
    assert base == RESULT_B


def test_multiple_provisional_deps_refuse(con):
    base, reason = _chained_base(
        con,
        _node("dep-a", "dep-b"),
        "proj",
        _reader({"dep-a": "provisional", "dep-b": "provisional"}),
        HEAD,
    )
    assert base is None and "refused" in reason


def test_provisional_dep_without_result_defers(con):
    base, reason = _chained_base(
        con, _node("dep-a"), "proj", _reader({"dep-a": "provisional"}), HEAD
    )
    assert base is None and "no recorded result commit" in reason


def test_mixed_complete_and_provisional_chains(con):
    _record_result(con, "dep-b", RESULT_B)
    base, reason = _chained_base(
        con,
        _node("dep-a", "dep-b"),
        "proj",
        _reader({"dep-a": "complete", "dep-b": "provisional"}),
        HEAD,
    )
    assert base == RESULT_B and reason is None


def test_missing_graph_falls_back_to_head(con):
    class _Missing:
        def load_project(self, project_id):
            raise FileNotFoundError("no graph")

    base, reason = _chained_base(con, _node("dep-a"), "proj", _Missing(), HEAD)
    assert base == HEAD and reason is None
