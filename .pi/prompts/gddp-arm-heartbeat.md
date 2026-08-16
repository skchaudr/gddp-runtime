---
description: Disclose and verify armed heartbeat state before starting loop ticks
argument-hint: "[project]"
---

Verify and disclose heartbeat arming for project "${1:-myapi-part1}".
1. Run `deploy/mini-heartbeat/bin/arm.sh` (or verify via `gddp-heartbeat status`).
2. Confirm timer interval, log tail (`~/Library/Logs/gddp-heartbeat.log`), and active environment variables.
3. Record heartbeat armed timestamp in `/tmp/gddp-loop-status.log`.
4. Report heartbeat readiness and trigger the initial graph loop tick.
