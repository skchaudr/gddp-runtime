"""
runner.py — Heartbeat vNext main loop.

Replaces scripts/heartbeat.py with a graph-driven, config-aware event processor.

Usage (from Big Pi):
    cd ~/opclaw/scripts
    python3 -m runtime.heartbeat.runner \
        --project vault-doctor \
        --repo skchaudr/vault-doctor \
        [--config-path /path/to/gddp-config]  # optional, uses GDDP_CONFIG_PATH env or sibling dir

What it does:
    1. Reads the project graph to find ready nodes (graph_reader)
    2. Fetches pending events from SQLite
    3. Plans dispatchable jobs sequentially on the main thread
    4. Dispatches planned jobs in parallel worker threads
    5. Records all state changes to SQLite on the main thread
"""

import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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

# GDDP_RUNTIME_ROOT points to the runtime state root; OPCLAW_ROOT remains a legacy fallback.
_default_root = Path(__file__).parent.parent.parent.parent
RUNTIME_ROOT = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH = RUNTIME_ROOT / "db" / "queue.db"


@dataclass(frozen=True)
class PlannedDispatch:
    event_id: str
    classification: dict
    job: dict


@dataclass(frozen=True)
class DispatchOutcome:
    planned: PlannedDispatch
    success: bool
    issue_url: str = ""
    error: str = ""


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
    try:
        planned_dispatches = _plan_dispatches(
            con, project_id, repo, ready_nodes, reader
        )

        if not planned_dispatches:
            print("Heartbeat complete.")
            return

        outcomes_by_job_id = _execute_dispatches(planned_dispatches, repo)
        _record_outcomes(con, planned_dispatches, outcomes_by_job_id)

        print("Heartbeat complete.")
    finally:
        con.close()


def _plan_dispatches(
    con: sqlite3.Connection,
    project_id: str,
    repo: str,
    ready_nodes: list,
    reader: GraphReader,
) -> list[PlannedDispatch]:
    """
    Phase A: Fetch events, classify, scope-check, and reserve jobs on the main thread.
    """
    cur = con.cursor()
    # Stale 'claimed' events (a heartbeat crashed mid-claim) become eligible
    # again after 30 minutes.
    stale_cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    ).isoformat()
    # Events arrive from intake with project_id=NULL; the repo→project binding
    # lives in project.yaml, mirrored by this runner's --project/--repo args.
    # Adopt unowned events from our repo alongside events already stamped ours.
    cur.execute(
        """
        SELECT * FROM events
         WHERE (project_id = ? OR (project_id IS NULL AND repo = ?))
           AND (status = 'received'
                OR (status = 'claimed' AND claimed_at < ?))
        """,
        (project_id, repo, stale_cutoff),
    )
    events = cur.fetchall()

    if not events:
        print("No pending events.")
        return []

    print(f"Found {len(events)} pending event(s).\n")

    planned_dispatches: list[PlannedDispatch] = []

    for event in events:
        event_id = event["event_id"]

        # Atomic claim: only one heartbeat process may win this event. A
        # concurrent runner that read the same 'received' row loses the
        # UPDATE race and skips.
        claim = con.execute(
            """
            UPDATE events
               SET status = 'claimed', claimed_at = ?, project_id = ?
             WHERE event_id = ?
               AND (status = 'received'
                    OR (status = 'claimed' AND claimed_at < ?))
            """,
            (datetime.now(timezone.utc).isoformat(), project_id, event_id, stale_cutoff),
        )
        con.commit()
        if claim.rowcount != 1:
            print(f"Skipping: {event_id} (claimed by another heartbeat)")
            continue

        print(f"Processing: {event_id} ({event['event_type']})")

        # Classify and reserve jobs on the main thread.
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

        # Scope checks continue to use the single main-thread SQLite connection.
        scope = check_scope(node, project_id, con, reader)
        if not scope:
            mark_event_scope_blocked(con, event_id, scope.reason)
            print(f"  → scope blocked: {scope.reason}\n")
            continue

        # Reserve the job before dispatch so other heartbeats see it immediately.
        job = build_job(
            node,
            event,
            project_id,
            repo,
            RUNTIME_ROOT,
            classification["executor_recommendation"],
        )
        job_id = job["job_id"]

        insert_job(con, job)
        insert_queue_record(con, job_id)
        planned_dispatches.append(
            PlannedDispatch(
                event_id=event_id,
                classification=classification,
                job=job,
            )
        )
        print(f"  → job created: {job_id}")
        print()

    # Phase A commit: make reservation rows durable before worker dispatch starts.
    con.commit()
    return planned_dispatches


def _execute_dispatches(
    planned_dispatches: list[PlannedDispatch],
    repo: str,
) -> dict[str, DispatchOutcome]:
    """
    Phase B: Worker threads execute dispatch(job, repo) in parallel.
    """
    print(f"Dispatching {len(planned_dispatches)} job(s) in parallel.\n")

    outcomes_by_job_id: dict[str, DispatchOutcome] = {}
    max_workers = min(32, max(1, len(planned_dispatches)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_plan = {
            executor.submit(dispatch, planned.job, repo): planned
            for planned in planned_dispatches
        }
        for future in as_completed(future_to_plan):
            planned = future_to_plan[future]
            try:
                result = future.result()
                outcomes_by_job_id[planned.job["job_id"]] = DispatchOutcome(
                    planned=planned,
                    success=result.success,
                    issue_url=result.issue_url,
                    error=result.error,
                )
            except Exception as exc:
                outcomes_by_job_id[planned.job["job_id"]] = DispatchOutcome(
                    planned=planned,
                    success=False,
                    error=f"Dispatch raised exception: {exc}",
                )
    return outcomes_by_job_id


def _record_outcomes(
    con: sqlite3.Connection,
    planned_dispatches: list[PlannedDispatch],
    outcomes_by_job_id: dict[str, DispatchOutcome],
) -> None:
    """
    Phase C: Record results sequentially on the main thread.
    """
    for planned in planned_dispatches:
        outcome = outcomes_by_job_id[planned.job["job_id"]]
        event_id = planned.event_id
        job_id = planned.job["job_id"]

        print(f"Recording: {event_id} ({planned.job['node_id']})")
        if outcome.success:
            mark_event_mapped(con, event_id)
            mark_job_running(con, job_id)
            print(f"  → dispatched to {planned.classification['executor_recommendation']}")
            if outcome.issue_url:
                print(f"  → issue: {outcome.issue_url}")
        else:
            mark_job_failed(con, job_id)
            print(f"  → DISPATCH FAILED: {outcome.error}")
        print()

    con.commit()


def main():
    parser = argparse.ArgumentParser(description="GDDP Heartbeat vNext")
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
