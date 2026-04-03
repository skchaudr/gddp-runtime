"""
graph_updater.py — Disabled runtime graph mutation entrypoint.

Graph and gddp-config remain human-owned project truth. Runtime may not call
this module to mark nodes complete or write completion state back into
gddp-config. Any graph edits must happen through an explicit human review flow
outside runtime execution.
"""

from typing import Any, Dict


def update_graph_node_complete(*_args, **_kwargs) -> Dict[str, Any]:
    """
    Legacy compatibility stub.

    Returns a disabled response instead of mutating project truth.
    """
    return {
        "ok": False,
        "reason": "graph_mutation_disabled_review_required",
    }
