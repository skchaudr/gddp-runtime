---
description: Dispatch worker in background after join gate check
subagent: delegate
---

Prepare background execution for ready GDDP node "$1" in project "$2".
1. Check `jobs.status` — if active job exists for node $1, do NOT double-dispatch.
2. Formulate worker prompt with node constraints and acceptance criteria.
3. Launch detached execution via `subagent({ workflowScript: ..., async: true })`.
4. Return job ID and live status handle immediately to main session.
