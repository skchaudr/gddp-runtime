"""
classifier.py — Maps implementation requests to ready nodes.

The heartbeat only plans forward-path execution work. Return/review handling is
kept outside automatic dispatch.
"""

import sqlite3
from typing import Optional

from .graph_reader import NodeData


def classify(event: sqlite3.Row, ready_nodes: list[NodeData]) -> Optional[dict]:
    """
    Returns a classification dict if the event maps to a dispatchable node, else None.

    Rules for v1:
    - Only issue.opened events trigger dispatch
    - If there are no ready nodes, event is ignored
    - If there is exactly one ready node, it wins automatically
    - If there are multiple ready nodes, priority ordering applies (high > normal > low)
    """
    if event["event_type"] != "issue.opened":
        return None

    if not ready_nodes:
        return None

    # Pick highest-priority ready node
    priority_order = {"high": 0, "normal": 1, "low": 2}
    # min() is O(N) compared to sorted()[0] which is O(N log N)
    target = min(ready_nodes, key=lambda n: priority_order.get(n.priority, 1))

    return {
        "category":                "implementation_request",
        "intent":                  "implement_existing_node",
        "in_scope":                True,
        "matched_node_id":         target.node_id,
        "executor_recommendation": _pick_executor(target),
        "requires_code_execution": True,
        "requires_human_review":   False,
    }


def _pick_executor(node: NodeData) -> str:
    """Pick the first declared execution mode, preserving graph ordering."""
    modes = node.allowed_execution_modes
    return modes[0] if modes else "jules"
