---
description: Assess graph frontier, node readiness, and dispatch work via Foreman agent
argument-hint: "<project>"
---

Dispatch Foreman agent to process graph work and frontier for project "${1:-myapi-part1}".
1. Run subagent with agent `foreman` to:
   - Check graph status and identify ready nodes (`~/bin/gddp node status`)
   - Dispatch ready nodes with node watchers armed
   - Triage failure classes (infra retry vs work failure report)
   - Reconcile index/node YAML status drift
2. Output dispatched job IDs, frontier changes, and any blocked nodes.
