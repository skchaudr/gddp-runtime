"""
test_graph_updater.py — Verifies runtime graph mutation stays disabled.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.runtime.graph_updater import update_graph_node_complete


def test_update_graph_node_complete_is_disabled():
    result = update_graph_node_complete("p1", "n1", "pr123", "2023-10-27")
    assert result == {
        "ok": False,
        "reason": "graph_mutation_disabled_review_required",
    }
