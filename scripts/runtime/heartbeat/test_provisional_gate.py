"""
test_provisional_gate.py — Tests for the provisional-flow system writer.

Doctrine: provisional is scheduler-visible evidence, never graph truth.
complete stays human-only; human_gate nodes never move without the operator.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml

from scripts.runtime.heartbeat.provisional_gate import (
    maybe_mark_provisional,
    provisional_eligible,
)

# The writer imports gddp-config's node_cli for its surgical status
# rewriters; tests copy the real module so fixture and production share one
# implementation. Skip when no sibling config checkout is available.
_REAL_CONFIG = Path(
    os.environ.get("GDDP_CONFIG_PATH")
    or Path(__file__).resolve().parents[4] / "gddp-config"
)
_REAL_NODE_CLI = _REAL_CONFIG / "scripts" / "node_cli.py"

PASS_VERIFICATION = {
    "verdict": "pass",
    "integrity": {
        "intent_preserved": True,
        "graph_integrity_preserved": True,
        "required_human_review": False,
    },
}

NODE_YAML = """\
schema_version: '1.0'
schema_type: node
node_id: node-a
title: Node A
status: ready
priority: medium
unlocks: []
"""

PROJECT_YAML = """\
schema_version: '1.0'
project_id: proj
repo: owner/repo
nodes:
  - id: node-a
    status: ready
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
    (nodes / "node-a.yaml").write_text(NODE_YAML)
    (tmp_path / "graphs" / "proj" / "project.yaml").write_text(PROJECT_YAML)
    return tmp_path


def _status(config_root: Path) -> tuple[str, str]:
    node_doc = yaml.safe_load(
        (config_root / "graphs/proj/nodes/node-a.yaml").read_text()
    )
    project_text = (config_root / "graphs/proj/project.yaml").read_text()
    return node_doc["status"], project_text


def test_eligible_pass_marks_provisional_in_node_and_project(config_root):
    ok = maybe_mark_provisional(
        project_id="proj",
        node_id="node-a",
        verification=PASS_VERIFICATION,
        evidence_ref="res_test",
        config_path=str(config_root),
    )
    assert ok is True
    node_status, project_text = _status(config_root)
    assert node_status == "provisional"
    assert "status: provisional" in project_text


def test_failed_verdict_does_not_mark(config_root):
    bad = {**PASS_VERIFICATION, "verdict": "fail"}
    assert (
        maybe_mark_provisional(
            project_id="proj",
            node_id="node-a",
            verification=bad,
            evidence_ref="res_test",
            config_path=str(config_root),
        )
        is False
    )
    assert _status(config_root)[0] == "ready"


def test_integrity_lane_false_does_not_mark(config_root):
    bad = {
        "verdict": "pass",
        "integrity": {
            "intent_preserved": False,
            "graph_integrity_preserved": True,
            "required_human_review": False,
        },
    }
    assert (
        maybe_mark_provisional(
            project_id="proj",
            node_id="node-a",
            verification=bad,
            evidence_ref="res_test",
            config_path=str(config_root),
        )
        is False
    )
    assert _status(config_root)[0] == "ready"


def test_required_human_review_does_not_mark(config_root):
    bad = {
        "verdict": "pass",
        "integrity": {
            "intent_preserved": True,
            "graph_integrity_preserved": True,
            "required_human_review": True,
        },
    }
    assert (
        maybe_mark_provisional(
            project_id="proj",
            node_id="node-a",
            verification=bad,
            evidence_ref="res_test",
            config_path=str(config_root),
        )
        is False
    )
    assert _status(config_root)[0] == "ready"


def test_human_gate_node_is_never_marked(config_root):
    node_path = config_root / "graphs/proj/nodes/node-a.yaml"
    node_path.write_text(NODE_YAML + "human_gate: true\n")
    assert (
        maybe_mark_provisional(
            project_id="proj",
            node_id="node-a",
            verification=PASS_VERIFICATION,
            evidence_ref="res_test",
            config_path=str(config_root),
        )
        is False
    )
    assert _status(config_root)[0] == "ready"


def test_terminal_status_is_never_touched(config_root):
    node_path = config_root / "graphs/proj/nodes/node-a.yaml"
    node_path.write_text(NODE_YAML.replace("status: ready", "status: complete"))
    assert (
        maybe_mark_provisional(
            project_id="proj",
            node_id="node-a",
            verification=PASS_VERIFICATION,
            evidence_ref="res_test",
            config_path=str(config_root),
        )
        is False
    )
    assert _status(config_root)[0] == "complete"


def test_already_provisional_is_idempotent(config_root):
    node_path = config_root / "graphs/proj/nodes/node-a.yaml"
    node_path.write_text(NODE_YAML.replace("status: ready", "status: provisional"))
    assert (
        maybe_mark_provisional(
            project_id="proj",
            node_id="node-a",
            verification=PASS_VERIFICATION,
            evidence_ref="res_test",
            config_path=str(config_root),
        )
        is False
    )


def test_missing_integrity_lane_does_not_mark(config_root):
    assert provisional_eligible({"verdict": "pass"}) is False
    assert provisional_eligible({"verdict": "pass", "integrity": None}) is False


def test_confidence_is_not_a_gate(config_root):
    """Low confidence with a pass verdict still marks provisional — confidence
    orders the operator's review queue; it never gates flow (mode 1)."""
    low_conf = {
        "verdict": "pass",
        "integrity": {
            "intent_preserved": True,
            "graph_integrity_preserved": True,
            "required_human_review": False,
            "confidence": 0.05,
        },
    }
    assert (
        maybe_mark_provisional(
            project_id="proj",
            node_id="node-a",
            verification=low_conf,
            evidence_ref="res_test",
            config_path=str(config_root),
        )
        is True
    )
