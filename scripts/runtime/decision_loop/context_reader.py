"""
context_reader.py - builds the context payload the runtime decision loop needs.

Reads three sources:
1. gddp-config graph YAML (via GraphReader)
2. SQLite recent rows (events, jobs, results)
3. The current trigger event
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional

from ..heartbeat.graph_reader import GraphReader, NodeData


@dataclass
class ProjectState:
    project_id: str
    repo: str
    nodes: list[NodeData]
    pending_nodes: list[NodeData]
    ready_nodes: list[NodeData]
    complete_nodes: list[NodeData]
    deferred_nodes: list[NodeData]


@dataclass
class RecentActivity:
    active_jobs: list[dict]       # jobs with status=running or dispatched
    recent_results: list[dict]    # last 20 results
    stale_jobs: list[dict]        # jobs running > 6 hours
    stale_events: list[dict]      # events received > 6 hours


@dataclass
class DecisionContext:
    project: ProjectState
    activity: RecentActivity
    trigger: dict                  # the event that woke the decision loop


def read_project_state(reader: GraphReader, project_id: str) -> ProjectState:
    """Load project graph and categorize nodes by status."""
    project = reader.load_project(project_id)

    all_nodes = []
    for node_summary in project.nodes:
        try:
            node = reader.load_node(project_id, node_summary["id"])
            all_nodes.append(node)
        except FileNotFoundError:
            pass

    # Buckets mirror the node schema's human-owned status vocabulary:
    # pending | ready | complete | deferred. Execution states live on
    # jobs/queue_records, never on nodes.
    pending = [n for n in all_nodes if n.status == "pending"]
    ready = [n for n in all_nodes if n.status == "ready"]
    complete = [n for n in all_nodes if n.status == "complete"]
    deferred = [n for n in all_nodes if n.status == "deferred"]

    return ProjectState(
        project_id=project_id,
        repo=project.repo,
        nodes=all_nodes,
        pending_nodes=pending,
        ready_nodes=ready,
        complete_nodes=complete,
        deferred_nodes=deferred,
    )


def read_recent_activity(con: sqlite3.Connection, project_id: str) -> RecentActivity:
    """Pull recent rows from SQLite to understand momentum and detect stale state."""
    cur = con.cursor()

    # Active jobs (dispatched or running) — scoped to this project so one
    # project's work does not block dispatch on another.
    cur.execute(
        "SELECT * FROM jobs WHERE project_id = ? AND status IN ('dispatched', 'running') ORDER BY created_at DESC",
        (project_id,),
    )
    active_jobs = [dict(row) for row in cur.fetchall()]

    # Recent results (last 20) — results carry no project_id, so scope via
    # their parent job.
    cur.execute(
        """
        SELECT r.* FROM results r
        JOIN jobs j ON r.job_id = j.job_id
        WHERE j.project_id = ?
        ORDER BY r.received_at DESC LIMIT 20
        """,
        (project_id,),
    )
    recent_results = [dict(row) for row in cur.fetchall()]

    # Stale jobs: running for more than 6 hours
    cur.execute("""
        SELECT * FROM jobs
        WHERE project_id = ?
        AND status IN ('dispatched', 'running')
        AND created_at < datetime('now', '-6 hours')
    """, (project_id,))
    stale_jobs = [dict(row) for row in cur.fetchall()]

    # Stale events: received but unprocessed for more than 6 hours
    cur.execute("""
        SELECT * FROM events
        WHERE project_id = ?
        AND status = 'received'
        AND received_at < datetime('now', '-6 hours')
    """, (project_id,))
    stale_events = [dict(row) for row in cur.fetchall()]

    return RecentActivity(
        active_jobs=active_jobs,
        recent_results=recent_results,
        stale_jobs=stale_jobs,
        stale_events=stale_events,
    )


def read_context(
    reader: GraphReader,
    con: sqlite3.Connection,
    project_id: str,
    trigger: dict,
) -> DecisionContext:
    """Build the full context payload for one decision cycle."""
    project = read_project_state(reader, project_id)
    activity = read_recent_activity(con, project_id)

    return DecisionContext(
        project=project,
        activity=activity,
        trigger=trigger,
    )
