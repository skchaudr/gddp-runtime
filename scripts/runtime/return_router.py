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
from .verification.bridge import verify_job_return
from .heartbeat.state_recorder import (
    allocate_retry_attempt,
    finalize_executor_session_dispatch,
    mark_job_running,
)

_FALLBACK_ALLOWED_REPOS = ["skchaudr/vault-doctor", "skchaudr/test-project", "skchaudr/gddp-runtime"]


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


def validate_repo(repo_name: str, allowed_repos: list | None = None) -> bool:
    """Reject repos not in the allowed list."""
    repos = allowed_repos if allowed_repos else _FALLBACK_ALLOWED_REPOS
    return repo_name in repos


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    # Concurrency: WAL lets readers overlap the single writer; busy_timeout
    # makes a colliding writer wait instead of raising 'database is locked'.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _refresh_evaluations_export() -> None:
    """Best-effort refresh of the evaluations export after a result lands.

    Runs scripts/export_evaluations.py as a subprocess so nothing it does
    (yaml errors, missing gddp-config, permissions) can break the return path.
    """
    import subprocess
    import sys

    exporter = Path(__file__).resolve().parent.parent / "export_evaluations.py"
    try:
        subprocess.run(
            [sys.executable, str(exporter)],
            capture_output=True, timeout=30, check=False,
        )
    except Exception:
        pass


def _load_job(job_id: str) -> Optional[dict]:
    con = _connect()
    try:
        row = con.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        con.close()


