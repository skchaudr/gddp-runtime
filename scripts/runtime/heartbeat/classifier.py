"""
classifier.py — Maps implementation requests to ready nodes.

The heartbeat only plans forward-path execution work. Return/review handling is
kept outside automatic dispatch.
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

from .graph_reader import NodeData


_NODE_TAG_RE = re.compile(r"(?i)node[:\s-]+([a-z0-9_-]+)")


def _tag_sources(event) -> list[str]:
    """Places a `node: <id>` tag may legitimately appear."""
    sources = []
    for field in ("url", "branch"):
        value = event[field] if field in event.keys() else None
        if value:
            sources.append(str(value))
    # Issue title/body live only in the saved raw payload, not the event row.
    raw_path = (
        event["raw_payload_path"] if "raw_payload_path" in event.keys() else None
    )
    if raw_path:
        try:
            payload = json.loads(Path(raw_path).read_text())
            issue = payload.get("issue", {})
            for text in (issue.get("title"), issue.get("body")):
                if text:
                    sources.append(str(text))
        except (OSError, ValueError):
            pass  # unreadable payload → no extra sources, event stays untagged
    return sources


def classify(event: sqlite3.Row, ready_nodes: list[NodeData]) -> Optional[dict]:
    """
    Returns a classification dict if the event maps to a dispatchable node, else None.

    Rules:
    - Only issue.opened events trigger dispatch
    - Dispatch requires an explicit `node: <id>` tag (in url, branch, or the
      issue title/body from the raw payload) naming a ready node. There is
      deliberately NO fallback: repos are public, so an untagged issue must
      never spend executor budget on a guessed node.
    """
    if event["event_type"] != "issue.opened":
        return None

    if not ready_nodes:
        return None

    ready_ids = {n.node_id for n in ready_nodes}

    target = None
    for value in _tag_sources(event):
        match = _NODE_TAG_RE.search(value)
        if match and match.group(1) in ready_ids:
            target = next(n for n in ready_nodes if n.node_id == match.group(1))
            break

    if target is None:
        return None  # no explicit tag for a ready node → ignored, auditable

    recommendation = _pick_executor(target)
    routing_raw = event["routing"] if "routing" in event.keys() else None
    if routing_raw:
        try:
            selected = (json.loads(routing_raw) or {}).get("selected_executor")
        except ValueError:
            selected = None
        if selected:
            # Operator preselection (gddp dispatch). Never fall back silently:
            # an executor the node does not allow ignores the event auditably.
            if selected not in target.allowed_execution_modes:
                return None
            recommendation = selected

    return {
        "category":                "implementation_request",
        "intent":                  "implement_existing_node",
        "in_scope":                True,
        "matched_node_id":         target.node_id,
        "executor_recommendation": recommendation,
        "requires_code_execution": True,
        "requires_human_review":   False,
    }


def _pick_executor(node: NodeData) -> str:
    """Pick the first declared execution mode, preserving graph ordering."""
    modes = node.allowed_execution_modes
    return modes[0] if modes else "jules"
