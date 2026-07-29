# GDDP Rebuild

Written 2026-07-29, after Rig 1's first unattended run.

This is not a cleanup pass. It replaces a foundation.

---

## What went wrong, structurally

Agents add. They almost never remove.

A system that reads, parses, and generates faster than a human will, by default,
respond to every problem by adding a layer. Adding is safe — it cannot break what
already works, it looks like progress, and it is fast. Removing requires
understanding what depends on what, and being willing to be wrong visibly. The
gradient always points at "add."

Every agent that arrives has no memory of why the previous layer was added. It
reads accretion as terrain and builds on it. Over enough sessions, workarounds
become architecture, and nobody chose any of it.

GDDP is what that produces. Not bad code — *unchosen* code.

The overnight run made this legible because a human finally had to operate the
thing end to end and ask what each part was for. Every question found something:

| Question asked | What it found |
|---|---|
| "What is install-dormant?" | A pi-big→sab-mini cutover tool with an exclusivity contract, repurposed as a rig installer |
| "Why are we against the webhook listener?" | A split-brain risk that does not exist — GitHub only sends to one host |
| "What's the polling stage?" | A module named `reconciler` that reconciles nothing |
| "Why are we dealing with patches?" | Nobody set `automationMode`, so a whole subsystem grew to manage diffs |
| "Was that node even ready?" | Two CLI surfaces disagreeing about what is dispatchable |

Six findings, one cause.

---

## The measure that got lost

The purpose of the rigs is **comparative evidence about pathways** — which route
is trustworthy for which kind of work, and what the evaluator sees differently
across them. Acceptance follows trust; trust follows evidence.

The nodes are instrumentation. Whether a node's code is correct, whether git
history is clean, whether a patch applies — none of that is the product. The
product is **the evaluator's judgment, in front of a human.**

The overnight run failed by that measure, and it failed in the most instructive
way possible: **the integrity mechanism prevented the evidence.**

Three sessions returned real work. All three were rejected because a commit hash
did not match, before a single acceptance criterion was read. The system
protected the repository from imperfect patches and, in doing so, destroyed the
only output anyone wanted.

That tradeoff was never chosen. It accreted.

**Design rule going forward: no mechanism may block the evaluator from rendering
a judgment.** Admission control decides what gets *merged*, never what gets
*evaluated*. A verdict on flawed work is worth more than silence on correct work.

---

## Foundation being replaced: blocking review → provisional continuation

This is the deepest one. Everything else in this document is downstream of it.

### The original intent

If valid work passes locally in a meaningful way, and there is downtime with
nothing being done for hours, the agent should move to the next node and keep
building. Dependencies exist to **sequence agents**, not to force operator
downtime. Sab retains final authority to accept, reject, or unwind graph truth at
any point.

That was the point of GDDP from day one.

### What was built instead

Two different questions were collapsed into one:

1. **May the next agent start work?** — execution sequencing
2. **Is this node done?** — graph truth, human-owned

"Human owns graph truth" was read as "a human must approve every transition
before any further work happens." That converts every dependency edge into an
operator wait state.

Verified mechanism, 2026-07-29:

- `reconciler.py:746` — after evaluation, the job is set to `awaiting_review`
  unconditionally. There is no branch on the verdict. A passing evaluation and a
  failing one produce identical state.
- `scope_checker.py:59` — a dependent node is blocked unless its dependency is
  `complete` in graph YAML, and `complete` is only ever written by a human
  editing that YAML by hand.

Net: **passing work cannot unblock anything.** There is no autonomous
continuation path. The system was built to stop.

### What replaces it

Separate the two questions that were merged.

A strong evaluator pass advances execution **provisionally** — dependents become
dispatchable, agents keep moving, the queue keeps draining. Graph truth stays
exactly where it is: `awaiting_review`, awaiting human acceptance, with full
authority to reject or unwind anything that was built on a provisional pass.

`scope_checker` gates on *execution eligibility*, not on graph status. Graph
status remains the human's record of what is actually accepted.

This is not auto-acceptance. Nothing writes to gddp-config. The human's authority
is unchanged — what changes is that exercising it is no longer a precondition for
the next agent to start.

