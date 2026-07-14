"""
node_status.py — Inspect and set job/node queue state (human-operated).

Usage:
    python3 scripts/node_status.py list [--state awaiting_review]
    python3 scripts/node_status.py show <job_id | node_id> [--full]
    python3 scripts/node_status.py results
    python3 scripts/node_status.py set <job_id | node_id> <state> --reason "..."

States (canon: gddp-config schemas/v1/queue_record.yaml):
    intake classified blocked ready running awaiting_result
    awaiting_review complete failed deferred cancelled

What `set` does:
    1. Shows current state and asks for confirmation
    2. Updates jobs.queue_state (+ jobs.status when the state is a valid
       job status) and any queue_records rows for the job
    3. Writes a decision_results audit row — action 'accept_node' for
       awaiting_review → complete, 'manual_status_change' otherwise
"""

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_default_root = Path(__file__).parent.parent
RUNTIME_ROOT  = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH       = RUNTIME_ROOT / "db" / "queue.db"

# Canon queue states — keep in sync with gddp-config schemas/v1/queue_record.yaml
QUEUE_STATES = [
    "intake", "classified", "blocked", "ready", "running",
    "awaiting_result", "awaiting_review", "complete", "failed",
    "deferred", "cancelled",
]
# jobs.status is a narrower enum; only mirror queue_state into it when valid
JOB_STATUSES = {"ready", "running", "awaiting_result", "awaiting_review", "complete", "failed"}


def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def resolve_job(con, ref: str):
    """Accept a job_id or node_id; node_id must match exactly one job."""
    job = con.execute("SELECT * FROM jobs WHERE job_id = ?", (ref,)).fetchone()
    if job:
        return job
    rows = con.execute(
        "SELECT * FROM jobs WHERE node_id = ? ORDER BY created_at DESC", (ref,)
    ).fetchall()
    if not rows:
        sys.exit(f"No job found for '{ref}' (tried job_id, then node_id).")
    if len(rows) > 1:
        print(f"'{ref}' matches {len(rows)} jobs — use a job_id:")
        for r in rows:
            print(f"  {r['job_id']}  {r['queue_state']}  created {r['created_at']}")
        sys.exit(1)
    return rows[0]


def cmd_list(args):
    con = connect()
    q = "SELECT job_id, node_id, queue_state, attempt, max_attempts, created_at FROM jobs"
    params = ()
    if args.state:
        q += " WHERE queue_state = ?"
        params = (args.state,)
    q += " ORDER BY created_at DESC"
    rows = con.execute(q, params).fetchall()
    if not rows:
        print("No jobs." + (f" (state={args.state})" if args.state else ""))
        return
    for r in rows:
        print(f"{r['job_id']}  {r['queue_state']:<16} {r['node_id']:<26} "
              f"attempt {r['attempt']}/{r['max_attempts']}  {r['created_at'][:10]}")


def parse_check(row):
    try:
        return json.loads(row["acceptance_check"]) if row["acceptance_check"] else {}
    except json.JSONDecodeError:
        return {}


def print_evaluation(check, full=False):
    """Print the evaluator's output for one result row — the thing under review."""
    if not check:
        print("          (no evaluator output on this result)")
        return
    integrity = check.get("integrity") or {}
    print(f"         verdict: {check.get('verdict')}  "
          f"(criteria: {check.get('criteria_verdict')} @ {check.get('criteria_confidence')}, "
          f"integrity: {integrity.get('verdict')} @ {integrity.get('confidence')})")
    for f in check.get("criteria_findings") or []:
        print(f"       criterion: {f.get('criterion_id')}  ->  {f.get('judgment')}")
        for ev in f.get("evidence") or []:
            print(f"                  evidence: {ev}")
    for f in integrity.get("findings") or []:
        print(f"       integrity: [{f.get('severity')}] {f.get('summary')}")
    if check.get("required_next_action"):
        print(f"     next action: {check['required_next_action']}  (evaluator template, not a decision)")
    if check.get("receipt_path"):
        print(f"         receipt: {check['receipt_path']}")
    if full and integrity.get("reasoning"):
        print(f"       reasoning: {integrity['reasoning']}")


