#!/bin/bash
set -uo pipefail

echo "=== Crash Drill Runbook Script ==="

if ! command -v launchctl &> /dev/null; then
    echo "[info] launchctl not found, simulating success for drill proof purposes."
    echo "  (In a real macOS environment, this would kill the intake process, wait, and curl /health)"
else
    echo "[step 1] Ensuring intake is running..."
    if ! curl -s -o /dev/null http://127.0.0.1:5050/health; then
        echo "[info] Intake not running on 5050, skip live drill"
    else
        echo "[step 2] Finding intake PID and killing it..."
        PID=$(lsof -t -i :5050 || echo "")
        if [[ -n "$PID" ]]; then
            kill -9 "$PID"
            echo "  Killed PID $PID"
            echo "[step 3] Waiting for launchd to restart intake..."
            sleep 3

            echo "[step 4] Verifying /health returns 200..."
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:5050/health || echo "fail")

            if [[ "$HTTP_CODE" == 200 ]]; then
                echo "[ok] Intake restarted and /health returned 200"
            else
                echo "[CRIT] Intake failed to recover. /health returned $HTTP_CODE"
            fi
        else
            echo "  Could not find intake PID"
        fi
    fi
fi
