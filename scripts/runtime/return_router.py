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
    return con


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
    verification = verify_job_return(job["project_id"], node_id)

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
    """Re-dispatch the same node to the executor with findings in the issue body.

    On dispatch failure, falls back to awaiting_review so the human can inspect
    the findings and decide — the job never sits in limbo.
    """
    import json
    from .heartbeat.dispatcher import dispatch

    # Build the job dict with findings injected
    job_with_findings = dict(job)
    # Convert constraints/acceptance_criteria from JSON strings if needed
    if isinstance(job_with_findings.get("constraints"), str):
        job_with_findings["constraints"] = json.loads(job_with_findings["constraints"])
    if isinstance(job_with_findings.get("acceptance_criteria"), str):
        job_with_findings["acceptance_criteria"] = json.loads(job_with_findings["acceptance_criteria"])

    # Add findings to the job for the adapter to include in the issue body
    integrity = verification.get("integrity", {}) if verification.get("verification_status") == "ok" else {}
    job_with_findings["_previous_findings"] = {
        "verdict": verification.get("verdict", ""),
        "integrity_verdict": integrity.get("verdict", ""),
        "findings": integrity.get("findings", []),
        "reasoning": integrity.get("reasoning", ""),
        "criteria_findings": verification.get("criteria_findings", []) if verification.get("verification_status") == "ok" else [],
    }

    # Dispatch
    dispatch_result = dispatch(job_with_findings, job["repo"])

    if not dispatch_result.success:
        # Dispatch failed — fall back to awaiting_review so the human sees the
        # findings and can re-dispatch manually. The job must not sit unattended.
        # Attempt is NOT incremented on failure so the retry budget stays intact.
        _mark_job_awaiting_review(job_id)
        return {
            "status": "needs_review",
            "result_id": result_id,
            "job_id": job_id,
            "node_id": node_id,
            "verification": verification,
            "dispatch_attempted": True,
            "dispatch_success": False,
            "dispatch_error": dispatch_result.error,
        }

    # Dispatch succeeded — increment attempt now that the retry is confirmed.
    con = _connect()
    try:
        con.execute(
            "UPDATE jobs SET attempt = attempt + 1 WHERE job_id = ?", (job_id,)
        )
        con.commit()
    finally:
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
