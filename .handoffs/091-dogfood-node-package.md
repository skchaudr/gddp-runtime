# 091 — Dogfood run node package (UNAPPROVED BACKLOG — do not import)

**Date:** 2026-08-10. **Status:** SUPERSEDED as a dispatch package by co-advisor
review (Codex, 2026-08-10): 19 substantive runtime repairs mix path validation
with repairing the path — a failure would be ambiguous between executor,
harness, and spec. Preserved verbatim as the follow-on backlog; becomes a
dispatch candidate only after the report/test/edit-shaped dogfood run proves
evaluator visibility end-to-end. See 092 for the live package. **Graph:** `gddp-dogfood` (new), repo `skchaudr/gddp-runtime`.
**Executor:** `local_subprocess` one-shot → pi `xai/grok-4.5` (pinned in VM
gddp.env). **Evaluator:** post-hoc pi harness, DeepSeek semantic lane (key loaded).
**Doctrine:** auto-advance, up to 3 retries per node, each retry a fresh one-shot
carrying previous findings. Every node: one commit on a work branch, binary
criteria, suite green.

Tranche 1 = nodes 01–05 (live proof at small scale). Tranches 2–4 release as
tranche 1 lands clean.

## Tranche 1 — smoke + safest (01–05)

- **node-01-factory-noise-gitignore** — Add `.factory/` (and peers) to
  gddp-runtime `.gitignore`. Criteria: file lists the entry; `git status` clean
  with `.factory/` present; suite green.
- **node-02-worktree-skip-tests** — Fix the 15 cross-repo tests that skip from a
  git worktree (`parents[4]` path-depth assumption in test_provisional_status.py
  and peers). Criteria: suite run from a worktree reports 0 skips of that set;
  suite green from root checkout.
- **node-03-scan-break** (BM-021) — A deferred/refused event must not `break`
  the scan of later events. Criteria: regression test with two queued events
  shows the second is processed; suite green.
- **node-04-stale-node-lock** (BM-022) — A node lock held with no live executor
  is released after a bounded stale window. Criteria: regression test proves
  lock release; release is logged; suite green.
- **node-05-lease-visibility** (BM-044) — The 30-minute event lease is visible
  in `jobs_status.py` output. Criteria: status output shows lease expiry for a
  claimed event; suite green.

## Tranche 2 — event-flow bugs (06–10)

- **node-06-silent-skip** (BM-010) — runtime must never silently skip a node;
  every skip gets a durable, visible disposition. Criteria: induced skip
  produces a recorded reason queryable via jobs_status; suite green.
- **node-07-defer-loop** (BM-016) — an event that re-queues forever gets a
  bounded defer count then parks for human review. Criteria: regression test
  shows bounded deferral → parked; suite green.
- **node-08-late-result-terminal** (BM-042) — a late executor result must not be
  marked terminal `ignored`; record it as late evidence attached to the node.
  Criteria: regression test; evidence visible; suite green.
- **node-09-late-after-cancel** (BM-043) — a result arriving after best-effort
  cancellation is recorded (not dropped) and flagged for review. Criteria:
  regression test; suite green.
- **node-10-scan-abort-containment** (BM-012) — one project's scan failure must
  not abort `--all-active` scans of other projects. Criteria: regression test
  with a failing project and a healthy one; suite green.

## Tranche 3 — dispatch-path repairs (11–15)

- **node-11-scope-blocked-resumable** (BM-013) — `scope_blocked` becomes a
  resumable park, not terminal disposal. Criteria: re-scoped event dispatches
  without operator DB surgery; suite green.
- **node-12-duplicate-lock-escape** (BM-006) — documented operator escape for a
  false permanent duplicate lock (CLI verb, not SQL). Criteria: escape releases
  lock, logs the override; suite green.
- **node-13-operator-escape-hatch** (BM-041) — explicit operator escape for
  indefinite duplicate-dispatch blocks, same pattern. Criteria: CLI verb works,
  override logged; suite green.
- **node-14-planned-mission-intake** (BM-009) — an already-planned mission's
  intake is not gated by the unsolicited-webhook rule. Criteria: regression
  test; unsolicited intake still refused; suite green.
- **node-15-prelaunch-repair** (BM-024) — avoidable engagement pre-launch
  rejections repair locally (fetch/checkout) before refusing. Criteria:
  regression test shows repair-then-proceed; genuine refusal still refuses;
  suite green.

## Tranche 4 — evaluation-path repairs (16–19)

- **node-16-evaluate-retrievable** (BM-026) — single-session path: a
  retrievable commit is evaluated even when durability bookkeeping fails;
  durability repaired separately. Criteria: regression test; suite green.
- **node-17-record-not-suppress-single** (BM-028 single-session residue) —
  record the anomaly, still evaluate. Criteria: regression test; suite green.
- **node-18-orphaned-capacity** (BM-023) — capacity/duplicate guards release
  when no executor is progressing. Criteria: regression test; suite green.
- **node-19-human-gate-removal** — remove the human_gate flag handling from
  frontier/provisional code and fixtures (already ordered; VM YAMLs cleaned
  separately by operator). Criteria: flag gone from code; suite green.

## Explicitly NOT in this package

- node-10 redo / node-11 retry (pi-harness-execution graph, separate decision)
- BM-018 merge machinery (a capability build, not a fix — needs its own design
  conversation before it becomes a node)
- The 3 flask intake tests on the VM (environment gap, not graph work)
- gddp-config reconciliation commit (janitorial, mine to do directly)
