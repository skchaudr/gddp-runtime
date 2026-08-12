# 093 — Post-dogfood outstanding inventory (for operator review)

Purpose: Sab asked for the complete outstanding-issues list, written out in full
sentences with enough context to read carefully away from the chat. This is a
reading document, not a work order. Nothing here is started unless Sab says so.

------------------------------------------------ Agent Section START

Date: 2026-08-12
Worktree: main checkout (sab-mini)
Branch: main (both repos clean and synced with origin; VM synced likewise)

## Where things stand

The 22-node dogfood run completed on 2026-08-11: 19 pass, 2 needs-human-review,
1 fail (the fail was a miswritten criterion, not bad work). The post-demolition
runtime ran the full loop unattended for ~4.5 hours. Since then: the VM
gddp-config divergence was reconciled (12 rebased onto 10, pushed), the
heartbeat timer moved to 2 minutes, Grok 4.6 landed five import-tooling fixes,
and the pi-harness-execution backlog was retroactively evaluated (all
criteria-pass). Sab personally committed the T4 provisional status writes as
`712f5eb`, taking human ownership of the runtime's pass record.

## A. Waiting on the operator

**A1. The gddp-dogfood review queue (22 nodes).** Nineteen nodes passed and sit
at `provisional`; only Sab can move them to `complete`. Nodes 11 and 13 are
held for review on a paperwork nit (the executor did not verifiably quote the
pytest tail line); the work itself looked fine on inspection. Node 16 received
a `fail` verdict because the criterion allowed exactly 3 known host failures
and the suite showed 4 — the fourth being a pre-existing, unrelated rig1
assertion the executor documented honestly. The evaluator's own evidence
confirms the new test passes 5/5. Recommendation on record: accept 16, quick
eyeball on 11/13. Review runs through `bin/gddp node browse --project
gddp-dogfood`: c = accept (complete), r = reject (returns to ready; the retry
carries findings as the fix-list), d = defer.

**A2. The pi-harness-execution review queue (9 nodes).** The four execute nodes
were droid-era `factory_mission` results whose verdicts were suppressed by the
"second court" (review_required → evaluator never invoked — the exact pathology
the demolition removed). They now have post-hoc evaluator receipts, as do the
five audits. All nine are criteria-pass and awaiting the same accept/reject
decision.

**A3. The status-storage redesign (the live design thread).** Discussion
concluded: node YAML files should be pure definitions (intent: title, criteria,
dependencies — human-authored, never runtime-touched), and `project.yaml`
should be the single execution board carrying status. The March-era mistake
was not the index; it was keeping status writable in both places. This
redesign absorbs the provisional write-through doctrine question (A: runtime
never writes graph status / B: blessed automation commits) by reducing the
writable surface to one designated file.

**A4. Sab's two project graphs.** Ready to be fleshed out. The intent is a
pilot run where Sab operates the tooling himself (import, dispatch, review)
with Pi as co-pilot — the usability proof.

## B. Pi executor defects (real, unfiled)

**B1. One-shot hang (worked around, root cause open).** A completed one-shot pi
process (`--print`) failed to exit: extension discovery registers an inotify
file-watcher that keeps the Node event loop alive (`do_epoll_wait` on the
inotify fd, zero sockets, exits only on signal). The workaround —
`--no-extensions` in the executor argv — produced clean first-attempt exits
for the rest of the run. The root fix belongs in pi itself: one-shot mode
should drain the loop on completion regardless of extension watchers. Evidence
is packaged from the dogfood run; an issue has not been filed.

**B2. No execution timeout floor.** `local_agent_executor` waits on the agent
process with no timeout. The hang above was caught only because a human-equivalent
was watching the process table. A hung session holds capacity indefinitely.

**B3. BM-026 confirmed live.** Exit code outranks durable result: node-01's
first attempt completed its work (commit durable at 04:33) but was SIGINT'd
during the hang, exited 254, was marked failed, and retried — ~13 minutes of
redundant work. The register already holds the fix direction (evaluate
retrievable results; repair durability separately).

## C. Unproven lanes

**C1. Pi-RPC adapter.** Merged, never canaried. A staged canary exists in
`.worktrees/pi-rpc-adapter`. The one-shot local_subprocess lane is the proven
path; pi-rpc remains a claim until a node round-trips through it.

## D. Ruled but never executed

**D1. Push-guard archive.** Sab ruled (089 §8.4) that `mission_push_guard.py`
cannot live in production until a real use case appears. It is now unwired
(zero live imports) but still physically present with its tests. The archive
move was never executed.

**D2. 089 Stage 4 ("measure, record, stop").** The demolition's closing stage —
final line-count accounting and the stop record — never ran.

**D3. The 091 backlog.** Nineteen substantive runtime repairs (BM-006–044
class) preserved as an unapproved package at
`.handoffs/091-dogfood-node-package.md`. Deferred during dogfood because the
nodes mixed path validation with path repair (failure would have been
ambiguous); they await re-scoping as their own package.

## E. Host and hygiene items (small)

- **mini heartbeat is dead** (has been since the EX_CONFIG era: configured
  `.venv` missing). Mini cannot be an engine until the FRESH-HOST-STANDUP
  checklist runs. Currently VM is the only engine; mini is cockpit-only.
- **DeepSeek duplicate export** in the VM's gddp.env (a stale line-9 export
  shadowed by the effective line-21). Cosmetic; removal deferred mid-run.
- **Mercury keychain entry missing** (credential hygiene, longstanding).
- **Demolition worktree cleanup** — `.worktrees/mission-demolition` is fully
  merged and holds a duplicate 092 draft; removal needs Sab's explicit word.
- **VM flask gap** — three test-collection failures (flask not installed,
  PEP 668 blocks pip); pre-existing, off the live path.
- **`project.yaml.bak`** was swept into a dogfood import commit; classify or
  remove at the next config housekeeping pass.

## F. Resolved this session (for board completeness)

Import tooling friction (five fixes, Grok 4.6: priority alias, `--update`
path, artifact-path warning, dispatch `--yes`, docs); VM gddp-config divergence
(rebased, pushed, all three checkouts synced); heartbeat timer 5min → 2min;
the pi-harness "no evaluator" question (second-court victims, now judged);
the T4 provisional writes (committed by Sab as `712f5eb`).

## The proposal shape under discussion

The status-board redesign (A3) is the shift: node files become pure
definitions; `project.yaml` becomes the one mutable status store; the dual
rewriters and the desync failure class die. The migration is small (schema
drops status from node files, readers pivot to the board, validator's
cross-check becomes one-way). The pilot run (A4) then doubles as the
migration's proof: Sab flies a graph on the new shape. Executor-defect fixes
(B1–B3) are natural pilot-graph node content. Multi-heartbeat direction is
recorded (`docs/decision-multi-heartbeat-direction.md`) and converges with the
redesign: one status store is where the coordination algorithms live.

### Resume point

Sab reads this inventory, then the design conversation resumes on the
status-board proposal. No agent work is in flight; nothing is running; all
repos are clean and synced.

------------------------------------------------ Agent Section END

------------------------ Do NOT edit this file past this point

## Narrative / Trajectory (SAB ONLY)

### Intent going into/at start of session

### Interpretation of how the session went

### Friction experienced or anticipated

### What's Next (Momentum or Lack Thereof)
