<instruction>You are an expert software engineer. You are working on a WIP branch. Please run `git status` and `git diff` to understand the changes and the current state of the code. Analyze the workspace context and complete the mission brief.</instruction>
<workspace_context>
<artifacts>
--- CURRENT TASK CHECKLIST ---
# Task: Big Pi Baseline Audit

- [x] Identify active services and canonical runtime entrypoints.
- [x] Document active paths and required env vars (`OPCLAW_ROOT`).
- [x] Extract deploy/update steps actually being used.
- [x] Determine validation commands.
- [x] Check for branch divergence, stale state, or path ambiguity.
- [x] Produce `audit_report.md` with baseline data and source-of-truth recommendation.

--- IMPLEMENTATION PLAN ---
# Runner.py Fixes

## Goal Description
Fix the `runner.py` docstring to reflect accurate module invocation on Big Pi and fix the hardcoded event selection so the heartbeat only pulls events for the target `project_id`. This prevents the heartbeat from incorrectly processing events for other projects.

## Proposed Changes

### `scripts/runtime/heartbeat/runner.py`

#### [MODIFY] [runner.py](file:///home/saboor/work/repos/gddp-runtime/scripts/runtime/heartbeat/runner.py)
Update the docstring usage instructions:
```diff
-Usage:
-    python3 scripts/runtime/heartbeat/runner.py \
+Usage (from Big Pi):
+    cd ~/opclaw/scripts
+    python3 -m runtime.heartbeat.runner \
```

Update the event selection behavior to filter by `project_id`:
```diff
-    cur.execute("SELECT * FROM events WHERE status = 'received'")
-    events = cur.fetchall()
+    cur.execute(
+        "SELECT * FROM events WHERE status = 'received' AND project_id = ?",
+        (project_id,)
+    )
+    events = cur.fetchall()
```

## Verification Plan

### Automated Tests
- Run the existing `test_parallel_dispatch.py` locally to ensure filtering by `project_id` doesn't break tests (the test inserts events with `project_id='parallel-test'` and queries for them, so it should pass seamlessly).
  `pytest -q scripts/runtime/heartbeat/test_parallel_dispatch.py`
</artifacts>
</workspace_context>
<mission_brief>[Describe your task here...]</mission_brief>