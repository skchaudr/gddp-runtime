"""
return_router.py — Convert merged PR events into review receipts.

Runtime does not mutate graph truth on the return path. A merged PR may create a
structured receipt in SQLite and move the matching job into `awaiting_review`.
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

from .results_store import DB_PATH, write_result

ALLOWED_REPOS = ["skchaudr/vault-doctor"]


def parse_node_id(pr_body: str) -> Optional[str]:
    """Extract `node: <node_id>` from the PR body."""
    if not pr_body:
        return None
    match = re.search(r"(?mi)^node:\s*(.+)$", pr_body)
    if match:
        return match.group(1).strip()
    return None


def parse_job_id(pr_body: str) -> Optional[str]:
    """Extract `job: <job_id>` from the PR body."""
    if not pr_body:
        return None
    match = re.search(r"(?mi)^job:\s*(.+)$", pr_body)
    if match:
        return match.group(1).strip()
    return None


def validate_repo(repo_name: str) -> bool:
    """Reject repos not in ALLOWED_REPOS."""
    return repo_name in ALLOWED_REPOS


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _load_job(job_id: str, con: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    owns_con = False
    if con is None:
        con = _connect()
        owns_con = True
    try:
        row = con.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        if owns_con:
            con.close()


def _mark_job_awaiting_review(job_id: str, con: Optional[sqlite3.Connection] = None) -> None:
    owns_con = False
    if con is None:
        con = _connect()
        owns_con = True
    try:
        con.execute(
            """
            UPDATE jobs
               SET status = 'awaiting_review',
                   queue_state = 'awaiting_review'
             WHERE job_id = ?
            """,
            (job_id,),
        )
        con.execute(
            "UPDATE queue_records SET queue = 'awaiting_review' WHERE job_id = ?",
            (job_id,),
        )
        if owns_con:
            con.commit()
    finally:
        if owns_con:
            con.close()


def handle_merged_pr(event: sqlite3.Row) -> dict:
    """
    Main entry point for merged PR handling.
    Returns review-routing status only; it never advances graph truth.
    """
    raw_path = event["raw_payload_path"]
    with open(raw_path) as f:
        payload = json.load(f)

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name")
    pr_number = pr.get("number")
    pr_body = pr.get("body", "")
    merged_at = pr.get("merged_at")
    merged_pr_url = pr.get("html_url")

    result_id = f"res_{event['event_id'][4:]}"

    if not validate_repo(repo_name):
        return {"status": "rejected", "reason": "repo_not_allowed"}

    node_id = parse_node_id(pr_body)
    if not node_id:
        return {"status": "rejected", "reason": "missing_node_tag"}

    job_id = parse_job_id(pr_body)
    if not job_id:
        return {"status": "rejected", "reason": "missing_job_tag"}

    con = _connect()
    try:
        job = _load_job(job_id, con)
        if job is None:
            return {"status": "rejected", "reason": "job_not_found"}

        if job["repo"] != repo_name:
            return {"status": "rejected", "reason": "repo_job_mismatch"}

        if job["node_id"] != node_id:
            return {"status": "rejected", "reason": "node_job_mismatch"}

        write_result(
            con=con,
            result_id=result_id,
            job_id=job_id,
            executor=job["executor"],
            outcome="success",
            status="needs_review",
            received_at=merged_at,
            github_action={
                "source": "merged_pr",
                "event_id": event["event_id"],
                "repo_name": repo_name,
                "pr_number": pr_number,
                "merged_at": merged_at,
                "merged_pr_url": merged_pr_url,
                "node_id": node_id,
                "review_required": True,
                "raw_payload_path": str(Path(raw_path)),
            },
        )

        _mark_job_awaiting_review(job_id, con)
        con.commit()
    finally:
        con.close()

    return {
        "status": "needs_review",
        "result_id": result_id,
        "job_id": job_id,
        "node_id": node_id,
    }