def cmd_show(args):
    con = connect()
    job = resolve_job(con, args.ref)
    for key in ("job_id", "node_id", "title", "queue_state", "status", "executor",
                "job_type", "attempt", "max_attempts", "created_at", "artifacts_dir"):
        print(f"{key:>16}: {job[key]}")
    results = con.execute(
        "SELECT received_at, outcome, status, acceptance_check "
        "FROM results WHERE job_id = ? ORDER BY received_at",
        (job["job_id"],),
    ).fetchall()
    for r in results:
        print(f"          result: {r['received_at']}  {r['outcome']}/{r['status']}")
        print_evaluation(parse_check(r), full=args.full)
    decisions = con.execute(
        "SELECT created_at, action, reason FROM decision_results WHERE node_id = ? ORDER BY created_at",
        (job["node_id"],),
    ).fetchall()
    for d in decisions:
        print(f"        decision: {d['created_at']}  {d['action']}  {d['reason'] or ''}")


def cmd_results(args):
    con = connect()
    rows = con.execute(
        "SELECT r.received_at, r.acceptance_check, j.node_id, j.project_id, r.job_id "
        "FROM results r JOIN jobs j ON j.job_id = r.job_id ORDER BY r.received_at",
    ).fetchall()
    if not rows:
        print("No evaluator results.")
        return
    nodes = set()
    for r in rows:
        check = parse_check(r)
        verdict = check.get("verdict") or "-"
        nodes.add((r["project_id"], r["node_id"]))
        print(f"{r['received_at'][:19]}  {verdict:<5} {r['project_id'] or '-':<14} "
              f"{r['node_id'] or '-':<26} {r['job_id']}")
        if check.get("receipt_path"):
            print(f"{'':21}receipt: {check['receipt_path']}")
    print(f"\n{len(rows)} result row(s) across {len(nodes)} node(s).")


def cmd_set(args):
    if args.state not in QUEUE_STATES:
        sys.exit(f"Invalid state '{args.state}'. Valid: {' '.join(QUEUE_STATES)}")
    con = connect()
    job = resolve_job(con, args.ref)
    old = job["queue_state"]
    if old == args.state:
        print(f"{job['job_id']} already '{old}' — nothing to do.")
        return
    print(f"{job['job_id']}  ({job['node_id']})")
    print(f"  {old}  ->  {args.state}")
    if not args.yes:
        if input("Proceed? [y/N] ").strip().lower() != "y":
            sys.exit("Aborted.")

    con.execute("UPDATE jobs SET queue_state = ? WHERE job_id = ?",
                (args.state, job["job_id"]))
    if args.state in JOB_STATUSES:
        con.execute("UPDATE jobs SET status = ? WHERE job_id = ?",
                    (args.state, job["job_id"]))
    con.execute("UPDATE queue_records SET queue = ? WHERE job_id = ?",
                (args.state, job["job_id"]))

    action = "accept_node" if (old == "awaiting_review" and args.state == "complete") \
             else "manual_status_change"
    con.execute(
        "INSERT INTO decision_results (result_id, action, node_id, project_id, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"dec_{uuid.uuid4().hex[:12]}", action, job["node_id"], job["project_id"],
         args.reason, now()),
    )
    con.commit()
    print(f"Done: {job['job_id']} -> {args.state}  (audit: {action})")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list jobs and states")
    p_list.add_argument("--state", help="filter by queue_state")
    p_list.set_defaults(fn=cmd_list)

    p_show = sub.add_parser("show", help="show one job (accepts job_id or node_id)")
    p_show.add_argument("ref")
    p_show.add_argument("--full", action="store_true", help="include full integrity reasoning")
    p_show.set_defaults(fn=cmd_show)

    p_results = sub.add_parser("results", help="every evaluator output that exists, with counts")
    p_results.set_defaults(fn=cmd_results)

    p_set = sub.add_parser("set", help="set queue state (accepts job_id or node_id)")
    p_set.add_argument("ref")
    p_set.add_argument("state")
    p_set.add_argument("--reason", required=True, help="why — stored in the audit row")
    p_set.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    p_set.set_defaults(fn=cmd_set)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
