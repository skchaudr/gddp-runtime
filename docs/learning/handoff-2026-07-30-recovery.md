# Handoff — 2026-07-30, GDDP recovery pass

**Audience: the agent picking this up.** Not a project doc. Written from Rig 1
(sab-air) at 2026-07-30 ~03:20Z / 2026-07-29 20:20 PDT. Sab is moving
environments because the session that produced this went badly (see
[Read this first](#read-this-first)).

---

## Read this first

The operator did not come here for maintenance. He came to be helped through a
**reckoning**: the conclusion, reached the previous session, that GDDP is close
to the inverse of what he asked for. Nodes were meant to be an *automated*
quality gate — opening provisionally on strong evaluator evidence, without him
present, with reasoning retrievable afterward for review. What exists requires
his manual certification at every step.

Core defect, already diagnosed and not in dispute: **`complete` became both the
canonical human-truth marker and the scheduler's permission gate.** Those must
separate.

Operating rule he adopted, and which he has already caught one agent violating:
**no presumption of preservation.** Every component justifies its existence for
the intended behavior or is deleted/rewritten. Adding vocabulary, adding docs,
"auditing," and reorganizing-while-keeping are the *same reflex under a
different name*. He has named this explicitly. Do not do it.

The session that produced this handoff failed in exactly that way: it added
~90 lines and deleted zero, re-derived conclusions already handed to it, spent
hours on PATH fixes and snapshots while the recovery sat untouched, and asked
for approval repeatedly instead of acting — in a conversation about a system
that cannot advance without him. **Read a request for the thing it asks for.
Weight tasks unequally. He has abundant Codex/Grok usage; implementation should
be delegated, not done here.**

---

## Live state

### Two machines only

| | sab-air (Rig 1) | sab-mini (home) |
|---|---|---|
| Role | async Jules lane, `com.gddp.rig1.heartbeat`, 300s | primary, its own clone + DB |
| runtime HEAD | `5beb302` | `5beb302` (snapshot branch off it) |
| config HEAD | `c8cd057` | `58c6e8b` at snapshot time |
| Snapshot | `/Users/saboor/snapshots/gddp-air-20260730T022303Z` | `/Users/sab-mini/snapshots/gddp-20260730T013731Z` |

Both snapshots hold four things no git mirror does: `db/` (gitignored),
`verification-runtime-live/` (gitignored), the plist (outside both repos), and
result branches never pushed. API keys deliberately excluded.

### Codex thread on sab-mini — parked

Pane `w2D:p1G`, **idle**. Read it with:

```
ssh sab-mini 'herdr pane read w2D:p1G --source recent --lines 220 --format text'
```

(`herdr --remote sab-mini` refuses non-interactively: server is v0.7.5 and wants
an approved update. ssh + `herdr <subcommand>` works fine.)

It got as far as pushing attributed pre-recovery snapshot commits:

- runtime `4c086a3`, config `3b63146`
- subject: `7.30.26 architectural disappointment realization`
- empty commits, trees verified identical, **both mains unchanged, tags intact**

The recovery itself — the deletions — **has not started.** Codex reported one
usage-limit reset remaining. The last operator input to it trails off
mid-sentence ("So, Claude made a point that it believed it was a good thing
so"), so it is waiting on him.

### Jules sessions — deadlock broken today

Three sessions sat in `AWAITING_USER_FEEDBACK` for **12.5 hours**. Each had
finished its work and stopped to ask permission to finish; every question was
already answered by the node packet it was given. `canary-retry-proof` pasted
the sentence that answered it ("designed so the executor will miss it on first
attempt") and then asked whether to miss it.

Cause was not policy. Three API mechanisms existed and none were used:

1. `automationMode` never set anywhere in code → Jules had no way to *land*
   work, so "should I commit?" was a genuine ambiguity.
2. `POST /sessions/{id}:sendMessage` → zero occurrences in the repo. The reply
   endpoint was never implemented, which is the only reason `needs_operator`
   was terminal.
3. `requirePlanApproval: False` *was* sent — and is a no-op, since the
   documented default is already false.

After the fix below, all three moved on the first 300s tick:

| session | node | state now |
|---|---|---|
| `5459406426454272010` | verdict-confidence-split | COMPLETED, real patch |
| `12018894192208831305` | canary-retry-proof | COMPLETED, "produce failure" |
| `8889434020487970160` | pi-evaluator-harness | IN_PROGRESS |

No PRs on any of them: `automationMode` is **create-time only**, and these
sessions predate the flag. Only new dispatches get PRs.

The verdict-confidence-split patch is worth reading — it renames
`_confidence_semantic_blend` → `_signals_semantic_blend` and defers to the
semantic score when the deterministic floor is indeterminate. That resolves the
criterion `blend-defers-to-semantic-when-floor-indeterminate`, which was
unsatisfiable because it named a function that did not exist.

### Database (Air, `db/queue.db`)

```
executor_sessions:  awaiting_reply 3, evaluated 2, failed 5
results:            2      (both crash-laundered — see below)
decision_results:   0      (empty since inception; nothing has ever adjudicated)
```

### Graph statuses (gddp-runtime nodes)

`pending 9, ready 6, complete 5, deferred 1`. No status means
"opened on evidence without a human," which is the conflation named above.

Ready every tick, never dispatched: `verdict-confidence-split`,
`pi-evaluator-harness`, `pi-evaluator-guard`, `canary-retry-proof`,
`job-state-consistency`, `heartbeat-crash-recovery`. **Dispatch only fires from
hand-authored `manual_inject` events** — the frontier→dispatch edge is manual
too.

---

## Uncommitted on Air — 5 files, review before trusting

```
scripts/adapters/executor_protocol.py
scripts/adapters/jules_api_adapter.py
scripts/adapters/test_executor_contract.py
scripts/runtime/heartbeat/reconciler.py
scripts/runtime/heartbeat/state_recorder.py
```

What they do:

- `dispatch()` sets `automationMode: AUTO_CREATE_PR`; the no-op
  `requirePlanApproval` is gone.
- `reply()` added to the Jules API adapter → `:sendMessage`. Probed by
  `hasattr`, deliberately **not** added to the `ExecutorAdapter` Protocol,
  because it is `runtime_checkable` and declaring it would break isinstance for
  adapters that cannot converse.
- `AWAITING_USER_FEEDBACK` now maps to a new `awaiting_reply` state;
  `AWAITING_PLAN_APPROVAL` / `PAUSED` stay `needs_operator`. Collapsing the
  three is what made the state terminal.
- Reconciler answers a question **once** with a standing "your packet carries
  full authority" reply, then escalates to `needs_operator` if the same session
  asks again. Bound is one auto-reply per parking episode, tracked by the
  existing state column — no migration.

**A regression was introduced and then fixed inside this same session; verify
it.** `awaiting_reply` was not in the active-session poll whitelist, so after
answering, all three sessions dropped out of reconciliation entirely and the two
COMPLETED ones were invisible to the heartbeat from 02:55Z onward. Fixed at
`state_recorder.py:365,372`. This is the same bug class as the one being fixed —
worth treating as evidence about how easily a new state becomes a new silent
parking lot.

Tests: **430 pass, 1 fail.** The failure is `test_rig1_render_plist.py::
test_render_heartbeat_default_jules_key_cmd` — pre-existing, deploy/ keychain-vs-
file default, last touched by `7d69498`, unrelated to these files.

Also on Air, already committed earlier: the LaunchAgent PATH fix. `/usr/local/bin`
held a stale Node 18 ahead of Homebrew's Node 26; `pi` is `#!/usr/bin/env node`
and needs `>=22.19.0`, so **every** evaluator run on this rig crashed while
interactive shells stayed fine.

---

## Do not trust the evidence layer

Both `results` rows contain, simultaneously:

```
lane_status: {"criteria": "crashed", "integrity": "crashed"}
criteria_confidence: 0.36   (0.16 on the other)
verdict: "needs-human-review"
harness_error: "pi exited with code 1: ... Node.js v18.16.1"
```

A crashed harness and a genuine "needs more evidence" judgement are
indistinguishable in the stored receipt. **Any confidence number emitted while
`lane_status == "crashed"` is fabricated.** Check `lane_status` before believing
any figure. This matters directly for the recovery: decisions about what is
load-bearing are otherwise being made on the same intuition that built the wrong
thing.

The `vault-doctor/scan-vault-core` receipt is from 2026-07-06 and predates the
confidence split; it needs regenerating.

---

## Pending work, unequally weighted

**1. The recovery deletions (the actual point).** Owner: Codex on sab-mini,
resumed by the operator. Snapshots exist; mains are clean; nothing blocks it.

Approved cut, 2,316 lines exact, zero code importers, 34 tests:

```
scripts/runtime/decision_loop/          1,504
scripts/runtime/graph_updater.py          279
scripts/runtime/test_graph_updater.py     235
docs/decision-loop-spec.md                298
```

Three things must travel with it, flagged and not yet included:

- ~15 `droid-wiki/` files describe both deleted systems as live — including
  `background/design-decisions.md:15` and `systems/state-persistence.md:3`,
  which encode the auto-advancement prohibition the operator has already ruled
  an agent distortion.
- `results_store.py:164,191` — two functions go dead the moment `engine.py` goes.
- Dangling links: `PROJECT-BRIEF.md:231`,
  `droid-wiki/overview/getting-started.md:54`, `docs/overnight-readiness.md:14`.

Keep `decision_results` for now — `jobs_status.py:249,339` uses it as the manual
job-audit log.

**2. Second deletion, newly unlocked.** With `AUTO_CREATE_PR`, Jules returns
PRs, so the entire patch-transport path has nothing to do: `collect()`'s
activity pagination, `base_commit_sha` threading, patch apply/persist. That
subsystem existed *only* because nobody set the flag. It was already item #1 on
the prior session's deletion candidate list.

**3. Deferred on purpose — do not remove by analogy.** The `local_subprocess`
ancestry check at `reconciler.py:470` is structurally similar to the deleted
HEAD-mismatch gate, but its failure mode is not understood the way that one was.
The operator kept it deliberately. `047dede` records why. This deferral is the
working model in miniature: delete on evidence, keep without it.

**4. Small, delegate it.** Tests for the reply path; the pre-existing plist
test; committing the 5 files above.

---

## Open questions that belong to the operator, not an agent

- Does a provisionally-open node satisfy a dependency for downstream dispatch?
  If yes, the graph advances on evidence and `complete` demotes to a human
  annotation with no scheduler power. This is graph truth.
- What replaces `manual_inject` as the trigger, so a ready node dispatches
  without a hand-authored event.
- Whether a crashed lane should be forbidden from emitting a confidence value at
  all, rather than defaulting to a number.
