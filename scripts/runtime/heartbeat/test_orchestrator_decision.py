"""Tests for the orchestrator decision channel.

The properties pinned here are the ones whose absence would let a stateless
orchestrator do damage: repeated wakes queueing repeated dispatches, an
improvised action reaching the runtime, rationale going missing from a
receipt, or graph truth moving on an agent's say-so.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from .orchestrator_decision import (
    ACTIONS,
    Decision,
    DecisionError,
    apply_decision,
    parse_decision,
    recent_decisions,
)

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


@dataclass
class FakeProject:
    project_id: str = "demo"
    repo: str = "owner/demo"
    execution_policy: dict = None

    def __post_init__(self):
        if self.execution_policy is None:
            self.execution_policy = {}


@pytest.fixture
def con() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY, schema_version TEXT, received_at TEXT,
            source TEXT, event_type TEXT, actor TEXT, url TEXT,
            project_id TEXT, project_node_candidates TEXT, scope_status TEXT,
            priority TEXT, risk_level TEXT, routing TEXT, status TEXT, repo TEXT
        );
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY, project_id TEXT, node_id TEXT, status TEXT
        );
        """
    )
    return connection


def _dispatch(node_id="alpha", **extra):
    return {
        "action": "dispatch",
        "node_id": node_id,
        "reason": "only dispatchable node and capacity is free",
        **extra,
    }


# --- parsing ---------------------------------------------------------------


def test_unknown_action_is_refused_by_name():
    """An improvised action fails here rather than becoming a new job type."""
    with pytest.raises(DecisionError) as exc:
        parse_decision({"action": "reassign_team", "reason": "seems right"})

    assert "reassign_team" in str(exc.value)
    assert "dispatch" in str(exc.value)


def test_every_action_in_the_vocabulary_parses():
    for action in sorted(ACTIONS):
        raw = {"action": action, "reason": "because", "node_id": "alpha"}
        assert parse_decision(raw).action == action


def test_rationale_is_mandatory():
    """A receipt without a reason withholds the only part the next wake needs."""
    with pytest.raises(DecisionError, match="reason"):
        parse_decision({"action": "hold"})


def test_node_naming_actions_require_a_node():
    with pytest.raises(DecisionError, match="node_id"):
        parse_decision({"action": "dispatch", "reason": "go"})


def test_hold_needs_no_node():
    assert parse_decision({"action": "hold", "reason": "all healthy"}).node_id is None


def test_counts_must_be_positive_integers():
    with pytest.raises(DecisionError, match="to_n"):
        parse_decision({**_dispatch(), "to_n": 0})
    with pytest.raises(DecisionError, match="from_n"):
        parse_decision({**_dispatch(), "from_n": True})
    with pytest.raises(DecisionError, match="next_wake_s"):
        parse_decision({"action": "hold", "reason": "r", "next_wake_s": -30})


def test_a_json_string_decision_parses():
    decision = parse_decision(json.dumps(_dispatch()))

    assert decision.action == "dispatch" and decision.node_id == "alpha"


def test_unreadable_json_names_itself():
    with pytest.raises(DecisionError, match="unreadable JSON"):
        parse_decision("{not json")


# --- applying --------------------------------------------------------------


def test_dispatch_injects_an_event_the_pipeline_recognises(con, tmp_path):
    """The row must carry the `node: <id>` url tag the classifier routes on."""
    applied = apply_decision(
        con,
        FakeProject(),
        parse_decision(_dispatch()),
        now=NOW,
        receipts_root=tmp_path,
    )

    row = con.execute("SELECT * FROM events").fetchone()
    assert applied.effected is True
    assert row["source"] == "orchestrator"
    assert row["event_type"] == "issue.opened"
    assert row["url"] == "orchestrator-dispatch://node: alpha"
    assert json.loads(row["project_node_candidates"]) == ["alpha"]
    assert row["status"] == "received"
    assert row["repo"] == "owner/demo"


def test_repeated_wakes_queue_one_dispatch(con, tmp_path):
    """Every pulse re-reaches the same conclusion. Only the first may land.

    Without this guard a node that takes three ticks to start collects three
    dispatch events, and a wake meaning "start this once" becomes a queue.
    """
    for _ in range(3):
        apply_decision(
            con,
            FakeProject(),
            parse_decision(_dispatch()),
            now=NOW,
            receipts_root=tmp_path,
        )

    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_dispatch_declines_when_a_job_already_holds_the_node(con, tmp_path):
    con.execute(
        "INSERT INTO jobs (job_id, project_id, node_id, status)"
        " VALUES ('j1','demo','alpha','running')"
    )

    applied = apply_decision(
        con, FakeProject(), parse_decision(_dispatch()), now=NOW, receipts_root=tmp_path
    )

    assert applied.effected is False
    assert "j1" in applied.detail
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_a_node_at_the_human_gate_stays_undispatched(con, tmp_path):
    """awaiting_review belongs to the operator; a wake may not reopen it."""
    con.execute(
        "INSERT INTO jobs (job_id, project_id, node_id, status)"
        " VALUES ('j1','demo','alpha','awaiting_review')"
    )

    applied = apply_decision(
        con, FakeProject(), parse_decision(_dispatch()), now=NOW, receipts_root=tmp_path
    )

    assert applied.effected is False
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_project_default_executor_rides_the_routing(con, tmp_path):
    project = FakeProject(execution_policy={"default_executor": "cursor_cli"})

    apply_decision(
        con, project, parse_decision(_dispatch()), now=NOW, receipts_root=tmp_path
    )

    row = con.execute("SELECT routing FROM events").fetchone()
    assert json.loads(row["routing"]) == {"selected_executor": "cursor_cli"}


