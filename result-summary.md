# Result Summary: Heartbeat & Intake Crash Recovery

Automated crash-recovery evidence is green. The live intake restart criterion remains pending an operator-owned launchd drill.

## Acceptance Status

1. **`id: stale-claim-recovery-tested`**
   - **Status:** Met & Tested.
   - **Details:** Added `test_stale_claim_recovery_processed` in `scripts/runtime/heartbeat/test_crash_recovery.py`. It proves that when an event is stuck in the `'claimed'` status past the 30-minute stale cutoff, subsequent heartbeat runs successfully adopt, re-claim, and process the event without data loss or operator intervention.

2. **`id: intake-restart-proven`**
   - **Status:** Pending operator drill.
   - **Details:** Fixed `arm.sh` to set `RunAtLoad=true` and `KeepAlive=true` with a plist-aware helper, and added a focused automated test. No launchd or process operations were performed. `decision.md` lists the exact evidence the operator drill must capture.

3. **`id: no-double-processing`**
   - **Status:** Met & Tested.
   - **Details:** Added `test_no_double_processing` in `scripts/runtime/heartbeat/test_crash_recovery.py`. Both runners are synchronized immediately before the atomic claim `UPDATE`, proving that exactly one creates a job while the other safely skips it.

4. **`id: crash-drill-runbook`**
   - **Status:** Met & Documented.
   - **Details:** Created a reproducible crash drill runbook in `decision.md` to guide engineers through performing live validation of process recovery before overnight execution windows.

5. **`id: suite-green`**
   - **Status:** Met.
   - **Details:** `python3 -m pytest -q` passes: 269 tests, no regressions.

## Required Artifacts Included in the PR

- `decision.md` — Rationale, crash drill runbook, and pending live-evidence requirements.
- `result-summary.md` — This file.
- `graph-update.yaml` — Simple yaml indicating human-owned graph truth.
- `patch.diff` — The full, clean code diff.
