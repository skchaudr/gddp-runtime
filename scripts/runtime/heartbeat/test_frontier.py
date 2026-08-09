"""
test_frontier.py — Tests for automatic frontier advance.

Doctrine: only non-terminal scheduler statuses move (pending → ready);
human_gate nodes never advance; duplicate dispatch is guarded by active
jobs and pending frontier events; one tick advances one graph layer.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml

from scripts.runtime.heartbeat.frontier import advance_frontier
from scripts.runtime.heartbeat.graph_reader import GraphReader

# Same pattern as test_provisional_status.py: the writer uses gddp-config's
# node_cli for surgical status rewrites; copy the real module so fixture
# and production share one implementation.
_REAL_CONFIG = Path(
    os.environ.get("GDDP_CONFIG_PATH")
    or Path(__file__).resolve().parents[4] / "gddp-config"
)
_REAL_NODE_CLI = _REAL_CONFIG / "scripts" / "node_cli.py"

PROJECT_YAML = """\
schema_version: '1.0'
schema_type: project_graph
project_id: proj
project_name: Test Project
repo: owner/repo
execution_policy:
  frontier_auto_advance: true
nodes:
  - id: node-a
    status: complete
  - id: node-b
    status: provisional
  - id: node-c
    status: pending
  - id: node-d
    status: pending
  - id: node-e
    status: pending
  - id: node-f
    status: pending
  - id: node-g
    status: pending
  - id: node-h
    status: ready
  - id: node-i
    status: pending
"""

NODE_TEMPLATES = {
    "node-a": "status: complete",
    "node-b": "status: provisional",
    "node-c": "status: pending\ndepends_on:\n  - node-a\n  - node-b",
    "node-d": "status: pending\nhuman_gate: true\ndepends_on:\n  - node-b",
    "node-e": "status: pending\ndepends_on:\n  - node-a",
    "node-f": "status: pending\ndepends_on:\n  - node-missing",
    "node-g": "status: pending",
    "node-h": "status: ready",
    "node-i": "status: pending\ndepends_on:\n  - node-a",
}

NODE_YAML = """\
schema_version: '1.0'
schema_type: node
node_id: {node_id}
title: {node_id}
{body}
priority: medium
unlocks: []
"""


@pytest.fixture()
def config_root(tmp_path: Path) -> Path:
    if not _REAL_NODE_CLI.exists():
        pytest.skip("gddp-config checkout with scripts/node_cli.py not available")
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy(_REAL_NODE_CLI, scripts_dir / "node_cli.py")
    nodes = tmp_path / "graphs" / "proj" / "nodes"
    nodes.mkdir(parents=True)
    for node_id, body in NODE_TEMPLATES.items():
        (nodes / f"{node_id}.yaml").write_text(
            NODE_YAML.format(node_id=node_id, body=body)
        )
    (tmp_path / "graphs" / "proj" / "project.yaml").write_text(PROJECT_YAML)
    return tmp_path


@pytest.fixture()
def con():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE jobs (job_id TEXT PRIMARY KEY, project_id TEXT, "
        "node_id TEXT, status TEXT)"
    )
    con.execute(
        "CREATE TABLE events (event_id TEXT PRIMARY KEY, schema_version TEXT, "
        "received_at TEXT, source TEXT, event_type TEXT, actor TEXT, url TEXT, "
        "project_id TEXT, project_node_candidates TEXT, scope_status TEXT, "
        "priority TEXT, risk_level TEXT, routing TEXT, status TEXT, repo TEXT)"
    )
    # node-e has an active job; node-i has a pending frontier event.
    con.execute(
        "INSERT INTO jobs VALUES ('job_e', 'proj', 'node-e', 'running')"
    )
    con.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, url, "
        "project_id, status) VALUES ('evt_seed', 'now', 'frontier_auto', "
        "'issue.opened', 'frontier-dispatch://node: node-i', 'proj', 'received')"
    )
    yield con
    con.close()


def _node_status(config_root: Path, node_id: str) -> str:
    doc = yaml.safe_load(
        (config_root / "graphs/proj/nodes" / f"{node_id}.yaml").read_text()
    )
    return doc["status"]


def _index_statuses(config_root: Path) -> dict:
    doc = yaml.safe_load((config_root / "graphs/proj/project.yaml").read_text())
    return {n["id"]: n["status"] for n in doc["nodes"]}


def _frontier_events(con) -> list[tuple]:
    return con.execute(
        "SELECT url, status FROM events WHERE source = 'frontier_auto' "
        "AND event_id != 'evt_seed' ORDER BY url"
    ).fetchall()


def test_advances_unblocked_and_injects_events(config_root, con):
    reader = GraphReader(config_path=str(config_root))
    transitioned = advance_frontier(con, reader, "proj")

    assert sorted(transitioned) == ["node-c", "node-g"]
    assert _node_status(config_root, "node-c") == "ready"
    assert _node_status(config_root, "node-g") == "ready"
    index = _index_statuses(config_root)
    assert index["node-c"] == "ready"
    assert index["node-g"] == "ready"

    events = _frontier_events(con)
    assert events == [
        ("frontier-dispatch://node: node-c", "received"),
        ("frontier-dispatch://node: node-g", "received"),
    ]


def test_skips_gate_active_missing_dep_and_non_pending(config_root, con):
    reader = GraphReader(config_path=str(config_root))
    advance_frontier(con, reader, "proj")

    assert _node_status(config_root, "node-d") == "pending"  # human_gate
    assert _node_status(config_root, "node-e") == "pending"  # active job
    assert _node_status(config_root, "node-f") == "pending"  # dep missing
    assert _node_status(config_root, "node-h") == "ready"    # already ready
    assert _node_status(config_root, "node-i") == "pending"  # pending event


def test_second_tick_is_idempotent(config_root, con):
    reader = GraphReader(config_path=str(config_root))
    first = advance_frontier(con, reader, "proj")
    second = advance_frontier(con, reader, "proj")

    assert first
    assert second == []
    assert _frontier_events(con) == [
        ("frontier-dispatch://node: node-c", "received"),
        ("frontier-dispatch://node: node-g", "received"),
    ]


def test_opt_out_by_default(config_root, con, tmp_path):
    project_yaml = config_root / "graphs/proj/project.yaml"
    project_yaml.write_text(PROJECT_YAML.replace("  frontier_auto_advance: true\n", ""))
    reader = GraphReader(config_path=str(config_root))

    assert advance_frontier(con, reader, "proj") == []
    assert _node_status(config_root, "node-c") == "pending"
    assert _frontier_events(con) == []


def test_rejected_provisional_dependency_reblocks(config_root, con):
    """A provisional dep rejected back to ready is no longer satisfied."""
    reader = GraphReader(config_path=str(config_root))
    node_b = config_root / "graphs/proj/nodes/node-b.yaml"
    node_b.write_text(node_b.read_text().replace("status: provisional", "status: ready"))
    project_yaml = config_root / "graphs/proj/project.yaml"
    project_yaml.write_text(project_yaml.read_text().replace("status: provisional", "status: ready"))

    assert advance_frontier(con, reader, "proj") == ["node-g"]
    assert _node_status(config_root, "node-c") == "pending"
