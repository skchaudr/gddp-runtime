"""
scope_checker.py — Guards against duplicate dispatch.

Before creating a job, verifies:
1. No active job already running for this node (status = running or ready)
2. All depends_on nodes are complete in project.yaml

This is the gate that prevents the infinite dispatch loop we hit in Phase 3-4.
"""

import sqlite3

from .graph_reader import GraphReader, NodeData


class ScopeCheckResult:
    def __init__(self, safe: bool, reason: str = ""):
        self.safe = safe
        self.reason = reason

    def __bool__(self):
        return self.safe


# Dependency satisfaction: complete (human-accepted) and provisional
# (evaluator-passed, awaiting operator review) both satisfy. See
# docs/GDDP-rebuild.md "Provisional flow — two review modes".
SATISFIED_DEP_STATUSES = frozenset({"complete", "provisional"})


def check_scope(
    node: NodeData,
    project_id: str,
    con: sqlite3.Connection,
    graph_reader: GraphReader,
) -> ScopeCheckResult:
    """
    Returns ScopeCheckResult. safe=True means it is OK to dispatch.
    """

    # 1. Active job guard — reject if a job for this node is already in flight.
    #    awaiting_result (waiting on executor return) and awaiting_review (the
    #    human queue) both prevent a later heartbeat from dispatching again.
    cur = con.cursor()
    cols = {row[1] for row in cur.execute("PRAGMA table_info(jobs)")}
    if "project_id" in cols:
        cur.execute(
            "SELECT job_id FROM jobs WHERE project_id = ? AND node_id = ? AND status IN ('ready', 'running', 'awaiting_result', 'awaiting_review')",
            (project_id, node.node_id),
        )
    else:
        cur.execute(
            "SELECT job_id FROM jobs WHERE node_id = ? AND status IN ('ready', 'running', 'awaiting_result', 'awaiting_review')",
            (node.node_id,),
        )
    active = cur.fetchone()
    if active:
        job_id = active["job_id"] if hasattr(active, "keys") else active[0]
        return ScopeCheckResult(
            safe=False,
            reason=f"Active job already exists for {node.node_id}: {job_id}",
        )

    # 2. Dependency check — all depends_on must be satisfied in the graph.
    #    A rejected provisional returns to ready and re-blocks here.
    if node.depends_on:
        try:
            project = graph_reader.load_project(project_id)
        except FileNotFoundError as e:
            return ScopeCheckResult(safe=False, reason=str(e))

        node_status = {n["id"]: n.get("status", "pending") for n in project.nodes}
        for dep_id in node.depends_on:
            dep_status = node_status.get(dep_id, "unknown")
            if dep_status not in SATISFIED_DEP_STATUSES:
                return ScopeCheckResult(
                    safe=False,
                    reason=f"Dependency '{dep_id}' is not satisfied (status: {dep_status})",
                )

    return ScopeCheckResult(safe=True)
