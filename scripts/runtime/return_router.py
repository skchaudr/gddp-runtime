"""
return_router.py — Core logic for processing merged PRs and advancing the graph.

When a PR merges, this module:
1. Validates the repo
2. Parses the node_id from the PR body
3. Records the attempt in results_store
4. Updates the graph via graph_updater
"""

import json
import re
import sqlite3
from typing import Optional

from .graph_updater import update_graph_node_complete
from .results_store import write_result

ALLOWED_REPOS = ["skchaudr/vault-doctor"]

def parse_node_id(pr_body: str) -> Optional[str]:
    """
    Extracts node id using regex matching "node: " on its own line.
    Case-insensitive, multiline.
    """
    if not pr_body:
        return None
    # Match "node: <node_id>" where <node_id> is the rest of the line
    match = re.search(r"(?mi)^node:\s*(.+)$", pr_body)
    if match:
        return match.group(1).strip()
    return None

def validate_repo(repo_name: str) -> bool:
    """Rejects repos not in ALLOWED_REPOS."""
    return repo_name in ALLOWED_REPOS

def handle_merged_pr(event: sqlite3.Row) -> dict:
    """
    Main entry point for the return loop.
    Returns a result dict for the caller/runner.
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

    # Generate a result_id based on event_id for tracking
    result_id = f"res_{event['event_id'][4:]}"

    # 1. Validate repo
    if not validate_repo(repo_name):
        write_result(
            result_id=result_id,
            repo_name=repo_name,
            status="rejected",
            reason=f"repo_not_allowed: {repo_name}",
            pr_number=pr_number
        )
        return {"status": "rejected", "reason": "repo_not_allowed"}

    # 2. Parse node_id
    node_id = parse_node_id(pr_body)
    if not node_id:
        write_result(
            result_id=result_id,
            repo_name=repo_name,
            status="rejected",
            reason="missing_node_tag",
            pr_number=pr_number
        )
        return {"status": "rejected", "reason": "missing_node_tag"}

    # 3. Write initial "pending" row
    write_result(
        result_id=result_id,
        repo_name=repo_name,
        node_id=node_id,
        pr_number=pr_number,
        merged_at=merged_at,
        status="pending"
    )

    # 4. Update graph
    # We need project_id. For now, assume it can be derived or is the same as repo name (last part)
    # The requirement doesn't specify how to get project_id, but vault-doctor repo usually maps to vault-doctor project
    project_id = repo_name.split("/")[-1]

    update_res = update_graph_node_complete(
        project_id=project_id,
        node_id=node_id,
        merged_pr=merged_pr_url,
        merged_at=merged_at
    )

    if update_res["ok"]:
        write_result(
            result_id=result_id,
            repo_name=repo_name,
            status="completed",
            commit_sha=update_res["commit_sha"]
        )
        return {"status": "completed", "commit_sha": update_res["commit_sha"]}
    else:
        write_result(
            result_id=result_id,
            repo_name=repo_name,
            status="failed",
            reason=update_res["reason"]
        )
        return {"status": "failed", "reason": update_res["reason"]}
