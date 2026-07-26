## Decision

1. I've added a robust test suite `scripts/runtime/heartbeat/test_crash_recovery.py` to test the stale claim recovery and the concurrent execution logic (atomic claim) logic in `heartbeat`.
2. I've updated the config-of-record `deploy/mini-heartbeat/launchd/com.gddp.intake.plist` by changing `KeepAlive` from `<false/>` to `<true/>` so that launchd will restart the `intake` server when it crashes mid-run.
3. I've verified the launchd config by checking the KeepAlive key in `com.gddp.intake.plist` using `deploy/mini-heartbeat/test_launchd_recovery.py`.

## Crash Drill Runbook

To manually verify the crash recovery of the `intake` server on the target macOS system:

1. **Verify Initial State**: Check that the `intake` server is active and responding:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5050/health
   # Expected output: 200
   ```

2. **Simulate Crash**: Find the PID of the `intake` server and kill it abruptly (simulating a crash):
   ```bash
   PID=$(lsof -t -i :5050)
   kill -9 $PID
   ```

3. **Verify Recovery**: Wait a few seconds for `launchd` to recognize the process died and automatically restart it due to the `KeepAlive=true` property:
   ```bash
   sleep 3
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5050/health
   # Expected output: 200
   ```

This drill proves that if the intake process is killed mid-run, it is cleanly restarted by launchd without operator action.

The automated tests in `scripts/runtime/heartbeat/test_crash_recovery.py` also prove that `heartbeat` itself recovers safely from crashes during dispatch because the SQL UPDATE claim is strictly atomic (preventing double processing) and allows claiming events after a 30-minute stale window.
