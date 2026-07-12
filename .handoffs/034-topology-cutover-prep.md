# 034 — Topology target+transition + mini cutover prep

------------------------------------------------ Agent Section START

Date: 2026-07-12 (night shift)
Worktree: /home/sab/gddp-runtime (sab-dev VM)
Branch: main @ 6c57942

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Canary retry proof completed earlier (9b97388); this session landed migration-aware topology and cutover hardening so the next day does not rediscover split-brain by archaeology. TOPOLOGY.md now has Target + Transition sections; CUTOVER.md is the ordered pi-big → sab-mini checklist; intake fails closed without webhook secret; smoke.sh checks secret resolver + HMAC 401.

### Scope touched (One file per line, +/- for only what was changed)

+ TOPOLOGY.md — target topology, transition state 2026-07-12, agent preflight rules
+ deploy/mini-heartbeat/CUTOVER.md — phased cutover checklist (new)
+ deploy/mini-heartbeat/README.md — points to TOPOLOGY + CUTOVER
+ deploy/mini-heartbeat/bin/smoke.sh — webhook secret len + /health + HMAC 401
+ deploy/mini-heartbeat/env/gddp.env.example — transition ssh resolver comment
+ scripts/intake_server.py — fail-closed startup; /health 503 when secret missing
+ scripts/test_intake_server.py — startup check tests
+ docs/postmortem-canary-scope-2026-07-12.md — mark 5b/5c done
+ docs/host-roles.md — superseded banner
+ droid-wiki/deployment.md — defer to TOPOLOGY.md

### Constrained areas touched (none / list + justification)

none — docs + deploy kit + intake safety only; pi-big still production until Sab runs CUTOVER phases 4–6.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

main clean, pushed to origin/main (6c57942). 252 tests pass via `.venv/bin/python -m pytest -q scripts/`. VM cannot SSH to sab-mini or pi-big in BatchMode (no keys from sab-dev).

### Artifacts (Filepath - Description, 1 line max per artifact)

TOPOLOGY.md — human-owned machine map (Target + Transition)
deploy/mini-heartbeat/CUTOVER.md — executable migration phases 0–7 + rollback

### Resume point (2-3 sentences max, anything more must be critically justifiable)

On sab-mini: `git pull`, confirm ❓ paths in TOPOLOGY.md, edit `deploy/mini-heartbeat/env/gddp.env` (transition ssh resolver if pass not migrated), `install-dormant.sh` + `smoke.sh`. Before arm: Phase 2 stable public URL on mini (not trycloudflare PID). Sab confirms TOPOLOGY ❓ items then run CUTOVER phases 4–6 when ready to decommission pi-big.

------------------------------------------------ Agent Section END