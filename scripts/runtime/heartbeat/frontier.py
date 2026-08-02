"""
frontier.py — Automatic frontier advance for provisionally-unblocked nodes.

Doctrine: `complete` is human-only graph truth; `provisional` is the
scheduler-visible marker that work passed evaluation. scope_checker already
treats provisional dependencies as satisfied, but until now nothing moved a
dependent from `pending` to `ready` and nothing triggered its dispatch —
forward momentum required an operator to re-run the CLI between every graph
layer. This module closes that gap for projects that opt in via
`execution_policy.frontier_auto_advance: true` in project.yaml.

Per heartbeat tick, per project, one frontier hop:

  1. Every `pending` node whose dependencies are all satisfied
     (complete | provisional, computed live from the graph) and that is not
     `human_gate: true` transitions to `ready` — a scheduler-visible status,
     never a terminal one; rejection of a provisional dependency re-blocks
     the node at the scope gate on the next planning pass.
  2. Each transitioned node gets a dispatch event injected into the events
     ledger (source `frontier_auto`), which the ordinary
     classify → scope → capacity → reserve → dispatch pipeline then
     processes like any CLI-injected dispatch. The ledger keeps an audit
     trail of what the frontier triggered and why.

Duplicate guards: a node with an active job (dispatched through review) or
an already-pending frontier event is never re-triggered. The status
snapshot is taken at tick start, so a single tick advances exactly one
graph layer — evidence from one layer unlocks the next on the following
tick.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .graph_reader import GraphReader
from .provisional_gate import _atomic_write, _load_node_cli
from .scope_checker import SATISFIED_DEP_STATUSES

ACTIVE_JOB_STATUSES = ("ready", "running", "awaiting_result", "awaiting_review")
PENDING_EVENT_STATUSES = ("received", "claimed")


def advance_frontier(
    con: sqlite3.Connection,
    reader: GraphReader,
    project_id: str,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Transition newly-unblocked pending nodes to ready and inject dispatch
    events. Returns the transitioned node ids (empty when the project has
    not opted in or nothing is newly unblocked)."""
    project = reader.load_project(project_id)
    if not (project.execution_policy or {}).get("frontier_auto_advance"):
        return []

    now = now or datetime.now(timezone.utc)
    root = reader.config_path
    project_path = root / "graphs" / project_id / "project.yaml"
    status_by_id = {n["id"]: n.get("status") for n in project.nodes}
    node_cli = _load_node_cli(root)
    transitioned: list[str] = []

    for node_summary in project.nodes:
        node_id = node_summary["id"]
        if status_by_id.get(node_id) != "pending":
            continue

        node_path = root / "graphs" / project_id / "nodes" / f"{node_id}.yaml"
        try:
            doc = yaml.safe_load(node_path.read_text()) or {}
        except OSError:
            continue

        # Mode 2: operator-declared human-gated nodes never auto-advance.
        if doc.get("human_gate") is True:
            continue

        depends_on = doc.get("depends_on", []) or []
        satisfied = all(
            status_by_id.get(dep) in SATISFIED_DEP_STATUSES for dep in depends_on
        )
        if not satisfied:
            continue

        if _has_active_job(con, project_id, node_id):
            print(f"  → frontier: {node_id} unblocked but has an active job; skipping")
            continue
        if _has_pending_frontier_event(con, project_id, node_id):
            continue

        node_text, _ = node_cli.replace_node_status(node_path.read_text(), "ready")
        project_text, _ = node_cli.replace_project_index_status(
            project_path.read_text(), node_id, "ready"
        )
        _atomic_write(node_path, node_text)
        _atomic_write(project_path, project_text)
        _inject_dispatch_event(con, project, node_id, now)
        transitioned.append(node_id)
        print(
            f"  → frontier: {node_id} pending → ready "
            f"(deps satisfied), dispatch event injected"
        )

    if transitioned:
        con.commit()
        # The runner re-reads ready nodes for this tick's planning; the
        # cached project/node state predates the writes above.
        reader.invalidate(project_id)
    return transitioned


def _has_active_job(con: sqlite3.Connection, project_id: str, node_id: str) -> bool:
    placeholders = ",".join("?" for _ in ACTIVE_JOB_STATUSES)
    row = con.execute(
        f"SELECT 1 FROM jobs WHERE project_id = ? AND node_id = ? "
        f"AND status IN ({placeholders}) LIMIT 1",
        (project_id, node_id, *ACTIVE_JOB_STATUSES),
    ).fetchone()
    return row is not None


def _has_pending_frontier_event(
    con: sqlite3.Connection, project_id: str, node_id: str
) -> bool:
    placeholders = ",".join("?" for _ in PENDING_EVENT_STATUSES)
    row = con.execute(
        f"SELECT 1 FROM events WHERE project_id = ? AND source = 'frontier_auto' "
        f"AND status IN ({placeholders}) AND url = ? LIMIT 1",
        (
            project_id,
            *PENDING_EVENT_STATUSES,
            f"frontier-dispatch://node: {node_id}",
        ),
    ).fetchone()
    return row is not None


def _inject_dispatch_event(
    con: sqlite3.Connection, project, node_id: str, now: datetime
) -> str:
    """Insert one dispatch event in the same schema the gddp CLI uses, so the
    classify/scope/plan pipeline processes it identically to an
    operator-injected dispatch (classifier routes on the `node: <id>` url
    tag; routing stays NULL so the node's configured executor applies)."""
    event_id = (
        f"evt_frontier_{now.strftime('%Y%m%dT%H%M%S')}_"
        f"{node_id}_{secrets.token_hex(3)}"
    )
    con.execute(
        "INSERT INTO events (event_id, schema_version, received_at, source, "
        "event_type, actor, url, project_id, project_node_candidates, "
        "scope_status, priority, risk_level, routing, status, repo) "
        "VALUES (?, '1.0', ?, 'frontier_auto', 'issue.opened', ?, ?, ?, ?, "
        "'pending', 'pending', 'pending', ?, 'received', ?)",
        (
            event_id,
            now.isoformat(),
            "frontier",
            f"frontier-dispatch://node: {node_id}",
            project.project_id,
            json.dumps([node_id]),
            None,
            project.repo,
        ),
    )
    return event_id
