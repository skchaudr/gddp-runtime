# Postmortem — Canary Retry Review Goose Chase (2026-07-12)

Scope: the plan-review and mid-run confusion around retry PR #102 (canary node, `job_20260711T17104259`), spanning the VM review session and the Mac Mini execution loop.

## What happened (timeline)

1. Mini planner produced an execution plan for merging retry PR #102, noting the PR touched three pre-existing artifact files "in conflict with the node's narrow file-scope constraint."
2. VM reviewer (Claude) verified cheap local claims (handoff freshness, jules.yml, git state) — and misread all three as "stale" because the plan's premises described the **Mini's** checkout, not the VM's. Machine was never named in the plan.
3. VM reviewer promoted the unverified "scope violation" claim to fact, then built multi-turn analysis on it: exemption lines, evaluator control gaps, cleanup contingencies. Neither handoff 032 nor 033 documented any scope violation; nobody had quoted the constraint.
4. Merge proceeded. The signed merged-PR webhook hit pi-big (200) — which **correctly ignored it** (no matching job; canary is local-only to the Mini). The Mini's own public webhook endpoint returned 502 (stale tunnel).
5. Mini agent, given topology context, confirmed: canary job exists only in the Mini's local queue; pi-big was 5 commits behind without return-path wiring. Chose signed GitHub redelivery via temporary Cloudflare tunnel over synthesizing an intake event.
6. Constraint finally quoted verbatim: **"Only create or modify scripts/echo.py and docs/echo-usage.md."** The scope violation was real in letter — but the three violated files are the artifact-gate paperwork the executor is *required* to write.

## Root causes

- **No topology map.** `droid-wiki/deployment.md` describes a single-machine (Big Pi) world; `docs/host-roles.md` describes the retired OpenClaw topology (2026-03-21, wrong hostnames). No document mapped machines → queues → webhooks → auth. Every agent reconstructed (or missed) topology per session.
- **Plans don't name their machine.** Worktree-state claims are machine-relative; reviewers on other hosts falsify them incorrectly.
- **Claim laundering.** The reviewer treated a claim embedded in another agent's plan as evidence, amplified it, and flagged the original author for under-handling the very claim it originated. Primary evidence (the constraint text) was one SSH away the whole time — and the VM had no SSH/gh auth to reach it.
- **Constraint template contradicts the artifact gate.** The whitelist ("Only create or modify …") omits the receipt artifacts the gate obligates the executor to write. Compliant executors are structurally forced to violate the letter of their constraints.
- **Ephemeral tunnel left registered.** The Mini's public webhook endpoint 502'd because a temporary exposure was never torn down/reverted — undocumented, so it surfaced as a mid-run mystery.

## What worked

- pi-big's intake ignored a signed event with no matching job — job-matching discipline held.
- Doctrine held under pressure: verdict ≠ acceptance; no synthetic intake events during a live proof; scope evidence preserved rather than normalized.
- The Mini agent, once topology was supplied, made the right call (signed redelivery, not fabrication).

## Action items

| # | Item | Status |
|---|---|---|
| 1 | `TOPOLOGY.md` at repo root, human-owned; supersedes host-roles.md | drafted 2026-07-12, Sab to verify ❓ items |
| 2 | Plans must open with "Target machine: X" | convention, adopt next dispatch |
| 3 | Constraint template: carve out artifact-gate paths from file whitelists (or move receipts outside work tree) | backlog |
| 4 | Feed `changed_files` (already in DB, unused) into integrity lane 2 context so fresh-eyes review always sees the delta | backlog |
| 5 | Tunnel lifecycle: HMAC-reject test before exposure; teardown + webhook-URL revert is part of done | recorded in TOPOLOGY.md rule 4 |
| 6 | Reviewer rule: incoming claims are uncorroborated until primary-sourced; label them so in turn one | Claude memory saved |
| 7 | Mark/retire stale `docs/host-roles.md` | pending Sab (delete needs approval) |
