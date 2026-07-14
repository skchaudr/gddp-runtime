# 038 — Mini orientation complete → evaluator harness path

Instructions: written ON sab-mini at the end of the orientation/hardening session that 037 set up. Every claim below was verified live on this host during the session — but re-verify with `baseline.sh` on arrival; that's what it's for.

------------------------------------------------ Agent Section START

Date: 2026-07-14
Worktree: /Users/sab-mini/repos/gddp-runtime (sab-mini, production host)
Branch: main @ d716aa1 (clean, synced origin/main)

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

The mini is now self-contained production: secrets (`pass` store + GPG F0928E218506BB29) migrated off pi-big 2026-07-13, hash-verified, ssh resolver dead — with one platform landmine found and fixed (Homebrew `pass` shells out to `brew --prefix gnu-getopt` at runtime and hangs forever under launchd; production env cmds now call `gpg --batch --quiet --decrypt` directly, see `deploy/mini-heartbeat/env/gddp.env` comment). Baseline is green by script, not claim: `deploy/mini-heartbeat/bin/baseline.sh` = 19 ok / 0 warn / 0 crit (tiered exit 0/1/2 = OK/DEGRADED/BROKEN; WARN = fragile e.g. git dirty, CRIT = inoperable/unsafe e.g. HMAC round-trip fails). Canary `canary-retry-proof` (job_20260711T17104259) is still `awaiting_review` — its retry-loop proof is complete (two results rows, 07-11T17:35Z / 07-12T07:16Z); the exit is Sab-only via `scripts/node_status.py`, and no agent recommends which outcome.

### Scope touched (One file per line, +/- for only what was changed)

+ scripts/node_status.py — human review-gate CLI: list/show/set across all 11 canon queue states, audit row per change (5ca1f9e)
+ deploy/mini-heartbeat/bin/baseline.sh — tiered production verifier, 8 sections: git sync, secret locality+resolution, launchd/health/funnel, HMAC 401+200 round-trip, queue.db integrity+writability, heartbeat tick, gh auth, pi + verifier extensions (168bded, 32b9c7d)
~ TOPOLOGY.md — secrets rows now mini-local gpg-direct; pi-big = offline backup only (4bc6f1d)
~ .gitignore — graphify-out/ untracked (hook regenerates every commit → perpetual dirt) (4c953e0)
~ droid-wiki/lore.md — new era: retry proof, incident, cutover, tooling (c63f86c)
~ droid-wiki/deployment.md — Production: sab-mini section; Big Pi content marked Archive (c63f86c)
~ droid-wiki/systems/intake-server.md — launchd/funnel; fixed stale claim: missing secret = exit 1, not warn-and-continue (c63f86c)
~ droid-wiki/reference/configuration.md — same exit-1 fix; added GDDP_INTAKE_INSECURE row (c63f86c)
~ droid-wiki/features/retry-loop.md — "Proven live" section with canary receipts (c63f86c)
~ deploy/mini-heartbeat/env/gddp.env — LOCAL ONLY, not committed: gpg-direct secret cmds
+ .handoffs/038-mini-orientation-baseline-evaluator-path.md — this handoff

### Constrained areas touched (none / list + justification)

Production launchd plists re-rendered + re-armed during secrets migration (required to repoint resolver cmds; ~10 min intake downtime 03:28–03:38 PT Jul 13, disclosed). No graph YAML, no gddp-config writes, no node acceptance.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

main clean @ d716aa1, 0/0 vs origin/main, all session work pushed. Session commits: 4bc6f1d, 5ca1f9e, 168bded, 4c953e0, 32b9c7d, c63f86c.

### Artifacts (Filepath - Description, 1 line max per artifact)

deploy/mini-heartbeat/bin/baseline.sh — run this first, always; green = exit 0
scripts/node_status.py — Sab's canary decision tool (`set job_20260711T17104259 <state> --reason "..."`)
docs/postmortem-canary-scope-2026-07-12.md — the incident behind the git-pull-only + secret-locality rules
droid-wiki/lore.md — narrative now current through Jul 13
.handoffs/037-mini-clean-baseline-startup.md — prior handoff (what this session executed)
deploy/mini-heartbeat/env/gddp.env — local secrets config; the pass-under-launchd comment is load-bearing

### Resume point (2-3 sentences max, anything more must be critically justifiable)

NEXT PATH — the evaluator harness, and specifically the hard half of it. The prior Factory droid session ended on the right framing: making the evaluator *safer* is the easy part (it already runs as a subprocess the return router can survive, read-only tools, timeouts, guard extension — baseline.sh proves it's *alive*); the hard part is making it more *capable while staying trusted* — an evaluator whose pass means pass and whose non-pass means something concrete, because overnight runs put it in the human's seat for hours and "not possible just cause we say so." Concrete first moves: (1) read the harness end-to-end (`pi_runner.py`, `gddp_verifier.ts`, `gddp_verifier_guard.ts`, the bridge, `retry_budget.py`) and map what the evaluator can actually observe vs what it claims to judge; (2) build correctness evidence, not liveness evidence — e.g. a small graded fixture set of known-verdict nodes (clear pass, clear fail-with-evidence, ambiguous) replayed through the evaluator so its judgment is measured before it's trusted overnight; (3) only then widen loops/iterations. Sab-only pending: canary decision via node_status.py. Do not start the evaluator work unprompted — scope it with Sab first.

------------------------------------------------ Agent Section END