### Why this was hard to see

The blocking behavior was recorded, in agent memory and in prior handoffs, as a
deliberate **frozen invariant** — "no automatic graph writeback or node
advancement may be reintroduced." Every subsequent agent inherited that as
doctrine and defended it, including during this session.

A distortion that gets written down as a principle is much more durable than a
bug. This is the strongest argument for the standing rule at the bottom of this
document.

---

## Foundation being replaced: patch return → PR return

### What exists now

The Jules API adapter creates a session with no `automationMode`. Per the API
docs, default means no PR is created and code changes come back as `changeSet`
artifacts inside activities. So the system:

1. Pages through session activities hunting for `changeSet.gitPatch`
2. Extracts a `unidiffPatch` and a `baseCommitId`
3. Writes the patch to a spool directory
4. Records `expected_base_commit_sha` from **local git HEAD** at dispatch
5. Compares the two at collect time and rejects on mismatch

Every step after (1) exists only because the output is a diff. A diff is
meaningless without the commit it applies to, so the runtime had to invent
base tracking, base binding, an integrity check, a spool, and — as of last night
— a preflight guard to protect the binding.

Five layers, all downstream of one unset config field.

### What replaces it

`automationMode: AUTO_CREATE_PR`. Jules opens a real GitHub PR, surfaced as
`session.outputs[].pullRequest` with `url`, `title`, `description`.

A PR carries its own base and its own merge semantics. There is nothing to bind
to a local HEAD, nothing to mismatch, nothing to spool.

It also reconnects to `return_router.py`, which already exists, already handles
merged-PR events, and is already the documented return path.

### What comes out

- `expected_base_commit_sha` binding in `runner.py`
- base-SHA mismatch rejection in `reconciler.py`
- patch-hunting in `JulesApiAdapter.collect()`
- the patch spool
- `_REMOTE_BRANCHING_EXECUTORS` preflight guard in `dispatcher.py` (`6e86f17`)

That last one is mine, written last night. It defends a mechanism this rebuild
deletes. It is included here deliberately: the instinct that produced it is the
same instinct this document exists to correct.

### What this is not

Not a rewrite. Not a new abstraction. The replacement is a config field plus the
removal of what that field made unnecessary. If the change grows a new subsystem,
it has failed.

### Open questions before doing it

- Does the local executor lane (`local_subprocess`) still need base binding? It
  runs in a worktree off local HEAD, so probably yes — the removal may be
  Jules-specific rather than global.
- Does a PR-based return still let the evaluator see the work *before* merge?
  It must. Evaluation cannot depend on a human merging first.
- What happens to `jules_action`, the original GitHub-issue adapter? PR mode may
  make it redundant, or may make it the same thing by a different route.

---

## Sequencing

1. **Stop admission from blocking evaluation.** `reconciler.py:496` raises on
   base mismatch before the worktree is even created. Build at the patch's own
   base instead, record the mismatch as a finding on the receipt, evaluate, and
   mark the job non-integratable. Only an unretrievable or unidentifiable result
   should prevent evaluation. Delete the preflight guard from `6e86f17` in the
   same change — it prevents dispatch in a situation that would now produce a
   readable verdict.
2. **Provisional continuation.** Branch on the verdict at `reconciler.py:746`;
   gate `scope_checker` on execution eligibility rather than graph status. This
   is the one that restores the original intent.
3. **Answer the retry question.** `retry_budget: 3`, zero retries fired.
4. **Then** the PR-return replacement, with deletions in the same change as the
   config flip — never the flip alone, or the old machinery becomes dead weight
   nobody dares remove.

Note what is *not* on this list: hand-feeding a `changeSet` to the evaluator to
get a verdict out of last night's stuck work. It would produce a verdict, but it
would be unearned — it proves nothing about whether the pathway delivers verdicts
on its own, which is the entire thesis of the rig.

Renames and doc gaps are tracked in `Current-GDDP-Tasks.md` and are not part of
this rebuild.

---

## Standing rule for agents working in this repo

Before adding a layer, establish what it is compensating for and whether that
thing should exist. If the answer is "an earlier layer," remove instead.

Prefer deleting a mechanism to guarding it.
