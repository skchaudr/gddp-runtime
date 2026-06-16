"""
intake_server.py — Webhook intake server for Phase 3.

Receives raw GitHub webhooks, normalizes them, writes to events table.
Raw payloads are saved under the runtime state root for auditing.

Run:
    python3 scripts/intake_server.py

Then expose via ngrok:
    ngrok http 5050
    → paste the https URL into GitHub repo webhook settings
"""

import hashlib
import hmac
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, request, jsonify

_default_root = Path(__file__).parent.parent
RUNTIME_ROOT  = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH       = RUNTIME_ROOT / "db" / "queue.db"

# Optional: set GITHUB_WEBHOOK_SECRET env var to validate signatures
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def verify_signature(payload_bytes: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        return False  # fail verification if no secret configured
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

def normalize_event(gh_event_type: str, payload: dict) -> dict | None:
    """
    Map a raw GitHub webhook payload to our normalized event schema.
    Returns None if the event type is not in our controlled taxonomy.
    """
    action = payload.get("action", "")
    pr     = payload.get("pull_request", {})
    issue  = payload.get("issue", {})
    repo   = payload.get("repository", {})
    sender = payload.get("sender", {})

    event_type_map = {
        ("pull_request", "opened"):       "pull_request.opened",
        ("pull_request", "synchronize"):  "pull_request.updated",
        ("pull_request", "closed"):       "pull_request.opened",  # may be a merge
        ("issues",       "opened"):       "issue.opened",
        ("issue_comment","created"):      "issue.commented",
        ("push",         ""):             "push.branch_updated",
        ("check_suite",  "completed"):    "workflow.succeeded",
        ("workflow_run", "completed"):    "workflow.succeeded",
        ("workflow_run", "failed"):       "workflow.failed",
    }

    mapped_type = event_type_map.get((gh_event_type, action))
    if mapped_type is None:
        return None  # unknown / unhandled event — will be stored as ignored

    # Pull PR or issue number
    pr_number    = pr.get("number") or (payload.get("pull_request", {}).get("number"))
    issue_number = issue.get("number")
    branch       = (pr.get("head", {}).get("ref")
                    or payload.get("ref", "").replace("refs/heads/", ""))
    base_branch  = pr.get("base", {}).get("ref", "main")
    commit_sha   = (pr.get("head", {}).get("sha")
                    or payload.get("after", ""))
    url          = pr.get("html_url") or issue.get("html_url") or ""

    ts = now()
    event_id = f"evt_{ts.replace(':', '').replace('-', '').replace('.', '')[:19]}"

    return {
        "event_id":                 event_id,
        "received_at":              ts,
        "source":                   "github",
        "event_type":               mapped_type,
        "actor":                    sender.get("login", ""),
        "branch":                   branch,
        "base_branch":              base_branch,
        "pr_number":                pr_number,
        "issue_number":             issue_number,
        "commit_sha":               commit_sha,
        "url":                      url,
        "project_id":               None,   # classifier fills this in
        "project_node_candidates":  json.dumps([]),
        "scope_status":             "pending",
        "priority":                 "pending",
        "risk_level":               "pending",
        "classification":           json.dumps({}),
        "routing":                  json.dumps({"selected_queue": "intake"}),
        "status":                   "received",
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/webhook")
def webhook():
    payload_bytes = request.get_data()
    sig           = request.headers.get("X-Hub-Signature-256", "")
    gh_event_type = request.headers.get("X-GitHub-Event", "")

    # 1. Signature check
    if not verify_signature(payload_bytes, sig):
        print("  [intake] REJECTED — invalid signature")
        return jsonify({"error": "invalid signature"}), 401

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        print("  [intake] REJECTED — invalid json")
        return jsonify({"error": "invalid json"}), 400

    # 2. Save raw payload to disk (always, regardless of type)
    raw_dir = RUNTIME_ROOT / "events" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_ts   = now().replace(":", "").replace("-", "")[:19]
    safe_event_type = os.path.basename(gh_event_type)
    raw_file = raw_dir / f"{safe_event_type}_{raw_ts}.json"
    raw_file.write_text(json.dumps(payload, indent=2))
    print(f"  [intake] raw payload saved → {raw_file.name}")

    # 3. Normalize
    event = normalize_event(gh_event_type, payload)
    if event is None:
        print(f"  [intake] IGNORED — no mapping for {gh_event_type}/{payload.get('action','')}")
        return jsonify({"status": "ignored"}), 200

    event["raw_payload_path"]        = str(raw_file)
    event["normalized_payload_path"] = str(
        RUNTIME_ROOT / "events" / "normalized" / f"{event['event_id']}.yaml"
    )

    # 4. Insert into events table
    try:
        con = connect()
        try:
            con.execute("""
                INSERT INTO events (
                    event_id, received_at, source, event_type, actor,
                    branch, base_branch, pr_number, issue_number, commit_sha, url,
                    project_id, project_node_candidates,
                    scope_status, priority, risk_level,
                    raw_payload_path, normalized_payload_path,
                    classification, routing, status
                ) VALUES (
                    :event_id, :received_at, :source, :event_type, :actor,
                    :branch, :base_branch, :pr_number, :issue_number, :commit_sha, :url,
                    :project_id, :project_node_candidates,
                    :scope_status, :priority, :risk_level,
                    :raw_payload_path, :normalized_payload_path,
                    :classification, :routing, :status
                )
            """, event)
            con.commit()
        finally:
            con.close()
    except sqlite3.Error as e:
        print(f"  [intake] REJECTED — database error: {e}")
        return jsonify({"error": "database error"}), 500

    print(f"  [intake] event inserted → {event['event_id']} ({event['event_type']})")
    return jsonify({"status": "accepted", "event_id": event["event_id"]}), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"ERROR: queue.db not found at {DB_PATH}")
        print("Run: python3 scripts/init_db.py first")
        sys.exit(1)

    print(f"Intake server starting on http://127.0.0.1:5050")
    print(f"DB: {DB_PATH}")
    print(f"Expose with: ngrok http 5050")
    app.run(host="127.0.0.1", port=5050, debug=False)
