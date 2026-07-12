# 036 — Mini production live, topology + dispatch docs, test baseline

Date: 2026-07-12
Worktree: /home/sab/gddp-runtime (sab-dev VM); production on sab-mini
Branch: main @ e843015

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

pi-big → sab-mini cutover executed: pi-big disarmed, mini launchd intake+heartbeat armed, Tailscale Funnel on `:5050`, all 12 webhooks on `https://sab-mini.tail02ac6f.ts.net/webhook` (JSON PATCH required). Agent-bus sprint added 19 known-good tests (264 total pytest). TOPOLOGY rewritten as runtime map; `docs/dispatch-checklist.md` is intent/plan/execute gates with cause-and-effect. Canary job `job_20260711T17104259` still `awaiting_review`.

### Scope touched (One file per line, +/- for only what was changed)

+ TOPOLOGY.md — runtime hosts/paths only (no agent-edit gate)
+ docs/dispatch-checklist.md — intent, planning, execution checklists
+ docs/postmortem-canary-scope-2026-07-12.md — recovery items marked done
+ deploy/mini-heartbeat/bin/common.sh — plist XML/sed escape fix
+ deploy/mini-heartbeat/test_*.py — render, arm refuse, smoke dry
+ scripts/test_intake_server.py, test_intake_webhook_roundtrip.py
+ .handoffs/035-*, 036-*

### Constrained areas touched (none / list + justification)

none

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

main clean, synced with origin/main. mini @ pull needed for e843015+. Production verified: intake health ok, gddp-runtime hook URL is sab-mini. pi-big intake inactive.

### Artifacts (Filepath - Description, 1 line max per artifact)

TOPOLOGY.md — sab-mini production map
docs/dispatch-checklist.md — live dispatch gates (read before next run)
.handoffs/035-baseline-tests-cutover-webhooks.md — webhook repoint incident
deploy/mini-heartbeat/CUTOVER.md — migration runbook (mostly complete)

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Sab: `accept_node` on `canary-retry-proof` when ready. Optional: live proof on one real GitHub event (delivery 200 → `events` row → heartbeat). Migrate pi-big `pass` to mini when cutting ssh resolver dependency. Next agent: read `TOPOLOGY.md` + `docs/dispatch-checklist.md` before dispatch; no agent-authored doc stamped as Sab canon.

------------------------------------------------ Agent Section END