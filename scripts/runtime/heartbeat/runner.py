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
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .classifier import classify
from .dispatcher import dispatch
from .graph_reader import GraphReader
from .job_factory import build_job
from .reconciler import reconcile_sessions
from .scope_checker import check_scope
from .state_recorder import (
    finalize_executor_session_dispatch,
    insert_executor_session,
    insert_job,
    insert_queue_record,
    mark_event_classified,
    mark_event_ignored,
    mark_event_mapped,
    mark_event_scope_blocked,
    mark_job_failed,
    mark_job_running,
)

from ..return_router import handle_merged_pr

# GDDP_RUNTIME_ROOT points to the runtime state root; OPCLAW_ROOT remains a legacy fallback.
_default_root = Path(__file__).parent.parent.parent.parent
RUNTIME_ROOT = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH = RUNTIME_ROOT / "db" / "queue.db"


@dataclass(frozen=True)
class PlannedDispatch:
    event_id: str
    classification: dict
    job: dict

    session_db_id: str

@dataclass(frozen=True)
class DispatchOutcome:
    planned: PlannedDispatch
    success: bool
    issue_url: str = ""
    error: str = ""
    session_ref: object = None  # adapters.executor_protocol.SessionRef | None


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    # Concurrency: WAL lets readers overlap the single writer; busy_timeout
    # makes a colliding writer wait instead of raising 'database is locked'.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _is_merged_pr_event(event) -> bool:
    """Check if an event is a merged PR (not just closed)."""
    event_type = event["event_type"] if "event_type" in event.keys() else ""
    if "pull_request" not in event_type:
        return False
    # Read the raw payload to check merged_at
    raw_path = event["raw_payload_path"] if "raw_payload_path" in event.keys() else None
    if not raw_path:
        return False
    try:
        payload = json.loads(Path(raw_path).read_text())
        pr = payload.get("pull_request", {})
        return pr.get("merged_at") is not None
    except (OSError, ValueError):
        return False


def run_heartbeat(
    project_id: str,
    repo: str,
    config_path: str = None,
    repo_path: str = None,
) -> None:
    reader = GraphReader(config_path=config_path)

    # Derive the local checkout path if the caller did not provide one.
    # The reconcile phase needs a filesystem path (not the GitHub owner/name).
    if repo_path is None:
        repos_root = os.environ.get("GDDP_REPOS_ROOT")
        if repos_root:
            derived = Path(repos_root) / repo.split("/")[-1]
            if derived.exists():
                repo_path = str(derived)

    # Load ready nodes from the graph (replaces hardcoded PHASE3_NODE)
    ready_nodes = reader.get_ready_nodes(project_id)
    if ready_nodes:
        print(f"Ready nodes: {[n.node_id for n in ready_nodes]}")
    else:
        print("No ready nodes in graph.")

    con = connect()
    try:
        # Phase 0: Reconcile active executor sessions (runs every tick).
        # CLI-based executors complete asynchronously without webhooks, so
        # every tick must poll for completion even when there are no new
        # intake events.
        reconcile_sessions(con, Path(repo_path) if repo_path else None, repo=repo)

        # Phase A-C: Plan and dispatch new events.
        planned_dispatches = _plan_dispatches(
            con, project_id, repo, ready_nodes, reader
        )

        if not planned_dispatches:
            print("Heartbeat complete.")
            return

        outcomes_by_job_id = _execute_dispatches(planned_dispatches, repo)
        _record_outcomes(con, planned_dispatches, outcomes_by_job_id, repo_path)

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

        # Return path: merged PR events go to the return router, not the classifier.
        if _is_merged_pr_event(event):
            print(f"  → return path: processing merged PR")
            try:
                result = handle_merged_pr(event)
                print(f"  → return router: {result.get('status', 'unknown')}")
                if result.get("status") == "redispatched":
                    print(f"  → retry dispatched: {result.get('issue_url', '')}")
                mark_event_mapped(con, event_id)
            except Exception as exc:
                print(f"  → return router ERROR: {exc}")
                mark_event_ignored(con, event_id)
            print()
            continue

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
        attempt_index = int(job.get("attempt", 0))
        attempt_id = f"{job_id}:attempt:{attempt_index}"
        session_db_id = insert_executor_session(
            con,
            job_id,
            job["executor"],
            attempt_id,
            attempt_index=attempt_index,
            state="dispatching",
        )
        planned_dispatches.append(
            PlannedDispatch(
                event_id=event_id,
                classification=classification,
                job=job,
                session_db_id=session_db_id,
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
                    session_ref=getattr(result, "session_ref", None),
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
    repo_path: str | None = None,
) -> None:
    """
    Phase C: Record results sequentially on the main thread.
    """
    # Capture the current HEAD as the expected base commit for CLI-dispatched
    # sessions. This pins the worktree the reconcile phase will create.
    head_sha = _get_head_sha(repo_path)

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
            # Finalize the attempt row allocated before adapter dispatch.
            if outcome.session_ref is not None:
                finalize_executor_session_dispatch(
                    con,
                    planned.session_db_id,
                    state="dispatched",
                    executor=outcome.session_ref.executor,
                    session_id=outcome.session_ref.session_id,
                    expected_base_commit_sha=head_sha,
                )
                print(
                    f"  → executor session: "
                    f"{outcome.session_ref.executor}/{outcome.session_ref.session_id}"
                )
            else:
                finalize_executor_session_dispatch(
                    con,
                    planned.session_db_id,
                    state="mediated",
                    session_id=outcome.issue_url or None,
                    expected_base_commit_sha=head_sha,
                )
        else:
            mark_job_failed(con, job_id)
            print(f"  → DISPATCH FAILED: {outcome.error}")
            finalize_executor_session_dispatch(
                con,
                planned.session_db_id,
                state="dispatch_failed",
                error=outcome.error or "dispatch failed",
                expected_base_commit_sha=head_sha,
            )
        print()

    con.commit()


def _get_head_sha(repo_path: str | None) -> str | None:
    """Get the current HEAD commit SHA of the local repo, or None."""
    if not repo_path:
        return None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="GDDP Heartbeat vNext")
    parser.add_argument("--project",     required=True, help="Project ID (e.g. vault-doctor)")
    parser.add_argument("--repo",        required=True, help="GitHub repo (owner/name)")
    parser.add_argument("--config-path", default=None,  help="Path to gddp-config checkout")
    parser.add_argument("--repo-path",   default=None,  help="Local filesystem path to the repo checkout (enables reconcile)")
    args = parser.parse_args()

    run_heartbeat(
        project_id=args.project,
        repo=args.repo,
        config_path=args.config_path,
        repo_path=args.repo_path,
    )


if __name__ == "__main__":
    main()
