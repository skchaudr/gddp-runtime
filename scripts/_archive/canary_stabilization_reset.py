"""
canary_stabilization_reset.py — Fresh-state reset for the Node 2
(direct-executor-round-trip) stabilization loop.

Deletes exactly the rows and artifacts one synthetic canary run created:
the injected event, the job it produced, and every executor_session/result
row tied to that job_id. Never touches other jobs for the same node_id —
canary-retry-proof carries real historical evidence (job_20260711T16542651,
job_20260711T17104259) from an earlier real attempt that this script must
never delete.

Usage:
    python3 scripts/canary_stabilization_reset.py <job_id> [--event-id <event_id>]

If --event-id is omitted, it is read from the job row before deletion.
"""

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

_default_root = Path(__file__).parent.parent
RUNTIME_ROOT = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH = RUNTIME_ROOT / "db" / "queue.db"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def reset(job_id: str, event_id: str | None = None) -> None:
    con = connect()
    try:
        job = con.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if job is None:
            print(f"No job row for {job_id} — nothing to reset in the DB.")
        else:
            resolved_event_id = event_id or job["event_id"]
            sessions = con.execute(
                "SELECT session_id FROM executor_sessions WHERE job_id = ?", (job_id,)
            ).fetchall()
            n_results = con.execute("DELETE FROM results WHERE job_id = ?", (job_id,)).rowcount
            n_sessions = con.execute(
                "DELETE FROM executor_sessions WHERE job_id = ?", (job_id,)
            ).rowcount
            n_queue = con.execute(
                "DELETE FROM queue_records WHERE job_id = ?", (job_id,)
            ).rowcount
            con.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            n_events = 0
            if resolved_event_id:
                n_events = con.execute(
                    "DELETE FROM events WHERE event_id = ?", (resolved_event_id,)
                ).rowcount
            con.commit()
            print(
                f"Deleted job {job_id}: {n_results} result row(s), "
                f"{n_sessions} session row(s), {n_queue} queue_record row(s), "
                f"1 job row, {n_events} event row(s)."
            )
            for s in sessions:
                _remove_git_ref(job_id, s["session_id"])
    finally:
        con.close()

    _prune_worktrees()


def _remove_git_ref(job_id: str, session_id: str) -> None:
    ref_name = f"gddp/result-{job_id}-{session_id}"
    proc = subprocess.run(
        ["git", "branch", "-D", ref_name],
        cwd=str(RUNTIME_ROOT),
        capture_output=True, text=True, check=False,
    )
    if proc.returncode == 0:
        print(f"Removed git ref {ref_name}")


def _prune_worktrees() -> None:
    subprocess.run(
        ["git", "worktree", "prune", "--expire", "now"],
        cwd=str(RUNTIME_ROOT),
        capture_output=True, check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    parser.add_argument("--event-id", default=None)
    args = parser.parse_args()
    reset(args.job_id, args.event_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
