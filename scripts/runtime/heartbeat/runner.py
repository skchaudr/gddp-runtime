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
from .dispatcher import cancel_remote_session, dispatch, executor_preflight_error
from .graph_reader import GraphReader
from .job_factory import build_job
from .reconciler import (
    DEFAULT_MAX_CONCURRENT_EVALUATIONS,
    EvaluationBatch,
    reconcile_sessions,
)
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


def _configured_job_capacity(execution_policy: dict) -> int | None:
    """Return the configured positive job cap, or no cap when omitted."""
    value = execution_policy.get("max_concurrent_jobs")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("execution_policy.max_concurrent_jobs must be a positive integer")
    return value


def _active_job_count(con: sqlite3.Connection, repo: str) -> int:
    """Count reserved or running jobs that consume executor capacity."""
    row = con.execute(
        """SELECT COUNT(*)
             FROM jobs
            WHERE repo = ?
              AND (
                  status IN ('ready', 'running')
                  OR queue_state IN ('ready', 'running')
              )""",
        (repo,),
    ).fetchone()
    return int(row[0])


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

    project = reader.load_project(project_id)
    max_concurrent_jobs = _configured_job_capacity(project.execution_policy)
    evaluation_capacity = (
        max_concurrent_jobs
        if max_concurrent_jobs is not None
        else DEFAULT_MAX_CONCURRENT_EVALUATIONS
    )

    # Load ready nodes from the graph (replaces hardcoded PHASE3_NODE)
    ready_nodes = reader.get_ready_nodes(project_id)
    if ready_nodes:
        print(f"Ready nodes: {[n.node_id for n in ready_nodes]}")
    else:
        print("No ready nodes in graph.")

    con = connect()
    try:
        evaluation_batch = EvaluationBatch(max_workers=evaluation_capacity)
        try:
            # Phase 0: Poll/collect every active session, then start all
            # evaluation-ready verifier subprocesses without waiting. This
            # lets planning and dispatch continue while evaluators run.
            reconcile_sessions(
                con,
                Path(repo_path) if repo_path else None,
                repo=repo,
                evaluation_batch=evaluation_batch,
            )

            # Phase A-C: Plan and dispatch new events.
            planned_dispatches = _plan_dispatches(
                con,
                project_id,
                repo,
                ready_nodes,
                reader,
                max_concurrent_jobs=max_concurrent_jobs,
                repo_path=repo_path,
            )

            if not planned_dispatches:
                print("Heartbeat complete.")
                return

            outcomes_by_job_id = _execute_dispatches(
                planned_dispatches, repo, repo_path
            )
            _record_outcomes(con, planned_dispatches, outcomes_by_job_id, repo_path)

            print("Heartbeat complete.")
        finally:
            # Worker threads never receive ``con``. The coordinator serializes
            # all result/session/job writes before closing the heartbeat DB.
            evaluation_batch.finalize(con)
    finally:
        con.close()


def _active_projects(reader: GraphReader) -> list:
    """Find graph projects with pending intake or unfinished runtime work."""
    con = connect()
    try:
        project_ids = {
            row[0]
            for row in con.execute(
                """
                SELECT DISTINCT project_id
                  FROM events
                 WHERE project_id IS NOT NULL
                   AND status IN ('received', 'claimed')
                UNION
                SELECT DISTINCT project_id
                  FROM jobs
                 WHERE project_id IS NOT NULL
                   AND (
                       status IN ('ready', 'running', 'awaiting_result')
                       OR queue_state IN ('ready', 'running', 'awaiting_result')
                   )
                """
            )
        }
        repos = {
            row[0]
            for row in con.execute(
                """
                SELECT DISTINCT repo
                  FROM events
                 WHERE project_id IS NULL
                   AND repo IS NOT NULL
                   AND status IN ('received', 'claimed')
                """
            )
        }
    finally:
        con.close()
    return [
        project
        for project in reader.list_projects()
        if project.project_id in project_ids or project.repo in repos
    ]


def run_active_projects(config_path: str | None = None) -> None:
    """Run one heartbeat tick for every project with actionable runtime state."""
    reader = GraphReader(config_path=config_path)
    projects = _active_projects(reader)
    if not projects:
        print("No active projects.")
        return
    print(f"Active projects: {[project.project_id for project in projects]}")
    for project in projects:
        run_heartbeat(
            project_id=project.project_id,
            repo=project.repo,
            config_path=config_path,
        )


