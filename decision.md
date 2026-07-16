# Implementation Decision: Heartbeat & Intake Crash Recovery Proofs

Date: 2026-07-16
Node: heartbeat-crash-recovery
PR Job ID: job_20260716T102119061b92648235b8

---

## Decision & Rationale

To ensure complete overnight readiness, we must prove that both the **heartbeat runner** and **webhook intake server** can survive crashes gracefully without losing events, skipping processing, or causing duplicate (double-processed) job dispatches.

This is achieved via two core mechanisms:
1. **Runner-Level Atomic & Stale Claiming:** The database `UPDATE` statement in `scripts/runtime/heartbeat/runner.py` is fully atomic. A single event is only ever claimed by one runner run (and exactly one thread/process) because of the combined `UPDATE` filter query checking for `status = 'received'`. Furthermore, if a runner crashes *after* claiming an event but *before* planning or finishing dispatch, that event will sit in the `'claimed'` status. The runner's subsequent runs automatically reclaim stale claims older than 30 minutes.
2. **Launchd KeepAlive Supervision (macOS sab-mini):** `arm.sh` now uses Python's plist parser to set `RunAtLoad` and `KeepAlive` on the installed intake plist. A focused test verifies those booleans. The actual restart behavior still requires the operator drill below; this change does not claim that live evidence.

To make these properties provable, we have:
- Written explicit concurrency and temporal tests under `scripts/runtime/heartbeat/test_crash_recovery.py` to assert atomic claiming and stale claim recovery.
- Replaced the broken line-oriented plist mutation with a plist-aware helper and added a focused automated test.
- Documented the operator-owned crash drill below. No live transcript is included because no launchd or process operations were performed in this change.

---

## Crash Drill Runbook (id: crash-drill-runbook)

This drill must be performed and verified on the active control plane host (e.g., `sab-mini` or the testing target) before any unattended overnight runs window.

### Step 1: Initialize Queue & State
Verify that the SQLite queue is initialized and clean.
```bash
cd ~/repos/gddp-runtime
# Ensure database and tables exist
.venv/bin/python scripts/init_db.py
```

### Step 2: Arm mini-heartbeat
Arm the launchd-supervised services with the explicit arming flag.
```bash
MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh

# Confirm the installed intake plist is armed before killing anything.
/usr/bin/plutil -extract RunAtLoad raw ~/Library/LaunchAgents/com.gddp.intake.plist
/usr/bin/plutil -extract KeepAlive raw ~/Library/LaunchAgents/com.gddp.intake.plist
```

### Step 3: Verify Running Services
Confirm both services are loaded, running, and healthy.
```bash
# Check launchd listing
launchctl list | grep com.gddp

# Check local health endpoint
curl -s -i http://127.0.0.1:5050/health
```
*Expected health output:* HTTP/1.1 200 OK with `{"status":"ok", "webhook_verification": true}`.

### Step 4: Run the Intake Crash Test (Kill & Resume)
Kill the running intake server process and verify launchd restarts it.
```bash
# Read the launchd-owned PID
INTAKE_PID=$(launchctl print "gui/$(id -u)/com.gddp.intake" | awk '/pid =/{print $3; exit}')
echo "Active Intake PID: ${INTAKE_PID}"

# Force kill the process
kill -9 "${INTAKE_PID}"
echo "Intake process killed. Waiting for launchd KeepAlive..."

# Wait 2 seconds for launchd cycle
sleep 2

# Verify a new process was spawned with a new PID
NEW_PID=$(launchctl print "gui/$(id -u)/com.gddp.intake" | awk '/pid =/{print $3; exit}')
echo "New Intake PID: ${NEW_PID}"
test -n "${NEW_PID}" && test "${NEW_PID}" != "${INTAKE_PID}"

# Confirm health endpoint returns 200 OK again
curl -s -i http://127.0.0.1:5050/health
```
*Expected outcome:* The `/health` endpoint returns `200 OK` without any operator intervention.

---

## Pending Evidence: Intake Restart Proof (id: intake-restart-proven)

**Status: pending operator drill.** The automated test proves that `arm.sh` writes `RunAtLoad=true` and `KeepAlive=true` into the installed intake plist. It does not prove launchd restarted a killed process. An operator must run the drill above on the active control plane and capture:

1. The original launchd-owned PID.
2. The kill command and a different replacement PID.
3. A post-restart `/health` response with HTTP 200.

Until that evidence exists, `intake-restart-proven` is not met and graph truth must not change.

---

## Automated Concurrency & Temporal Verification Tests

To verify these safety properties programmatically and continuously, we developed `scripts/runtime/heartbeat/test_crash_recovery.py`.

1. **Stale Claim Recovery Test (`test_stale_claim_recovery_processed`):**
   - **Procedure:** Inserts an event in `'claimed'` status with `claimed_at` timestamp set to 45 minutes ago (older than the 30-minute cutoff), along with an event set to 15 minutes ago (newer than the cutoff). It then triggers the heartbeat planner `_plan_dispatches()`.
   - **Verification:** Asserts that the stale event is successfully selected, updated, and has a corresponding job created (status is set to `'classified'`), while the fresh event is completely ignored.
2. **Atomic Concurrency Test (`test_no_double_processing`):**
   - **Procedure:** Inserts a single `'received'` event into a SQLite file-based queue. It then spawns two concurrent threads using independent connections. A test-only connection proxy blocks both threads immediately before the claim `UPDATE`, guaranteeing both already selected the same event before either claim executes.
   - **Verification:** Asserts that exactly one of the threads succeeds in claiming and planning a job, while the other thread gets `rowcount = 0` on its update statement, logs a skip, and exits cleanly. The total job count in the database is verified to be exactly 1.
