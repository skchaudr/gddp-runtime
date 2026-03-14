"""
graph_updater.py — Updates the project graph via GitHub Contents API.

Directly commits changes to gddp-config/graphs/<project_id>/project.yaml.
"""

import base64
import json
import os
import requests
import yaml
from typing import Dict, Any, Tuple

# Use skchaudr/gddp-config as the source of truth for graphs
CONFIG_REPO = "skchaudr/gddp-config"
API_BASE = "https://api.github.com"


def update_graph_node_complete(
    project_id: str,
    node_id: str,
    merged_pr: str,
    merged_at: str
) -> Dict[str, Any]:
    """
    Moves a node status to 'complete' in project.yaml via GitHub API.

    Returns:
        dict: { "ok": bool, "reason": str, "commit_sha": str }
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return {"ok": False, "reason": "GITHUB_TOKEN_missing"}

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    path = f"graphs/{project_id}/project.yaml"
    url = f"{API_BASE}/repos/{CONFIG_REPO}/contents/{path}"

    # 1. Read current file (to get content and SHA)
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return {"ok": False, "reason": "project_not_found"}

    data = resp.json()
    current_sha = data["sha"]
    content_b64 = data["content"]
    content_str = base64.b64decode(content_b64).decode("utf-8")

    try:
        project_data = yaml.safe_load(content_str)
    except Exception:
        return {"ok": False, "reason": "yaml_parse_failed"}

    # 2. Update the node status
    nodes = project_data.get("nodes", [])
    target_node = next((n for n in nodes if n.get("id") == node_id), None)

    if not target_node:
        return {"ok": False, "reason": "node_not_found"}

    if target_node.get("status") == "complete":
        return {"ok": False, "reason": "already_complete"}

    target_node["status"] = "complete"
    target_node["completed_at"] = merged_at
    target_node["merged_pr"] = merged_pr

    # 3. Write back to GitHub
    updated_content = yaml.dump(project_data, sort_keys=False)
    updated_b64 = base64.b64encode(updated_content.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"Complete node {node_id} via return-router",
        "content": updated_b64,
        "sha": current_sha
    }

    put_resp = requests.put(url, headers=headers, json=payload)
    if put_resp.status_code not in (200, 201):
        try:
            err_msg = put_resp.json().get("message", put_resp.text)
        except Exception:
            err_msg = put_resp.text
        return {"ok": False, "reason": f"github_commit_failed: {err_msg}"}

    commit_sha = put_resp.json().get("commit", {}).get("sha")
    return {"ok": True, "commit_sha": commit_sha}
