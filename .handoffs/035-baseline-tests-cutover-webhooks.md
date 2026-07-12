# 035 — Baseline tests sprint + webhook repoint fix

Date: 2026-07-12
Worktree: /home/sab/gddp-runtime (sab-dev VM)
Branch: main @ f411a5a

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Agent-bus sprint merged 19 known-good tests (intake health/roundtrip, mini-heartbeat arm/smoke/render). Cutover was partially false: all 12 GitHub hooks still pointed at pi-big (inactive intake); repointed to sab-mini via JSON-body `gh api PATCH` — flat `-f url=` is a no-op. gddp-runtime hook ping now 200.

### Scope touched (One file per line, +/- for only what was changed)

+ scripts/test_intake_server.py
+ scripts/test_intake_webhook_roundtrip.py
+ deploy/mini-heartbeat/test_arm_refuse.py
+ deploy/mini-heartbeat/test_smoke_dry.py
+ deploy/mini-heartbeat/test_render_plist.py
+ .handoffs/035-baseline-tests-cutover-webhooks.md

### Constrained areas touched (none / list + justification)

none

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

main clean, pushed f411a5a. 264 pytest pass on sab-dev. sab-mini intake armed, funnel 200; pi-big disarmed. Webhooks live on mini URL (verified ping 200 on gddp-runtime).

### Artifacts (Filepath - Description, 1 line max per artifact)

.handoffs/035-baseline-tests-cutover-webhooks.md — this handoff
agent-bus ids 292–295 — sprint coordination (grok-lead, grok-a, grok-b)

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Sab: ratify draft TOPOLOGY (remove sab-dev-2 from GDDP map; update Transition → mini production). Phase 7 live proof on a real repo event. `accept_node` on canary-retry-proof when ready. Fix CUTOVER.md Phase 6 example to use JSON PATCH for hooks.

------------------------------------------------ Agent Section END