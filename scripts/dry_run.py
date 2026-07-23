"""
dry_run.py — Fake end-to-end flow for Phase 2 verification.

Walks one mock GitHub PR event through the full pipeline:
  inject event → classify → scope check → create job → queue →
  simulate result → write artifacts → simulate merged PR → return router

No real executors are called. No GitHub API. SQLite only.
The verification bridge is mocked so no real LLM call happens.
"""

import json
import os
import sqlite3
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `from scripts.runtime...` imports when run as a plain script.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_default_root = Path(__file__).parent.parent
RUNTIME_ROOT  = Path(os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root))
DB_PATH       = RUNTIME_ROOT / "db" / "queue.db"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now():
    return datetime.now(timezone.utc).isoformat()

def job_dir(job_id):
    d = RUNTIME_ROOT / "jobs" / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def step(label):
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")


# ---------------------------------------------------------------------------
# Step 1: Inject fake event
# ---------------------------------------------------------------------------

def inject_event(cur):
    step("STEP 1 — Inject normalized event")

    event = {
        "event_id":                 "evt_dry_001",
        "received_at":              now(),
        "source":                   "github",
        "event_type":               "pull_request.opened",
        "actor":                    "dry-run-user",
        "branch":                   "feature/auth-boundary",
        "base_branch":              "main",
        "pr_number":                42,
        "issue_number":             None,
        "commit_sha":               "abc123def456",
        "url":                      "https://github.com/skchaudr/test-project/pull/42",
        "project_id":               "test-project",
        "project_node_candidates":  json.dumps(["auth-boundary"]),
        "scope_status":             "pending",
        "priority":                 "pending",
        "risk_level":               "pending",
        "raw_payload_path":         str(RUNTIME_ROOT / "events/raw/evt_dry_001.json"),
        "normalized_payload_path":  str(RUNTIME_ROOT / "events/normalized/evt_dry_001.yaml"),
        "classification":           json.dumps({}),
        "routing":                  json.dumps({"selected_queue": "intake"}),
        "status":                   "received",
    }

    # Write raw payload stub
    raw_path = RUNTIME_ROOT / "events/raw/evt_dry_001.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps({"stub": "raw github webhook payload"}, indent=2))

    cur.execute("""
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

    print(f"  event_id : {event['event_id']}")
    print(f"  source   : {event['source']}")
    print(f"  type     : {event['event_type']}")
    print(f"  project  : {event['project_id']}")
    print(f"  status   : {event['status']}")
    return event["event_id"]


# ---------------------------------------------------------------------------
# Step 2: Classify + scope check
# ---------------------------------------------------------------------------

def classify_and_scope(cur, event_id):
    step("STEP 2 — Classify and scope check")

    # Simulate: classifier maps event to node auth-boundary
    classification = {
        "category":                 "implementation_request",
        "intent":                   "implement_existing_node",
        "in_scope":                 True,
        "matched_node_id":          "auth-boundary",
        "executor_recommendation":  "jules",
        "needs_vertex_reasoning":   False,
        "requires_code_execution":  True,
        "requires_human_review":    False,
    }
    routing = {
        "selected_executor": "jules",
        "selected_queue":    "ready",
    }

    cur.execute("""
        UPDATE events
        SET classification = ?, routing = ?, scope_status = 'in_scope',
            priority = 'high', risk_level = 'medium', status = 'classified'
        WHERE event_id = ?
    """, (json.dumps(classification), json.dumps(routing), event_id))

    print(f"  category         : {classification['category']}")
    print(f"  matched_node_id  : {classification['matched_node_id']}")
    print(f"  executor         : {classification['executor_recommendation']}")
    print(f"  event status     → classified")


# ---------------------------------------------------------------------------
# Step 3: Create job
# ---------------------------------------------------------------------------

def create_job(cur, event_id):
    step("STEP 3 — Create job from node auth-boundary")

    job_id = "job_dry_001"
    artifacts = str(RUNTIME_ROOT / "jobs" / job_id) + "/"
    job_dir(job_id)  # create folder

    job = {
        "job_id":               job_id,
        "created_at":           now(),
        "event_id":             event_id,
        "project_id":           "test-project",
        "repo":                 "skchaudr/test-project",
        "node_id":              "auth-boundary",
        "job_type":             "implementation",
        "executor":             "jules",
        "queue_state":          "ready",
        "title":                "Implement authenticated request boundary",
        "goal":                 "Produce a reviewable result for node auth-boundary",
        "why":                  "Protected actions must only execute for verified users",
        "source_context":       json.dumps({
            "starting_branch": "feature/auth-boundary",
            "target_branch":   "main",
            "relevant_paths":  ["app/", "middleware.ts", "server/", "tests/"],
            "related_pr":      42,
        }),
        "constraints":          json.dumps([
            "do not couple auth logic to UI components",
            "preserve future support for role-based permissions",
        ]),
        "acceptance_criteria":  json.dumps([
            "protected routes reject unauthenticated requests",
            "authenticated users can access protected actions",
            "tests exist for both allowed and denied cases",
        ]),
        "dependencies":         json.dumps(["node:user-session-model"]),
        "priority":             "high",
        "risk_level":           "medium",
        "estimated_effort":     "medium",
        "status":               "ready",
        "attempt":              0,
        "max_attempts":         3,
        "artifacts_dir":        artifacts,
        "result_summary_path":  None,
    }

    cur.execute("""
        INSERT INTO jobs (
            job_id, created_at, event_id, project_id, repo, node_id,
            job_type, executor, queue_state, title, goal, why,
            source_context, constraints, acceptance_criteria, dependencies,
            priority, risk_level, estimated_effort,
            status, attempt, max_attempts, artifacts_dir, result_summary_path
        ) VALUES (
            :job_id, :created_at, :event_id, :project_id, :repo, :node_id,
            :job_type, :executor, :queue_state, :title, :goal, :why,
            :source_context, :constraints, :acceptance_criteria, :dependencies,
            :priority, :risk_level, :estimated_effort,
            :status, :attempt, :max_attempts, :artifacts_dir, :result_summary_path
        )
    """, job)

    # Mark event as mapped
    cur.execute("UPDATE events SET status = 'mapped' WHERE event_id = ?", (event_id,))

    # Write job.yaml to artifact folder
    (RUNTIME_ROOT / "jobs" / job_id / "job.yaml").write_text(
        f"# Job artifact\njob_id: {job_id}\nnode_id: auth-boundary\nexecutor: jules\n"
    )

    print(f"  job_id     : {job['job_id']}")
    print(f"  node_id    : {job['node_id']}")
    print(f"  executor   : {job['executor']}")
    print(f"  artifacts  : {artifacts}")
    print(f"  event status → mapped")
    return job_id


# ---------------------------------------------------------------------------
# Step 4: Queue record
# ---------------------------------------------------------------------------

def enqueue(cur, job_id):
    step("STEP 4 — Add to queue")

    cur.execute("""
        INSERT INTO queue_records (queue_item_id, job_id, queue, available_at)
        VALUES (?, ?, 'ready', ?)
    """, ("qi_dry_001", job_id, now()))

    print(f"  queue_item_id : qi_dry_001")
    print(f"  job_id        : {job_id}")
    print(f"  queue state   : ready")


# ---------------------------------------------------------------------------
# Step 5: Simulate executor result
# ---------------------------------------------------------------------------

def simulate_result(cur, job_id):
    step("STEP 5 — Simulate executor result (jules)")

    result_id = "res_dry_001"
    d = job_dir(job_id)

    # Write fake artifacts to job folder
    (d / "decision.md").write_text(
        "# Decision\n\n## Trigger\nPR #42 opened on feature/auth-boundary\n\n"
        "## Mapped Node\nauth-boundary\n\n## Selected Executor\nJules\n\n"
        "## Constraints Applied\n- no UI coupling\n- preserve RBAC extensibility\n"
    )
    (d / "result-summary.md").write_text(
        "# Result Summary\n\nImplemented JWT middleware in middleware.ts.\n"
        "Added tests in tests/auth-boundary.test.ts.\nAll 3 acceptance criteria met.\n"
    )
    (d / "patch.diff").write_text(
        "--- a/middleware.ts\n+++ b/middleware.ts\n@@ -0,0 +1,12 @@\n"
        "+// auth middleware stub (dry run)\n"
    )
    acceptance_check = {
        "protected_routes_reject_unauthenticated": "pass",
        "authenticated_users_can_access":          "pass",
        "tests_exist":                             "pass",
    }

    cur.execute("""
        INSERT INTO results (
            result_id, job_id, executor, received_at,
            execution_duration_seconds, outcome, status,
            changed_files, patch_path, summary_path, logs_path,
            acceptance_check, risks, followup_candidates
        ) VALUES (?, ?, 'jules', ?, 12, 'success', 'needs_review', ?, ?, ?, ?, ?, ?, ?)
    """, (
        result_id, job_id, now(),
        json.dumps(["middleware.ts", "tests/auth-boundary.test.ts"]),
        str(d / "patch.diff"),
        str(d / "result-summary.md"),
        str(d / "logs/"),
        json.dumps(acceptance_check),
        json.dumps(["role-based permissions deferred"]),
        json.dumps(["role-permission-layer"]),
    ))

    cur.execute("""
        UPDATE jobs SET status = 'awaiting_review', queue_state = 'awaiting_review'
        WHERE job_id = ?
    """, (job_id,))

    print(f"  result_id   : {result_id}")
    print(f"  outcome     : success")
    print(f"  duration    : 12s (simulated)")
    print(f"  artifacts written to: {d}")
    return result_id


# ---------------------------------------------------------------------------
# Step 6: Simulate merged PR + return router + bridge
# ---------------------------------------------------------------------------

def simulate_merged_pr(cur, job_id):
    step("STEP 6 — Simulate merged PR + return router + bridge")

    from unittest.mock import patch
    from scripts.runtime.return_router import handle_merged_pr

    # Write a fake merged-PR payload
    pr_payload = {
        "repository": {"full_name": "skchaudr/test-project"},
        "pull_request": {
            "number": 42,
            "body": "Implemented auth boundary.\n\nnode: auth-boundary\njob: job_dry_001",
            "merged_at": now(),
            "html_url": "https://github.com/skchaudr/test-project/pull/42",
        },
    }
    pr_path = RUNTIME_ROOT / "events/raw/pr_dry_001.json"
    pr_path.parent.mkdir(parents=True, exist_ok=True)
    pr_path.write_text(json.dumps(pr_payload, indent=2))

    # Insert a merged-PR event
    pr_event = {
        "event_id":                 "evt_dry_pr_001",
        "received_at":              now(),
        "source":                   "github",
        "event_type":               "pull_request.closed",
        "actor":                    "dry-run-user",
        "branch":                   "feature/auth-boundary",
        "base_branch":              "main",
        "pr_number":                42,
        "issue_number":             None,
        "commit_sha":               "abc123def456",
        "url":                      "https://github.com/skchaudr/test-project/pull/42",
        "project_id":               "test-project",
        "project_node_candidates":  json.dumps(["auth-boundary"]),
        "scope_status":             "pending",
        "priority":                 "pending",
        "risk_level":               "pending",
        "raw_payload_path":         str(pr_path),
        "normalized_payload_path":  str(RUNTIME_ROOT / "events/normalized/evt_dry_pr_001.yaml"),
        "classification":           json.dumps({}),
        "routing":                  json.dumps({"selected_queue": "intake"}),
        "status":                   "received",
    }
    cur.execute("""
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
    """, pr_event)

    # handle_merged_pr opens its own connection (_load_job, write_result,
    # _mark_job_awaiting_review), so commit the event/job rows first or the
    # job lookup will fail with job_not_found.
    cur.connection.commit()

    # Mock the bridge so no real LLM call happens
    fake_verification = {
        "verification_status":   "ok",
        "receipt_path":          "/tmp/dry_run_receipt.json",
        "verdict":               "pass",
        "criteria_confidence":   0.9,
        "completeness_status":   "complete",
        "required_next_action":  "Proceed to accept_node (open evidence PR).",
    }

    # handle_merged_pr expects a sqlite3.Row-like object with event_id and
    # raw_payload_path accessible via __getitem__.
    event_row_data = {"event_id": "evt_dry_pr_001", "raw_payload_path": str(pr_path)}
    class FakeEventRow:
        def __getitem__(self, key):
            return event_row_data[key]

    with patch("scripts.runtime.return_router.verify_job_return", return_value=fake_verification):
        result = handle_merged_pr(FakeEventRow())

    print(f"  return_router result : {result['status']}")
    print(f"  verification verdict : {fake_verification['verdict']}")
    print(f"  job routed to awaiting_review")
    print(f"  Node truth remains unchanged in the graph.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("  GDDP DRY RUN — Phase 2 vertical slice")
    print("=" * 60)

    con = connect()
    cur = con.cursor()
    dry_job_ids = "SELECT job_id FROM jobs WHERE event_id LIKE 'evt_dry_%'"
    for table in (
        "queue_records",
        "results",
        "artifact_verifications",
        "executor_sessions",
    ):
        cur.execute(f"DELETE FROM {table} WHERE job_id IN ({dry_job_ids})")
    cur.execute("DELETE FROM jobs WHERE event_id LIKE 'evt_dry_%'")
    cur.execute("DELETE FROM events WHERE event_id LIKE 'evt_dry_%'")


    event_id = inject_event(cur)
    classify_and_scope(cur, event_id)
    job_id   = create_job(cur, event_id)
    enqueue(cur, job_id)
    simulate_result(cur, job_id)
    simulate_merged_pr(cur, job_id)

    con.commit()
    con.close()

    print("\n" + "=" * 60)
    print("  DRY RUN COMPLETE")
    print("=" * 60)
    print(f"\n  DB    : {DB_PATH}")
    print(f"  Jobs  : {RUNTIME_ROOT / 'jobs'}")
    print()


if __name__ == "__main__":
    main()
