"""
rollback.py — Revert a job and restore node state.

Usage:
    python3 scripts/rollback.py --job job_20260312T21053737

What it does:
    1. Shows current state of the job
    2. Confirms with you before making any changes
    3. Reverts job to 'failed', queue record to 'cancelled'
    4. Prints what would need to happen on the graph side (node stays as-is)
    5. Logs the rollback to the job's decision.md
"""

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_default_root = Path(__file__).parent.parent
RUNTIME_ROOT  = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH       = RUNTIME_ROOT / "db" / "queue.db"


def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def rollback(job_id: str):
    con = connect()

    job = con.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not job:
        print(f"ERROR: job {job_id} not found")
        con.close()
        return

    queue = con.execute(
        "SELECT * FROM queue_records WHERE job_id = ?", (job_id,)
    ).fetchone()

    print(f"\nCurrent state:")
    print(f"  job_id      : {job['job_id']}")
    print(f"  node_id     : {job['node_id']}")
    print(f"  status      : {job['status']}")
    print(f"  queue_state : {job['queue_state']}")
    if queue:
        print(f"  queue       : {queue['queue']}")

    print()
    confirm = input("Roll back this job? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        con.close()
        return

    # Revert job and queue record
    con.execute(
        "UPDATE jobs SET status='failed', queue_state='failed' WHERE job_id=?",
        (job_id,)
    )
    if queue:
        con.execute(
            "UPDATE queue_records SET queue='cancelled' WHERE job_id=?", (job_id,)
        )

    # Append rollback note to decision.md if it exists
    decision_path = RUNTIME_ROOT / "jobs" / job_id / "decision.md"
    if decision_path.exists():
        with open(decision_path, "a") as f:
            f.write(f"\n\n---\n## Rollback\nRolled back at {now()}\nJob status set to: failed\nQueue set to: cancelled\n")

    con.commit()
    con.close()

    print()
    print(f"  job status  → failed")
    print(f"  queue       → cancelled")
    print()
    print(f"  Node '{job['node_id']}' state: unchanged")
    print(f"  Graph truth is human-owned; review any related receipts before changing the graph.")
    print(f"  Re-run the heartbeat to dispatch a fresh job against the same node.")
    print()
    print("Rollback complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, help="job_id to roll back")
    args = parser.parse_args()
    rollback(args.job)
