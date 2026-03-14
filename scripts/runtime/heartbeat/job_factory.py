"""
job_factory.py — Builds a job payload from a NodeData and event.

Returns a plain dict ready to INSERT into the jobs table.
Keeps all job construction logic in one place.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_id() -> str:
    return now().replace(":", "").replace("-", "").replace(".", "")[:17]


def build_job(
    node,          # NodeData
    event: sqlite3.Row,
    project_id: str,
    repo: str,
    opclaw_root: Path,
) -> dict:
    job_id = f"job_{ts_id()}"
    artifacts_dir = opclaw_root / "jobs" / job_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    return {
        "job_id":              job_id,
        "created_at":          now(),
        "event_id":            event["event_id"],
        "project_id":          project_id,
        "repo":                repo,
        "node_id":             node.node_id,
        "job_type":            "implementation",
        "executor":            "jules",
        "queue_state":         "ready",
        "title":               node.title,
        "goal":                f"Move node {node.node_id} from ready to complete",
        "why":                 node.why.strip(),
        "constraints":         json.dumps(node.constraints),
        "acceptance_criteria": json.dumps(node.acceptance),
        "priority":            node.priority,
        "status":              "ready",
        "attempt":             0,
        "max_attempts":        3,
        "artifacts_dir":       str(artifacts_dir) + "/",
        # These are passed to the adapter — not stored in the DB directly
        "_required_artifacts": node.required_artifacts,
    }
