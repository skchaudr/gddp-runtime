"""
replay.py — Replay failed or partial runtime steps from persisted state.

Usage:
    python3 -m runtime.replay --result-id res_20260312T21053737
    python3 -m runtime.replay --job-id job_20260312T21053737

What is replayed:
    - For --result-id: Re-runs the return router logic (handle_merged_pr) for the event
      associated with the result. This recreates the review receipt/state routing.
    - For --job-id: Re-dispatches the specific job to its assigned executor (e.g., Jules).

What is NOT replayed:
    - Initial webhook intake (events are read from the DB, not re-received).
    - Classification and scoping (uses the persisted job/event context).

Safeguards:
    - Re-dispatching a job (--job-id) requires explicit operator confirmation to
      prevent accidental or silent re-dispatches.
    - Operates on persisted DB state, ensuring no "DB surgery" is needed.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# Add the root directory to sys.path to allow importing from scripts package
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

try:
    from scripts.runtime import return_router
    from scripts.runtime.heartbeat import dispatcher, state_recorder
except ImportError:
    # Fallback for different execution contexts
    from runtime import return_router
    from runtime.heartbeat import dispatcher, state_recorder

# GDDP_RUNTIME_ROOT points to the runtime state root; OPCLAW_ROOT remains a legacy fallback.
_default_root = Path(__file__).parent.parent.parent
RUNTIME_ROOT = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH = RUNTIME_ROOT / "db" / "queue.db"

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def replay_result(result_id: str):
    print(f"Replaying result: {result_id}")

    # Deriving event_id: res_... -> evt_...
    if not result_id.startswith("res_"):
        print(f"Error: Invalid result_id format. Must start with 'res_'.")
        return

    event_id = "evt_" + result_id[4:]
    print(f"Derived event_id: {event_id}")

    con = connect()
    try:
        event = con.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if not event:
            print(f"Error: Event {event_id} not found in database.")
            return

        print(f"Found event: {event['event_type']} for project {event['project_id']}")
        print("Re-running return router...")

        outcome = return_router.handle_merged_pr(event)
        print(f"Replay outcome: {outcome}")
    finally:
        con.close()

def replay_job(job_id: str):
    print(f"Replaying job: {job_id}")

    con = connect()
    try:
        job_row = con.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not job_row:
            print(f"Error: Job {job_id} not found in database.")
            return

        job = dict(job_row)
        print(f"\nJob Details:")
        print(f"  ID       : {job['job_id']}")
        print(f"  Node     : {job['node_id']}")
        print(f"  Project  : {job['project_id']}")
        print(f"  Executor : {job['executor']}")
        print(f"  Goal     : {job['goal']}")
        print(f"  Status   : {job['status']}")

        confirm = input("\nRe-dispatch this job? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

        print(f"Re-dispatching to {job['executor']}...")

        # Dispatch
        result = dispatcher.dispatch(job, job['repo'])

        if result.success:
            state_recorder.mark_event_mapped(con, job['event_id'])
            state_recorder.mark_job_running(con, job['job_id'])
            con.commit()
            print(f"Successfully re-dispatched.")
            if result.issue_url:
                print(f"Issue URL: {result.issue_url}")
        else:
            state_recorder.mark_job_failed(con, job['job_id'])
            con.commit()
            print(f"Re-dispatch failed: {result.error}")

    finally:
        con.close()

def main():
    parser = argparse.ArgumentParser(description="GDAD Replay Mechanics")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--result-id", help="Replay a return router result (receipt/state routing)")
    group.add_argument("--job-id", help="Re-dispatch a failed or partial job")

    args = parser.parse_args()

    if args.result_id:
        replay_result(args.result_id)
    elif args.job_id:
        replay_job(args.job_id)

if __name__ == "__main__":
    main()