def _mark_job_awaiting_review(job_id: str) -> None:
    con = _connect()
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
        con.commit()
    finally:
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
    merge_commit_sha = pr.get("merge_commit_sha")

    result_id = f"res_{event['event_id'][4:]}"

    if not validate_repo(repo_name):
        return {"status": "rejected", "reason": "repo_not_allowed"}

    node_id = parse_node_id(pr_body)
    if not node_id:
        return {"status": "rejected", "reason": "missing_node_tag"}

    job_id = parse_job_id(pr_body)
    if not job_id:
        return {"status": "rejected", "reason": "missing_job_tag"}

    job = _load_job(job_id)
    if job is None:
        return {"status": "rejected", "reason": "job_not_found"}

    if job["repo"] != repo_name:
        return {"status": "rejected", "reason": "repo_job_mismatch"}

    if job["node_id"] != node_id:
        return {"status": "rejected", "reason": "node_job_mismatch"}

    # E1: run the evaluator automatically so the human reviews a receipt, not a
    # raw diff. The verdict is evidence only — the job routes to awaiting_review
    # regardless of outcome, and an evaluator failure is recorded, never fatal.
    # Phase 1: pass merge_commit_sha and pr_ref so the evaluator judges the
    # exact merged state in an isolated worktree, not whatever is on disk.
    pr_ref = str(pr_number) if pr_number else merged_pr_url
    verification = verify_job_return(
        job["project_id"], node_id,
        merge_commit_sha=merge_commit_sha,
        pr_ref=pr_ref,
        job_id=job_id,
        attempt=job.get("attempt", 0),
    )

    write_result(
        result_id=result_id,
        job_id=job_id,
        executor=job["executor"],
        outcome="success",
        status="needs_review",
        received_at=merged_at,
        acceptance_check=verification,
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

    # Live wire: refresh verification/<project>/evaluations.yaml so
    # every reading surface (jobs_status.py, graph viewer) sees this result
    # without a manual export. Best-effort — a broken export never blocks routing.
    _refresh_evaluations_export()

    # Retry loop: if the verdict is non-pass with evidence-referenced findings
    # and the project's retry budget has room, re-dispatch instead of awaiting_review.
    from scripts.runtime.verification.retry_budget import should_retry

    # Load the project YAML for retry_budget
    config_root = _config_root()
    project_yaml_path = config_root / "graphs" / job["project_id"] / "project.yaml"
    project_yaml = {}
    if project_yaml_path.exists():
        import yaml
        project_yaml = yaml.safe_load(project_yaml_path.read_text()) or {}

    # Secondary validation: if the project declares its own allowed_repos,
    # re-validate against that list (the initial check used the fallback list).
    project_allowed = project_yaml.get("execution_policy", {}).get("allowed_repos")
    if project_allowed and not validate_repo(repo_name, project_allowed):
        return {"status": "rejected", "reason": "repo_not_allowed_by_project"}

    # Extract integrity from the verification result
    integrity = verification.get("integrity") if verification.get("verification_status") == "ok" else None
    verdict = verification.get("verdict", "") if verification.get("verification_status") == "ok" else ""

    criteria_findings = verification.get("criteria_findings") if verification.get("verification_status") == "ok" else None
    if should_retry(verdict=verdict, integrity=integrity, job=job, project_yaml=project_yaml, criteria_findings=criteria_findings):
        result = _redispatch_with_findings(job_id, job, node_id, verification, result_id)
        return result

    _mark_job_awaiting_review(job_id)

    return {
        "status": "needs_review",
        "result_id": result_id,
        "job_id": job_id,
        "node_id": node_id,
        "verification": verification,
    }


def _config_root():
    import os
    from pathlib import Path
    _runtime_root = Path(__file__).resolve().parents[2]
    return Path(os.environ.get("GDDP_CONFIG_PATH", str(_runtime_root.parent / "gddp-config")))


def _redispatch_with_findings(job_id, job, node_id, verification, result_id):
    """Persist a correction attempt before dispatch and retain its evidence."""
    from .heartbeat.dispatcher import cancel_remote_session, dispatch

    integrity = (
        verification.get("integrity", {})
        if verification.get("verification_status") == "ok"
        else {}
    )
    previous_findings = {
        "verdict": verification.get("verdict", ""),
        "integrity_verdict": integrity.get("verdict", ""),
        "findings": integrity.get("findings", []),
        "reasoning": integrity.get("reasoning", ""),
        "criteria_findings": (
            verification.get("criteria_findings", [])
            if verification.get("verification_status") == "ok"
            else []
        ),
    }

    con = _connect()
    allocated = allocate_retry_attempt(
        con,
        job,
        executor=job["executor"],
        previous_findings=previous_findings,
    )
    if allocated is None:
        con.close()
        _mark_job_awaiting_review(job_id)
        return {
            "status": "needs_review",
            "result_id": result_id,
            "job_id": job_id,
            "node_id": node_id,
            "verification": verification,
            "dispatch_attempted": False,
            "dispatch_success": False,
        }

    job_with_findings, session_db_id = allocated
    con.commit()
    try:
        dispatch_result = dispatch(job_with_findings, job["repo"])
    except Exception as exc:
        dispatch_result = None
        dispatch_error = f"retry dispatch raised exception: {exc}"
    else:
        dispatch_error = dispatch_result.error or "retry dispatch failed"

    if dispatch_result is None or not dispatch_result.success:
        finalized = finalize_executor_session_dispatch(
            con,
            session_db_id,
            state="dispatch_failed",
            error=dispatch_error,
        )
        con.commit()
        con.close()
        if not finalized:
            return {
                "status": "dispatch_superseded",
                "result_id": result_id,
                "job_id": job_id,
                "node_id": node_id,
                "verification": verification,
                "dispatch_attempted": True,
                "dispatch_success": False,
                "dispatch_error": dispatch_error,
                "reservation_finalized": False,
            }
        _mark_job_awaiting_review(job_id)
        return {
            "status": "needs_review",
            "result_id": result_id,
            "job_id": job_id,
            "node_id": node_id,
            "verification": verification,
            "dispatch_attempted": True,
            "dispatch_success": False,
            "dispatch_error": dispatch_error,
        }

    if dispatch_result.session_ref is not None:
        finalized = finalize_executor_session_dispatch(
            con,
            session_db_id,
            state="dispatched",
            executor=dispatch_result.session_ref.executor,
            session_id=dispatch_result.session_ref.session_id,
        )
    else:
        finalized = finalize_executor_session_dispatch(
            con,
            session_db_id,
            state="mediated",
            session_id=dispatch_result.issue_url,
        )
    if not finalized:
        cancellation = "reservation is no longer dispatching"
        if dispatch_result.session_ref is not None:
            _, cancellation = cancel_remote_session(
                dispatch_result.session_ref, job["repo"]
            )
        con.commit()
        con.close()
        return {
            "status": "dispatch_superseded",
            "result_id": result_id,
            "job_id": job_id,
            "node_id": node_id,
            "verification": verification,
            "dispatch_success": True,
            "reservation_finalized": False,
            "cancellation": cancellation,
        }
    mark_job_running(con, job_id)
    con.commit()
    con.close()

    return {
        "status": "redispatched",
        "result_id": result_id,
        "job_id": job_id,
        "node_id": node_id,
        "verification": verification,
        "dispatch_success": True,
        "issue_url": dispatch_result.issue_url,
    }
