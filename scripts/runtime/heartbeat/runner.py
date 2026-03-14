"""
runner.py — Heartbeat vNext main loop.

Replaces scripts/heartbeat.py with a graph-driven, config-aware event processor.

Usage:
    python3 scripts/runtime/heartbeat/runner.py \\
        --project vault-doctor \\
        --repo skchaudr/vault-doctor \\
        [--config-path /path/to/gddp-config]  # optional, uses GDDP_CONFIG_PATH env or sibling dir

What it does:
    1. Reads the project graph to find ready nodes (graph_reader)
    2. Fetches pending events from SQLite
    3. Classifies each event against ready nodes (classifier)
    4. Checks scope — active job guard + dependency check (scope_checker)
    5. Builds a job payload (job_factory)
    6. Dispatches to the correct executor (dispatcher)
    7. Records all state changes to SQLite (state_recorder)
"""

import argparse
import os
import sqlite3
from pathlib import Path

from .classifier import classify
from .dispatcher import dispatch
from .graph_reader import GraphReader
from .job_factory import build_job
from .scope_checker import check_scope
from .state_recorder import (
    insert_job,
    insert_queue_record,
    mark_event_classified,
    mark_event_ignored,
    mark_event_mapped,
    mark_event_scope_blocked,
    mark_job_failed,
    mark_job_running,
)

# OPCLAW_ROOT: set OPCLAW_ROOT env var on Pi to point to ~/opclaw
# Falls back to the repo root for local dev (Mac)
_default_root = Path(__file__).parent.parent.parent.parent
OPCLAW_ROOT = Path(os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH = OPCLAW_ROOT / "db" / "queue.db"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def run_heartbeat(project_id: str, repo: str, config_path: str = None) -> None:
    reader = GraphReader(config_path=config_path)

    # Load ready nodes from the graph (replaces hardcoded PHASE3_NODE)
    ready_nodes = reader.get_ready_nodes(project_id)
    if ready_nodes:
        print(f"Ready nodes: {[n.node_id for n in ready_nodes]}")
    else:
        print("No ready nodes in graph.")

    con = connect()
    cur = con.cursor()

    cur.execute("SELECT * FROM events WHERE status = 'received'")
    events = cur.fetchall()

    if not events:
        print("No pending events.")
        con.close()
        return

    print(f"Found {len(events)} pending event(s).\n")

    for event in events:
        event_id = event["event_id"]
        print(f"Processing: {event_id} ({event['event_type']})")

        # 1. Classify
        classification = classify(event, ready_nodes)
        if classification is None:
            mark_event_ignored(con, event_id)
            print(f"  → ignored (no node mapping)\n")
            continue

        node_id = classification["matched_node_id"]
        node = next((n for n in ready_nodes if n.node_id == node_id), None)
        if node is None:
            mark_event_ignored(con, event_id)
            print(f"  → ignored (matched node {node_id} not in ready list)\n")
            continue

        mark_event_classified(con, event_id, classification)

        # 2. Scope check — active job guard + dependency check
        scope = check_scope(node, project_id, con, reader)
        if not scope:
            mark_event_scope_blocked(con, event_id, scope.reason)
            print(f"  → scope blocked: {scope.reason}\n")
            continue

        # 3. Build job
        job = build_job(node, event, project_id, repo, OPCLAW_ROOT)
        job_id = job["job_id"]

        insert_job(con, job)
        insert_queue_record(con, job_id)
        print(f"  → job created: {job_id}")

        # 4. Dispatch
        result = dispatch(job, repo)

        if result.success:
            mark_event_mapped(con, event_id)
            mark_job_running(con, job_id)
            print(f"  → dispatched to {classification['executor_recommendation']}")
            if result.issue_url:
                print(f"  → issue: {result.issue_url}")
        else:
            mark_job_failed(con, job_id)
            print(f"  → DISPATCH FAILED: {result.error}")

        print()

    con.commit()
    con.close()
    print("Heartbeat complete.")


def main():
    parser = argparse.ArgumentParser(description="GDAD Heartbeat vNext")
    parser.add_argument("--project",     required=True, help="Project ID (e.g. vault-doctor)")
    parser.add_argument("--repo",        required=True, help="GitHub repo (owner/name)")
    parser.add_argument("--config-path", default=None,  help="Path to gddp-config checkout")
    args = parser.parse_args()

    run_heartbeat(
        project_id=args.project,
        repo=args.repo,
        config_path=args.config_path,
    )


if __name__ == "__main__":
    main()
