---
description: "Multi-agent orchestration loop: dispatch Medic, Foreman, Steward, Sweep, Janitor, Bridgekeeper"
argument-hint: "<project>"
---

Orchestrate full GDDP agent workflow for project "${1:-myapi-part1}".
1. **Executor Health:** Run `medic` agent for job spool/heartbeat status.
2. **Graph Frontier:** Run `foreman` agent to dispatch ready nodes in project "${1:-myapi-part1}".
3. **Evaluation:** Run `sweep` agent for unverified job receipts.
4. **Triage:** Run `steward` agent to compile the human review queue.
5. **Hygiene & Sync:** Run `janitor` agent to commit provisional flips and `bridgekeeper` for parity.
6. Synthesize multi-agent findings into a single executive loop tick summary.
