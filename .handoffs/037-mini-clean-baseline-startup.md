# 037 — Mini clean-baseline startup → loops + hardening

Instructions: this is an *orientation* handoff for a fresh Claude instance booting ON sab-mini. Written from the sab-dev VM, so every mini-side claim below is "per docs — verify on arrival" (you can check them; I couldn't).

------------------------------------------------ Agent Section START

Date: 2026-07-13
Worktree: /home/sab/gddp-runtime (sab-dev VM); you (reader) are on sab-mini @ ~/repos/gddp-runtime
Branch: main @ bf95c65 (VM clean, synced origin/main)

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

pi-big → sab-mini cutover is done: mini is production (launchd `com.gddp.intake` + `com.gddp.heartbeat`, Tailscale Funnel `https://sab-mini.tail02ac6f.ts.net/webhook` → `:5050`, 12 webhooks repointed, `gh` authed). pi-big is disarmed but still holds the `pass` store + automation key F0928E218506BB29, and mini currently resolves secrets by ssh-ing to pi-big — the fragility that caused the 2026-07-12 canary-scope incident. Sab's goal now: reach a clean baseline on mini, then open more loops/iterations and harden.

### Scope touched (One file per line, +/- for only what was changed)

+ .handoffs/037-mini-clean-baseline-startup.md — this orientation handoff
+ .remember/remember.md — session checkpoint

### Constrained areas touched (none / list + justification)

none — docs/checkpoint only, no code, no graph YAML, no live infra

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

main clean @ bf95c65, synced with origin/main from the VM. Mini may be behind — `git pull` first. No open working changes.

### Artifacts (Filepath - Description, 1 line max per artifact)

TOPOLOGY.md — sab-mini production map (hosts/paths/URLs); last verified 2026-07-12
docs/dispatch-checklist.md — intent/plan/execute gates; read before any dispatch
AGENTS.md — agent session workflow
deploy/mini-heartbeat/CUTOVER.md — pi-big→mini migration runbook (mostly complete)
docs/postmortem-canary-scope-2026-07-12.md — the ssh-secret-resolver incident
.handoffs/036-mini-production-docs-baseline.md — prior handoff (264 pytest baseline)

### Resume point (2-3 sentences max, anything more must be critically justifiable)

CLEAN-BASELINE FIRST MOVES (verify, don't assume): (1) `git pull`; (2) run pytest → confirm green against 264 baseline; (3) verify intake health 200 + funnel live + both launchd jobs loaded; (4) confirm queue `db/queue.db` and that canary `canary-retry-proof` (job_20260711T17104259) is still `awaiting_review`. THEN hardening: migrate `pass` + F0928E218506BB29 off pi-big to kill the ssh-to-pi-big secret resolver (top fragility). Sab-only: `accept_node` on the canary — acceptance is human, never agent. Only after baseline is green + Sab confirms should loop/iteration expansion begin. Read TOPOLOGY.md + docs/dispatch-checklist.md before dispatch; no agent-authored doc is Sab canon.

------------------------------------------------ Agent Section END
