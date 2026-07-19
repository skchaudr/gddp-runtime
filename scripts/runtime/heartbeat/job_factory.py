"""
job_factory.py — Builds a job payload from a NodeData and event.

Returns a plain dict ready to INSERT into the jobs table.
Keeps all job construction logic in one place.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_id() -> str:
    # Truncating to [:17] keeps only centiseconds: two jobs built in the
    # same tick collided on identical ids (UNIQUE constraint, 2026-07-15).
    # A random suffix makes ids collision-proof; the timestamp prefix
    # stays first so ids still sort chronologically.
    ts = now().replace(":", "").replace("-", "").replace(".", "")[:17]
    return f"{ts}{uuid.uuid4().hex[:12]}"


def build_job(
    node,          # NodeData
    event: sqlite3.Row,
    project_id: str,
    repo: str,
    runtime_root: Path,
    executor: str,
) -> dict:
    job_id = f"job_{ts_id()}"
    artifacts_dir = runtime_root / "jobs" / job_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    return {
        "job_id":              job_id,
        "created_at":          now(),
        "event_id":            event["event_id"],
        "project_id":          project_id,
        "repo":                repo,
        "node_id":             node.node_id,
        "job_type":            "implementation",
        "executor":            executor,
        "queue_state":         "ready",
        "title":               node.title,
        "goal":                f"Produce a reviewable result for node {node.node_id}",
        "why":                 node.why.strip(),
        "constraints":         json.dumps(node.constraints),
        "acceptance_criteria": json.dumps(node.acceptance_criteria),
        "priority":            node.priority,
        "status":              "ready",
        "attempt":             0,
        "max_attempts":        3,
        "artifacts_dir":       str(artifacts_dir) + "/",
        "required_artifacts":  json.dumps(node.required_artifacts),
        "previous_findings":   None,
    }
