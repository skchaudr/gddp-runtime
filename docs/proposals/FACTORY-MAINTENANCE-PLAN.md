# Factory Maintenance — around-the-clock subagent plan

Status: plan for handoff. Author: Pi + Sab direction, 2026-08-13.
Pairs with FLEET-VISION.md: fleet is the *window*; this is the *staff*.

## Vision

The factory never sleeps. Maintenance is continuous, distributed, and boring.
Not one-shot subagent runs — standing roles on recurring schedules, each with
a bounded beat, cheap tools, and a written report at the end of every shift.
Sab wakes up to a short queue of decisions, not a pile of archaeology.

Design rule: maintenance agents **report and tidy**; they never move graph
truth. Node acceptance stays human, provisional writes stay the runtime's,
dispatch decisions stay the loop's.

## The standing roles

| # | Role | Beat | Cadence | Writes |
|---|------|------|---------|--------|
| 1 | **Steward** | Review queue triage: every provisional node's verdict + lane summary + receipt path, one page, ready for c/r/d | every 2h + on evaluation-complete | `reports/review-queue.md` (config repo, uncommitted) |
| 2 | **Janitor** | Repo hygiene: commit runtime-written provisional flips, classify untracked noise, keep handoffs current, graphify freshness, branch sync check | every 4h | commits to config/runtime (hygiene-only, co-authored) |
| 3 | **Bridgekeeper** | Evidence parity mini ↔ khoj-38: receipts, job/result rows, verdict bindings both ways | every 6h | verification dirs + queue.db imports (idempotent) |
| 4 | **Sweep** | State-driven evaluation: nodes with landed evidence but no verdict → run the evaluator lane; flag eval gaps | every 4h | verdict receipts via the sanctioned evaluator path |
| 5 | **Medic** | Loop health: heartbeat ticking, intake up, spool zombies, orphan worktrees, stale `active` executor rows, db backup rotation, watchdog signal rollup | every 1h | `reports/medic.md` + daily-memory alert lines only when firing |

Every role ends its run with ≤3 lines appended to daily memory: what it saw,
what it did, what needs Sab. That file is the morning newspaper.

## Runtime model

Each role is a **project-local pi subagent**: an agent definition at
`.pi/agents/<role>.md` (pi-subagents project scope — tools, model, and
description in frontmatter, per-agent overrides in `.pi/settings.json` under
`subagents.agentOverrides`). The definitions live in the repos they maintain
(gddp-runtime hosts Medic and Janitor; gddp-config hosts Steward, Sweep,
Bridgekeeper — or one home repo for all five, decide at build time), so the
staff is versioned with the factory, code-reviewed like any other change, and
wins over any global agent of the same name.

Scheduling, two options per role:

- **A. launchd + bounded pi packet** (recommended default). Exact same pattern
  as the proven mini-heartbeat kit: a timer fires `pi -p` invoking the role's
  subagent chain, run dies at completion. Survives reboots, zero persistent
  process, logs to `~/Library/Logs/`. Roles 1–5 all fit.
- **B. persistent fleet-boss session** hosting recurring subagent schedules
  (native `schedule.create`). Nicer steering, but the schedule dies with the
  session. Adopt when fleet (FLEET-VISION) exists as the always-on surface and
  can host the boss.

Start A, migrate to B when fleet lands. Either way each role is a **chain**:
brief → scoped worker → verifier pass → report write. No role is a single
free-running prompt.

## Tool scoping (safety)

- All roles: read tools, shell with a denylist (no `rm -rf`, no force-push,
  no graph yaml edits, no `gddp node browse` mutations).
- Janitor alone gets commit rights, restricted to hygiene diffs it can
  describe in one line; anything ambiguous goes to the report, not the tree.
- No role touches `status:` in node yamls or project indexes. Ever.
- Budget: cheap local/fast model for sweeps (Medic, Janitor); a stronger
  model only where judgment is real (Steward summaries, Sweep verdict review).

## Build order (swarm-ready milestones, binary-verified)

- **M1 — Medic** (smallest, pure read + report). Verify: run it now; its
  report correctly names the armed heartbeat state and tonight's residue
  (flea-market worktrees if any, spool entries).
- **M2 — Steward.** Verify: report lists exactly the current 44 provisional
  nodes with correct verdicts and receipt paths.
- **M3 — Janitor.** Verify: a run with a planted provisional write commits
  exactly that diff and nothing else.
- **M4 — Bridgekeeper.** Verify: remove one bridged receipt locally; next run
  restores it byte-identical.
- **M5 — Sweep.** Verify: a node with evidence and no verdict gets evaluated;
  a node with a verdict is never re-run.

## What this is not

Not dispatch. Not node authoring. Not acceptance. The loop decides what work
runs; the factory staff keeps the floors clean, the ledgers synced, and the
morning report short.