def _plan_dispatches(
    con: sqlite3.Connection,
    project_id: str,
    repo: str,
    ready_nodes: list,
    reader: GraphReader,
    *,
    expected_base_commit_sha: str | None = None,
    max_concurrent_jobs: int | None = None,
    repo_path: str | None = None,
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
         ORDER BY received_at, event_id
        """,
        (project_id, repo, stale_cutoff),
    )
    events = cur.fetchall()

    if not events:
        print("No pending events.")
        return []

    print(f"Found {len(events)} pending event(s).\n")

    planned_dispatches: list[PlannedDispatch] = []
    base_commit_resolved = expected_base_commit_sha is not None

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
            con.commit()
            print()
            continue

        # Classify and reserve jobs on the main thread.
        classification = classify(event, ready_nodes)
        if classification is None:
            mark_event_ignored(con, event_id)
            con.commit()
            print(f"  → ignored (no node mapping)\n")
            continue

        node_id = classification["matched_node_id"]
        node = next((n for n in ready_nodes if n.node_id == node_id), None)
        if node is None:
            mark_event_ignored(con, event_id)
            con.commit()
            print(f"  → ignored (matched node {node_id} not in ready list)\n")
            continue

        preflight_error = executor_preflight_error(
            classification["executor_recommendation"], repo, repo_path
        )
        if preflight_error:
            con.execute(
                """UPDATE events
                      SET status = 'received', claimed_at = NULL
                    WHERE event_id = ? AND status = 'claimed'""",
                (event_id,),
            )
            con.commit()
            print(f"  → deferred (executor preflight: {preflight_error})\n")
            continue

        if not base_commit_resolved:
            expected_base_commit_sha = _get_head_sha(repo_path)
            base_commit_resolved = True

        # Serialize the capacity check with reservation writes. This prevents
        # overlapping heartbeat processes from each observing the same free slot.
        con.execute("BEGIN IMMEDIATE")
        active_jobs = _active_job_count(con, repo)
        if (
            max_concurrent_jobs is not None
            and active_jobs >= max_concurrent_jobs
        ):
            con.execute(
                """UPDATE events
                      SET status = 'received', claimed_at = NULL
                    WHERE event_id = ? AND status = 'claimed'""",
                (event_id,),
            )
            con.commit()
            print(
                f"  → deferred (executor capacity "
                f"{active_jobs}/{max_concurrent_jobs})\n"
            )
            break

        mark_event_classified(con, event_id, classification)

        # Re-check scope while holding the reservation lock so two heartbeat
        # processes cannot reserve the same node concurrently.
        scope = check_scope(node, project_id, con, reader)
        if not scope:
            mark_event_scope_blocked(con, event_id, scope.reason)
            con.commit()
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
        job["expected_base_commit_sha"] = expected_base_commit_sha
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
            expected_base_commit_sha=expected_base_commit_sha,
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
        con.commit()
        print(f"  → job created: {job_id}")
        print()

    # Phase A commit: make reservation rows durable before worker dispatch starts.
    con.commit()
    return planned_dispatches


def _execute_dispatches(
    planned_dispatches: list[PlannedDispatch],
    repo: str,
    repo_path: str | None = None,
) -> dict[str, DispatchOutcome]:
    """
    Phase B: Worker threads execute dispatch in the target checkout.
    """
    print(f"Dispatching {len(planned_dispatches)} job(s) in parallel.\n")

    outcomes_by_job_id: dict[str, DispatchOutcome] = {}
    max_workers = min(32, max(1, len(planned_dispatches)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_plan = {
            executor.submit(dispatch, planned.job, repo, repo_path): planned
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
    for planned in planned_dispatches:
        outcome = outcomes_by_job_id[planned.job["job_id"]]
        event_id = planned.event_id
        job_id = planned.job["job_id"]
        expected_base_commit_sha = (
            planned.job.get("expected_base_commit_sha")
            or _get_head_sha(repo_path)
        )

        print(f"Recording: {event_id} ({planned.job['node_id']})")
        if outcome.success:
            # Finalize the reservation before advancing job/queue state.
            if outcome.session_ref is not None:
                finalized = finalize_executor_session_dispatch(
                    con,
                    planned.session_db_id,
                    state="dispatched",
                    executor=outcome.session_ref.executor,
                    session_id=outcome.session_ref.session_id,
                    expected_base_commit_sha=expected_base_commit_sha,
                )
            else:
                finalized = finalize_executor_session_dispatch(
                    con,
                    planned.session_db_id,
                    state="mediated",
                    session_id=outcome.issue_url or None,
                    expected_base_commit_sha=expected_base_commit_sha,
                )
            if not finalized:
                cancellation = "reservation is no longer dispatching"
                if outcome.session_ref is not None:
                    _, cancellation = cancel_remote_session(
                        outcome.session_ref,
                        str(planned.job.get("repo") or ""),
                    )
                mark_event_mapped(con, event_id)
                print(f"  → late dispatch result ignored: {cancellation}")
                print()
                continue

            mark_event_mapped(con, event_id)
            mark_job_running(con, job_id)
            print(
                f"  → dispatched to "
                f"{planned.classification['executor_recommendation']}"
            )
            if outcome.issue_url:
                print(f"  → issue: {outcome.issue_url}")
            if outcome.session_ref is not None:
                print(
                    f"  → executor session: "
                    f"{outcome.session_ref.executor}/"
                    f"{outcome.session_ref.session_id}"
                )
        else:
            finalized = finalize_executor_session_dispatch(
                con,
                planned.session_db_id,
                state="dispatch_failed",
                error=outcome.error or "dispatch failed",
                expected_base_commit_sha=expected_base_commit_sha,
            )
            if not finalized:
                mark_event_mapped(con, event_id)
                print(
                    "  → late dispatch failure ignored: reservation is no "
                    "longer dispatching"
                )
                print()
                continue
            mark_event_mapped(con, event_id)
            mark_job_failed(con, job_id)
            print(f"  → DISPATCH FAILED: {outcome.error}")
            print(
                "  → retry after repair: dispatch this node again through gddp"
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
    parser.add_argument("--project", help="Project ID (e.g. vault-doctor)")
    parser.add_argument("--repo", help="GitHub repo (owner/name)")
    parser.add_argument(
        "--all-active",
        action="store_true",
        help="tick every project with pending events or active jobs",
    )
    parser.add_argument("--config-path", default=None,  help="Path to gddp-config checkout")
    parser.add_argument("--repo-path",   default=None,  help="Local filesystem path to the repo checkout (enables reconcile)")
    args = parser.parse_args()

    if args.all_active:
        if args.project or args.repo or args.repo_path:
            parser.error("--all-active cannot be combined with project arguments")
        run_active_projects(config_path=args.config_path)
        return
    if not args.project or not args.repo:
        parser.error("--project and --repo are required without --all-active")
    run_heartbeat(
        project_id=args.project,
        repo=args.repo,
        config_path=args.config_path,
        repo_path=args.repo_path,
    )


if __name__ == "__main__":
    main()
