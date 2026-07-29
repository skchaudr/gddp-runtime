# Current GDDP Tasks

Open work as of 2026-07-29, after Rig 1's first unattended overnight run.

Ordering is by what unblocks evidence, not by severity. The measure of every item
below is whether it gets the evaluator's judgment in front of a human faster.

---

## Blocking the only thing that matters

### 1. Get an evaluator verdict on real returned work

Nothing reached evaluation on the overnight run. Five nodes dispatched, five real
Jules sessions completed with real `changeSet` artifacts, and the DeepSeek lane
never ran — three rejected on base-SHA mismatch, two collected after the fact.

This was the stated purpose of the run. It is the only open item that is not
plumbing.

Two live sessions have completed work sitting in them right now:

| node | session | state |
|---|---|---|
| heartbeat-crash-recovery | 7631176305667133873 | COMPLETED, changeSet present |
| verdict-confidence-split | 16018024730217648008 | COMPLETED, changeSet present |

**As of `56db172` the blocker is removed** — the base-commit comparison that
discarded three nodes unread is gone, so a re-dispatch now reaches evaluation
whether or not the base matches.

Not doing: hand-feeding a `changeSet` to the evaluator to force a verdict out of
last night's stuck work. It would produce a verdict but prove nothing about
whether the pathway delivers verdicts on its own, which is the thesis. The
earned path is a clean re-dispatch through the live loop.

---

## Pathway questions Rig 1 was built to answer

### 2. Verify retry behavior (#6)

`retry_budget: 3` in project.yaml. All three failed sessions show
`attempt_index 0` — no retry fired. Either base mismatch is deliberately
non-retryable, or retries are not wiring up.

"How do retries behave over hours" is one of Rig 1's three stated theses. It is
currently unanswered, not answered-in-the-negative.

### 3. Evaluator drift — untested

The third thesis. Cannot be tested until item 1 produces verdicts to compare.

---

## Accretion to remove or replace

See `GDDP-rebuild.md` for the reasoning. Tracked here for status only.

### 4. Rename `reconciler` (#12)

Nothing is reconciled. One source of truth (the executor session); the module
polls it, collects the patch, checks the base, and hands off. Name needs to say
"evaluates fitness to advance, retries up to N" without colliding with the
acceptance-criteria evaluator, and without reading as judge/oracle/auditor/verifier.

Candidate: `triage.py`. Name not yet decided — that decision blocks the work.

Touches: `scripts/runtime/heartbeat/reconciler.py`, runner import and call sites,
`--repo-path` help text, `[reconcile]` log prefixes, and four docs.

### 5. Land `fix/script-guards` (#2)

`scripts/heartbeat.py` is a legacy Phase 3 demo with a hardcoded
`PHASE3_NODE = scan-vault-core` that opens real GitHub issues (it opened #109
during bring-up). `scripts/dry_run.py` ignores `--help` and writes to the live DB.

Both are named like the real entrypoints and sit where someone bringing up a new
rig will find them first. Branch was requested from Grok; current state unconfirmed.

### 6. Machine-agnostic rig bring-up doc (#7)

The only bring-up doc is `deploy/mini-heartbeat/README.md`, written for a
pi-big → sab-mini cutover with a one-plane exclusivity contract. A third rig has
no runbook, which is why Rig 1's bring-up was hand-rolled and hit every footgun
in sequence.

Must cover: checkout must be on the executor's starting branch before dispatch;
key files live at `~/.config/gddp/*` and why (not `pass`, not keychain — neither
survives a headless session); the real tick is
`python -m scripts.runtime.heartbeat.runner`; `scripts/` contains demos that fire
real outward actions.

---

## Graph decisions (human-owned)

### 7. `pi-evaluator-guard` status (#10)

`project.yaml` marks it `status: ready` while its `depends_on` target
`pi-evaluator-harness` is also only `ready`, not `complete`. A node whose
dependency is incomplete should not carry `ready`.

Open question is which is wrong: the status field, or the frontier derivation
that recomputes blocked-ness at dispatch time. Dispatch behaved correctly and
refused it; the interactive CLI surface showed it as available.

### 8. Re-dispatch the three base-mismatch nodes (#9)

`canary-retry-proof`, `job-state-consistency`, `pi-evaluator-harness` failed on
base binding, not on merit. Unblocked now — HEAD is back on `main` and the
preflight guard is in.

Worth checking their existing session patches before spending executor budget
again. Note `canary-retry-proof`'s premise may no longer hold: it was designed so
the executor would miss `docs/echo-usage.md`, and Jules created that file.

---

## Closed 2026-07-29

- Merged `feat/rig1-scheduler` to main (`7d69498`) — the unmerged branch was the
  direct cause of the base-SHA failures
- Base-branch preflight guard (`6e86f17`) — refuses remote executors when the
  checkout has drifted off the executor's starting branch. **Note:** this guard
  may be deleted rather than kept; see `GDDP-rebuild.md`.
- Removed orphaned `jobs/job_dry_001` fixtures
- Rig 1 scheduler installed and armed (`com.gddp.rig1.heartbeat`, 300s)
- Both API keys moved to `0600` files that survive a locked keychain
- `gddp` CLI menu bugs — fixed separately on a TUI branch, not yet merged
