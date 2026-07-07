"""
classifier.py — Maps implementation requests to ready nodes.

The heartbeat only plans forward-path execution work. Return/review handling is
kept outside automatic dispatch.
"""

import re
import sqlite3
from typing import Optional

from .graph_reader import NodeData


_NODE_TAG_RE = re.compile(r"(?i)node[:\s-]+([a-z0-9_-]+)")


def classify(event: sqlite3.Row, ready_nodes: list[NodeData]) -> Optional[dict]:
    """
    Returns a classification dict if the event maps to a dispatchable node, else None.

    Rules for v1:
    - Only issue.opened events trigger dispatch
    - If there are no ready nodes, event is ignored
    - If there is exactly one ready node, it wins automatically
    - If there are multiple ready nodes, a `node: <id>` tag in event metadata
      (url, branch) is matched first; otherwise priority ordering applies
      (high > normal > low)
    """
    if event["event_type"] != "issue.opened":
        return None

    if not ready_nodes:
        return None

    ready_ids = {n.node_id for n in ready_nodes}

    # Try to match a `node: <id>` tag in event metadata (url, branch).
    target = None
    for field in ("url", "branch"):
        value = event[field] if field in event.keys() else None
        if not value:
            continue
        match = _NODE_TAG_RE.search(str(value))
        if match and match.group(1) in ready_ids:
            target = next(n for n in ready_nodes if n.node_id == match.group(1))
            break

    # Fall back to highest-priority ready node.
    if target is None:
        priority_order = {"high": 0, "normal": 1, "low": 2}
        target = sorted(ready_nodes, key=lambda n: priority_order.get(n.priority, 1))[0]

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
