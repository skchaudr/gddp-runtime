---
description: Full end-to-end loop tick (Heartbeat check → Executors → Graph work → Triage → Subagents)
argument-hint: "<project>"
---

Execute a complete GDDP loop tick for project "${1:-myapi-part1}" starting from armed heartbeat disclosure.

### Phase 1: Armed Heartbeat & Disclose
- Check `gddp-heartbeat status` and verify timer execution.
- Disclose armed state and confirm queue listener readiness.

### Phase 2: Executor Updates
- Query active jobs, running PIDs, and spool state using `medic`.

### Phase 3: Graph Work & Frontier
- Evaluate graph status for project "${1:-myapi-part1}".
- Dispatch ready frontier nodes via `foreman` with watchers armed.

### Phase 4: State Triage & Multi-Agent Dispatch
- Run `sweep` for pending evaluations and `steward` for provisional node triage.
- Run `janitor` for repo hygiene and `bridgekeeper` for VM parity.

### Phase 5: Handoff & Summary
- Report executed jobs, review-ready nodes, and next action items for Sab.
