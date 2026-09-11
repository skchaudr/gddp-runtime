# 132 — Cursor workspace and startup task packets

------------------------------------------------ Agent Section START

Date: 2026-09-10
Worktree: /home/sab-mini/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Sab requested two task packets and clarified hook-first sequencing for live execution. The draft ledger separates Cursor implementation/local checks from deployed-startup verification and an instrumented A0/A1/B0 scenario: two node identities, three attempts.

### Scope touched (One file per line, +/- for only what was changed)

+ docs/proposals/cursor-session-startup-packets.yaml
+ .handoffs/132-cursor-workspace-and-startup-task-packets.md

### Constrained areas touched (none / list + justification)

Planning artifacts only; runtime, service, graph, and job state retain their previous state.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

Started clean and synchronized at 1d335ab on main. Commit and push the packet ledger and this handoff together.

### Artifacts (Filepath - Description, 1 line max per artifact)

- docs/proposals/cursor-session-startup-packets.yaml — exactly two draft packets, explicit hook-readiness gate, actions/expected observations/results, and human-owned completion.
- deploy/mini-heartbeat/systemd/gddp-heartbeat.service — checked-in Linux startup invokes init_db.py; installed service equivalence remains a packet-2 check.
- Peer review via intercom session 01a0847d — applied explicit fixture isolation and rejected-token test; retained bounded schema-readiness checks as part of startup, with migration-algorithm repairs separated.

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Prepare hook integration alongside packet-1 local implementation and packet-2 read-only inspection. Live acceptance follows hook-readiness evidence and uses an isolated service instance through the deployed startup recipe; execution and graph placement remain for Sab to authorize.

------------------------------------------------ Agent Section END
