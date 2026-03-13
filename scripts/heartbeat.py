"""
heartbeat.py — Polls for pending events, creates jobs, dispatches to Jules.

Run once manually for Phase 3. In Phase 5 this becomes a scheduled cron job.

Usage:
    python3 scripts/heartbeat.py --repo skchaudr/test-project --node auth-boundary

What it does:
    1. Reads events with status = 'received'
    2. Classifies each event (hardcoded rules for Phase 3)
    3. Checks that the target node is 'ready' (hardcoded for Phase 3)
    4. Creates a job and queue record
    5. Dispatches to Jules via JulesActionAdapter
    6. Updates event status to 'mapped' and job status to 'running'
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from adapters.jules_action_adapter import JulesActionAdapter

DB_PATH     = Path(__file__).parent.parent / "db" / "queue.db"
OPCLAW_ROOT = Path(__file__).parent.parent


def now():
    return datetime.now(timezone.utc).isoformat()

def job_dir(job_id: str) -> Path:
    d = OPCLAW_ROOT / "jobs" / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def ts_id():
    return now().replace(":", "").replace("-", "").replace(".", "")[:17]


# ---------------------------------------------------------------------------
# Phase 3: hardcoded classifier
# In Phase 4+, this becomes a real classifier that reads the graph.
# ---------------------------------------------------------------------------

PHASE3_NODE = {
    "node_id":   "scan-vault-core",
    "title":     "Implement VaultDoctor scan_vault foundation",
    "goal":      "Move node scan-vault-core from ready to complete",
    "why":       "All other vault-doctor features depend on a working scan_vault() foundation",
    "constraints": [
        "implement in src/doctor.py only — do not modify triage.py",
        "do not delete or modify the mock vault files added in the previous PR",
        "use only libraries already in requirements.txt (python-frontmatter, rich, pyyaml)",
        "do not add new dependencies",
        "keep implementation simple — this is a foundation, not a full feature",
    ],
    "acceptance_criteria": [
        "VaultDoctor class exists in src/doctor.py",
        "scan_vault(vault_path) walks the directory tree and returns a list of file metadata dicts",
        "each metadata dict contains at minimum: path, size_bytes, extension, modified_at",
        "scan_vault correctly ignores .obsidian/ system files",
        "at least 3 passing tests in tests/test_doctor.py covering scan output structure",
        "tests use the existing mock vault at vault_doctor/mock_vault/ as fixture",
    ],
    "required_artifacts": ["decision.md", "result-summary.md", "patch.diff", "graph-update.yaml"],
}


def classify(event: sqlite3.Row) -> dict | None:
    """
    Returns classification dict if the event maps to a known node, else None.
    Only issue.opened events trigger implementation dispatch.
    pull_request.opened events are review signals — never dispatch Jules for these.
    """
    if event["event_type"] != "issue.opened":
        return None

    return {
        "category":                "implementation_request",
        "intent":                  "advance_existing_node",
        "in_scope":                True,
        "matched_node_id":         PHASE3_NODE["node_id"],
        "executor_recommendation": "jules",
        "requires_code_execution": True,
        "requires_human_review":   False,
    }


def run_heartbeat(repo: str):
    con = connect()
    cur = con.cursor()

    # Fetch all unprocessed events
    cur.execute("SELECT * FROM events WHERE status = 'received'")
    events = cur.fetchall()

    if not events:
        print("No pending events.")
        con.close()
        return

    print(f"Found {len(events)} pending event(s).\n")

    for event in events:
        event_id = event["event_id"]
        print(f"Processing: {event_id} ({event['event_type']})")

        # 1. Classify
        classification = classify(event)
        if classification is None:
            cur.execute(
                "UPDATE events SET status = 'ignored' WHERE event_id = ?", (event_id,)
            )
            print(f"  → ignored (no node mapping)\n")
            continue

        cur.execute(
            "UPDATE events SET status = 'classified', classification = ?, scope_status = 'in_scope' WHERE event_id = ?",
            (json.dumps(classification), event_id)
        )

        # 2. Create job
        job_id    = f"job_{ts_id()}"
        artifacts = str(job_dir(job_id)) + "/"

        cur.execute("""
            INSERT INTO jobs (
                job_id, created_at, event_id, project_id, repo, node_id,
                job_type, executor, queue_state, title, goal, why,
                constraints, acceptance_criteria,
                priority, status, attempt, max_attempts, artifacts_dir
            ) VALUES (?, ?, ?, 'phase3-project', ?, ?, 'implementation', 'jules', 'ready',
                      ?, ?, ?, ?, ?, 'high', 'ready', 0, 3, ?)
        """, (
            job_id, now(), event_id, repo,
            PHASE3_NODE["node_id"],
            PHASE3_NODE["title"],
            PHASE3_NODE["goal"],
            PHASE3_NODE["why"],
            json.dumps(PHASE3_NODE["constraints"]),
            json.dumps(PHASE3_NODE["acceptance_criteria"]),
            artifacts,
        ))

        cur.execute("""
            INSERT INTO queue_records (queue_item_id, job_id, queue, available_at)
            VALUES (?, ?, 'ready', ?)
        """, (f"qi_{ts_id()}", job_id, now()))

        print(f"  → job created: {job_id}")

        # 3. Dispatch to Jules via GitHub Action adapter
        node = dict(PHASE3_NODE)
        node["job_id"]   = job_id
        node["constraints"]          = json.dumps(node["constraints"])
        node["acceptance_criteria"]  = json.dumps(node["acceptance_criteria"])

        adapter = JulesActionAdapter(repo=repo)
        result  = adapter.dispatch(node)

        if result.success:
            cur.execute(
                "UPDATE events SET status = 'mapped' WHERE event_id = ?", (event_id,)
            )
            cur.execute(
                "UPDATE jobs SET status = 'running', queue_state = 'running' WHERE job_id = ?",
                (job_id,)
            )
            cur.execute(
                "UPDATE queue_records SET queue = 'running' WHERE job_id = ?", (job_id,)
            )
            print(f"  → dispatched to Jules")
            print(f"  → issue: {result.issue_url}")
        else:
            cur.execute(
                "UPDATE jobs SET status = 'failed', queue_state = 'failed' WHERE job_id = ?",
                (job_id,)
            )
            print(f"  → DISPATCH FAILED: {result.error}")

        print()

    con.commit()
    con.close()
    print("Heartbeat complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo",  required=True, help="GitHub repo (owner/name)")
    args = parser.parse_args()
    run_heartbeat(args.repo)
