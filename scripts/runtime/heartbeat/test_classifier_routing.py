"""test_classifier_routing.py — Operator executor preselection via event routing.

The gddp dispatch surface injects manual events whose `routing` JSON may name
a selected_executor. The classifier honors it only when the node allows that
executor; anything else must ignore the event auditably, never fall back.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.runtime.heartbeat.classifier import classify
from scripts.runtime.heartbeat.graph_reader import NodeData


def _node(modes=("local_subprocess", "jules_api")) -> NodeData:
    return NodeData(
        node_id="verdict-confidence-split",
        title="t",
        status="ready",
        type="capability",
        why="w",
        depends_on=[],
        acceptance_criteria=[],
        constraints=[],
        allowed_execution_modes=list(modes),
        required_artifacts=[],
        priority="high",
        unlocks=[],
    )


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE events (event_id TEXT, event_type TEXT, url TEXT, "
        "branch TEXT, raw_payload_path TEXT, routing TEXT)"
    )
    return c


def _event(con, routing=None):
    con.execute("DELETE FROM events")
    con.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
        (
            "evt_1",
            "issue.opened",
            "manual-dispatch://node: verdict-confidence-split",
            None,
            None,
            json.dumps(routing) if routing is not None else None,
        ),
    )
    return con.execute("SELECT * FROM events").fetchone()


def test_no_routing_uses_first_declared_mode(con):
    result = classify(_event(con), [_node()])
    assert result["executor_recommendation"] == "local_subprocess"


def test_valid_preselection_overrides_default(con):
    result = classify(
        _event(con, routing={"selected_executor": "jules_api"}), [_node()]
    )
    assert result["executor_recommendation"] == "jules_api"


def test_agent_neutral_mode_accepts_concrete_preselection(con):
    result = classify(
        _event(con, routing={"selected_executor": "local_subprocess"}),
        [_node(modes=("agent",))],
    )
    assert result["executor_recommendation"] == "local_subprocess"


def test_disallowed_preselection_ignores_event(con):
    result = classify(
        _event(con, routing={"selected_executor": "droid"}), [_node()]
    )
    assert result is None


def test_malformed_routing_falls_back_to_declared_mode(con):
    con.execute("DELETE FROM events")
    con.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
        ("evt_1", "issue.opened", "manual-dispatch://node: verdict-confidence-split",
         None, None, "{not json"),
    )
    event = con.execute("SELECT * FROM events").fetchone()
    result = classify(event, [_node()])
    assert result["executor_recommendation"] == "local_subprocess"
