---
description: Query active executor jobs, spool state, and system health via Medic agent
---

Dispatch Medic agent to collect live executor and infrastructure updates.
1. Run subagent with agent `medic` to check:
   - Heartbeat timer liveness and logs
   - Active/stuck jobs in `db/queue.db` (>30m running/dispatched)
   - Local subprocess spool zombie PIDs and orphaned worktrees
   - Queue database backup freshness
2. Report executor status summary and flagged infrastructure risks.
