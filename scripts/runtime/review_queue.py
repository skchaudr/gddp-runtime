"""
review_queue.py — Discover, claim, and complete verification jobs.

The review queue sits between the return router (which creates receipts)
and the conductor (which runs verification). It provides:
- poll: find jobs awaiting review
- claim: atomically mark a job as being verified (prevents concurrent processing)
- complete: write the verification verdict and update job status
"""

import sqlite3
from datetime import datetime, timezone

from .results_store import DB_PATH, write_result

# Map from DecisionOutput.verdict to result status.
VERDICT_STATUS_MAP = {
    "ACCEPT": "verified_accept",
    "FAIL": "verified_fail",
    "NEEDS_REVIEW": "escalated",
    "INVALID": "verified_fail",
    "INCOMPLETE": "verified_incomplete",
}


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def poll_awaiting_review() -> list[dict]:
    """Return all result rows with status='needs_review'."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT * FROM results WHERE status = 'needs_review' ORDER BY received_at"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def claim_for_verification(result_id: str) -> bool:
    """Atomically mark a result as being verified.

    Sets status from 'needs_review' to 'verifying'.
    Returns True if the claim succeeded (row was in needs_review state).
    Returns False if already claimed or not found.
    """
    con = _connect()
    try:
        cur = con.execute(
            "UPDATE results SET status = 'verifying' "
            "WHERE result_id = ? AND status = 'needs_review'",
            (result_id,),
        )
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def _load_result(result_id: str) -> dict | None:
    """Load a single result row by ID."""
    con = _connect()
    try:
        row = con.execute(
            "SELECT * FROM results WHERE result_id = ?", (result_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def complete_verification(
    result_id: str,
    verdict: str,
    reason: str,
    severity: str | None,
    matrix_row: int,
    structural_passed: bool,
    structural_results: list[dict],
) -> None:
    """Write the verdict into the results row and update status.

    Uses write_result() to update the existing row:
    - acceptance_check = verdict JSON blob
    - risks = structural results JSON
    - status = verdict-appropriate final state

    Status mapping:
      ACCEPT        -> 'verified_accept'
      FAIL          -> 'verified_fail'
      NEEDS_REVIEW  -> 'escalated'
      INVALID       -> 'verified_fail'
      INCOMPLETE    -> 'verified_incomplete'
    """
    existing = _load_result(result_id)
    if existing is None:
        raise ValueError(f"Result not found: {result_id}")

    verdict_status = VERDICT_STATUS_MAP.get(verdict, "verified_fail")

    verdict_blob = {
        "verdict": verdict,
        "reason": reason,
        "severity": severity,
        "matrix_row": matrix_row,
        "structural_passed": structural_passed,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }

    write_result(
        result_id=result_id,
        job_id=existing["job_id"],
        executor=existing["executor"],
        outcome=existing["outcome"],
        status=verdict_status,
        received_at=existing["received_at"],
        acceptance_check=verdict_blob,
        risks=structural_results,
        github_action=existing.get("github_action"),
    )