def test_absent_default_executor_leaves_routing_to_the_node(con, tmp_path):
    apply_decision(
        con, FakeProject(), parse_decision(_dispatch()), now=NOW, receipts_root=tmp_path
    )

    row = con.execute("SELECT routing FROM events").fetchone()
    assert json.loads(row["routing"]) == {}


def test_worker_budget_rides_the_routing(con, tmp_path):
    """dispatch's to_n is the advised worker count; it must reach the event,
    not survive only in the receipt."""
    apply_decision(
        con,
        FakeProject(),
        parse_decision({**_dispatch(), "to_n": 3}),
        now=NOW,
        receipts_root=tmp_path,
    )

    row = con.execute("SELECT routing FROM events").fetchone()
    assert json.loads(row["routing"]) == {"worker_budget": 3}


def test_worker_budget_shares_routing_with_a_default_executor(con, tmp_path):
    project = FakeProject(execution_policy={"default_executor": "cursor_cli"})

    apply_decision(
        con,
        project,
        parse_decision({**_dispatch(), "to_n": 2}),
        now=NOW,
        receipts_root=tmp_path,
    )

    row = con.execute("SELECT routing FROM events").fetchone()
    assert json.loads(row["routing"]) == {
        "selected_executor": "cursor_cli",
        "worker_budget": 2,
    }


@pytest.mark.parametrize("action", sorted(ACTIONS - {"dispatch"}))
def test_advisory_actions_touch_no_runtime_state(con, tmp_path, action):
    applied = apply_decision(
        con,
        FakeProject(),
        parse_decision({"action": action, "reason": "r", "node_id": "alpha"}),
        now=NOW,
        receipts_root=tmp_path,
    )

    assert applied.effected is False
    assert action in applied.detail
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_no_decision_writes_a_graph_file(con, tmp_path, monkeypatch):
    """Graph truth is the operator's. The applier reaches only events."""
    graph = tmp_path / "graphs" / "demo"
    graph.mkdir(parents=True)
    project_yaml = graph / "project.yaml"
    project_yaml.write_text("untouched")

    for action in sorted(ACTIONS):
        apply_decision(
            con,
            FakeProject(),
            parse_decision({"action": action, "reason": "r", "node_id": "alpha"}),
            now=NOW,
            receipts_root=tmp_path / "receipts",
        )

    assert project_yaml.read_text() == "untouched"
    tables = {
        row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert tables == {"events", "jobs"}


# --- receipts --------------------------------------------------------------


def test_receipt_preserves_the_reasoning_a_wipe_would_take(con, tmp_path):
    decision = parse_decision(
        {
            "action": "slice",
            "node_id": "alpha",
            "from_n": 3,
            "to_n": 6,
            "reason": "two independent implementation slices plus verification",
            "expect": "independent progress on both slices",
        }
    )

    applied = apply_decision(
        con, FakeProject(), decision, now=NOW, receipts_root=tmp_path
    )
    payload = json.loads(Path(applied.receipt_path).read_text())

    assert payload["decision"]["from_n"] == 3
    assert payload["decision"]["to_n"] == 6
    assert payload["decision"]["reason"].startswith("two independent")
    assert payload["decision"]["expect"] == "independent progress on both slices"


def test_next_wake_advice_round_trips_through_the_receipt(con, tmp_path):
    """The wait a wake sets is exactly the state the next wake needs when the
    run's interval is the orchestrator's to set."""
    decision = parse_decision(
        {"action": "hold", "reason": "gate holds everything", "next_wake_s": 120}
    )

    applied = apply_decision(
        con, FakeProject(), decision, now=NOW, receipts_root=tmp_path
    )
    payload = json.loads(Path(applied.receipt_path).read_text())

    assert payload["decision"]["next_wake_s"] == 120
    assert recent_decisions("demo", 1, receipts_root=tmp_path)[0]["next_wake_s"] == 120


def test_recent_decisions_returns_newest_first(con, tmp_path):
    for index, action in enumerate(["dispatch", "hold", "escalate"]):
        apply_decision(
            con,
            FakeProject(),
            parse_decision(
                {
                    "action": action,
                    "reason": f"r{index}",
                    "node_id": "alpha",
                    "wake_id": f"wake_{index}",
                }
            ),
            now=datetime(2026, 9, 4, 12, index, 0, tzinfo=timezone.utc),
            receipts_root=tmp_path,
        )

    rows = recent_decisions("demo", 2, receipts_root=tmp_path)

    assert [row["action"] for row in rows] == ["escalate", "hold"]
    assert rows[0]["reason"] == "r2"


def test_a_corrupt_receipt_costs_one_memory_rather_than_all(con, tmp_path):
    apply_decision(
        con,
        FakeProject(),
        parse_decision({"action": "hold", "reason": "healthy", "wake_id": "good"}),
        now=NOW,
        receipts_root=tmp_path,
    )
    (tmp_path / "demo" / "20260904T120100-bad.json").write_text("{truncated")

    rows = recent_decisions("demo", 5, receipts_root=tmp_path)

    assert [row["wake_id"] for row in rows] == ["good"]


def test_recent_decisions_on_a_fresh_project_is_empty(tmp_path):
    assert recent_decisions("never-run", 5, receipts_root=tmp_path) == []
