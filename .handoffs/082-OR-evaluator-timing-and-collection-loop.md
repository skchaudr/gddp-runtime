# 082 — OR — Evaluator timing, collection-loop naming, and the persistent-executor path

**OR = operator review required.** Nothing in this handoff has been acted on. It records what the
observation session raised that the five-node audit mission did not, plus two decisions only the
operator can make.

Date: 2026-08-09
Branch context: `feat/khoj-idle-shutdown`; mission work on `mission/milestone3`
Source: external read-only observation of the `factory_mission` build and the subsequent 5-node VM audit mission

---

## 1. The evaluator is armed by a process dying

The evaluator never runs while a mission is alive. Traced in `scripts/runtime/heartbeat/reconciler.py`:

```python
status = adapter.status(session_ref)
if status.state in {"dispatched", "running"}:
    for session in sessions:                 # all five
        update_executor_session_state(con, session["session_db_id"], state=status.state)
    return                                   # nothing else can happen
if status.state not in {"completed", "failed", "crashed"}:
    return
results = adapter.collect_engagement(session_ref)
```

`adapter.status()` derives its state from `process.poll()` on the mission PID. So mission exit is the
only event the loop can react to.

The "all jobs show `running`" state is **not display lag**. The loop actively writes `running` to
every row in the group on each 5-minute tick and returns.

Consequence still visible in the DB: `node-07-instructions-audit` remains `status=running`,
`state=running` with a live session id, hours after the droid process exited. Nothing has come back
for it because nothing can, until a status poll returns a terminal state.

**Correction to an earlier reading.** During the run this section was written against a live example
— node-01 completing at `07:17:29Z` with a commit, `gddp receipt` exit 0 and verified reachability,
then sitting unevaluated. That example was wrong: node-01 never reached this code path at all
(see §9). The reconciler trace above is accurate as code analysis; the anecdote attached to it was
Factory's internal mission state, not GDDP's.

## 2. Per-node collection is refused by contract, not deferred by schedule

`scripts/adapters/mission_adapter.py`:

```python
def collect(self, session_ref, dest_path):
    results = self.collect_engagement(session_ref)
    if len(results) != 1:
        return PatchResult(success=False, review_required=True,
            error="single-node collect cannot represent "
                  f"{len(results)} engagement results")
```

`collect_engagement` then sweeps all features at once against a status it names `terminal_status`.
There is no incremental path. This is a design property to change deliberately, not a bug to patch.

## 3. Feature-id mismatch has a five-node blast radius

```python
if len(by_feature) != len(results) or set(by_feature) != set(jobs_by_node):
    reason = ("engagement collect feature ids do not match reserved node ids; "
              "human review required")
    for session, job in jobs_by_node.values():
        _route_engagement_result_to_review(...)
```

One unrecognised feature id routes **all five** nodes to human review, including nodes that
completed cleanly. This is live risk, not theory: the previous mission grew its own feature set
12 → 19 → 22 by injecting remediation features mid-run. Any such injection produces ids the graph
never reserved.

## 4. Naming: `reconciler` should follow `conductor`

`conductor` was already renamed to the verification loop on the grounds that it implied
interpretation from something that only sequenced. `reconciler` is the same failure, unfixed.

- **Evaluator** is an agent. `scripts/runtime/verification/semantic/` holds `agent.py`, `prompt.py`,
  `pi_runner.py`, `pi_harness/gddp_verifier.ts`. `decision_engine.py` carries per-criterion
  `confidence` floats and `indeterminate` as a first-class verdict. The name matches the authority.
- **Reconciler** is a deterministic loop with no model and no inference. It polls, moves rows
  `running → collected → evaluated → awaiting_review`, does the git apply/commit, and writes the
  result row. `_run_evaluation` is defined *inside* it — the loop **calls** the evaluator. They are
  caller and callee, not peers.

The term is on loan from Kubernetes, where a reconciler *converges* observed toward desired state
from either direction. This one advances a linear state machine one way and converges nothing.

**Proposed: collection loop.** The adapter method is `collect`, the state is `collected`, and
`return_router.py` already exists. Claims nothing it does not do.

## 5. Decision taken: evaluate on node completion

Operator decision, recorded here: **the evaluator should run the moment a node completes**, whether
or not it gates or provisionally allows.

Rationale: evaluation is *information*; gating is *policy*. Welding them means the verdict waits on
a decision it does not need.

This is not blocked on evidence. Everything `verify_job_return` consumes existed at node-01's
07:17:29Z completion, and `d40ae31 feat(evidence): collect per-node mission manifests` already
shipped per-node granularity in the evidence layer. What is missing is a **signal** — today the only
one is mission-level `process.poll()`. Stream-JSON emits per-node events on a wire.

Collection and evaluation then stop sharing a clock: collection moves code and can stay at mission
exit where the branch mechanics live; evaluation judges a commit and can fire when the commit exists.

## 6. OPEN — operator decision required

**A node evaluated at completion is judged against its own commit.** Today everything is judged at
the end, against accumulated state. If node-05 edits node-01's files, an early node-01 verdict does
not move.

Judging what a node actually did is arguably more correct than judging what survived its successors
— but it answers a different question than the current design, and the change should be chosen
rather than absorbed as a side effect.

## 7. RESOLVED — persistent-executor work is now committed

At 01:29 this was 911 untracked lines on `feat/pi-rpc-adapter` with zero commits, while the
mission-mode exception had 20 commits and 8,988 lines at origin. As of 03:54 the branch is **19
commits ahead of main with a clean working tree**. The exposure is closed.

Retained as a note only because the prior mission's closing advice recommended a `git stash pop`
onto this exact branch, which would have dropped stale mission code (importing a `mission_push_policy`
module that no longer exists) over it. Do not follow that advice.

## 8. NOT VERIFIED

- Whether §3's blast radius ever triggered. It could not have on this run — collection never ran
  (see §9), so the feature-id guard was never reached. Still untested against a real mission.
- The per-node manifest claim in §5 is read from commit `d40ae31`, not from a fresh read of
  `mission_evidence.py`.
- Whether a Factory mission covering all five audits was launched outside GDDP's dispatcher. The
  droid-side heartbeats reported all five progressing, which GDDP's records cannot account for.
  Operator knows how it was launched; this handoff does not.

## 9. What the ledger actually records — read this before §1–§3

Queried `db/queue.db` at 03:54 (the DB is local; `GDDP_RUNTIME_ROOT=/Users/sab-mini/repos/gddp-runtime`,
`DB_PATH = RUNTIME_ROOT / "db" / "queue.db"`):

| node | job status | session state | error |
|---|---|---|---|
| `node-01-subagents-audit` | failed | `dispatch_failed` | `Object of type mappingproxy is not JSON serializable` |
| `node-03-tui-audit` | failed | `dispatch_failed` | same |
| `node-05-extensions-audit` | failed | `failed` | `Process exited early: gddp-node-receipt missing` |
| `node-07-instructions-audit` | running | `running` | — |
| `node-09-portfolio-audit` | **no job row** | — | — |

**Results rows for audit jobs: 0.** The evaluator has produced no verdict for any audit node.

So the evaluator-timing problem in §1 was never the binding constraint on this run. Two nodes never
dispatched, one died on a missing CLI, one is stuck, and one was never enqueued. The droid-side
heartbeats reporting "4/5 audits complete, no stall or error" were Factory's view of its own mission;
GDDP's ledger recorded failure or nothing for all of it.

**Both dispatch bugs are already fixed and committed:**

```
40a6905 fix(mission): thaw MappingProxyType before mission.md JSON serialization
a44d2af fix(mission): use gddp receipt instead of bespoke gddp-node-receipt
```

with a dated regression test — `test_projection_serializes_frozen_nodepacket_criteria_without_mappingproxy_error`.
This is the `factory_mission` adapter's first contact with real work: it hit two genuine bugs in
sequence and both were closed. The failed rows are the record of that, not decay.

**Operator actions, in order:**

1. `node-07-instructions-audit` is stuck in `running` with no terminal status. Decide whether to
   reconcile or fail it — nothing will move it on its own.
2. `node-09-portfolio-audit` has no job row. Determine whether it was never enqueued or enqueued
   elsewhere.
3. Re-dispatch the four audit nodes now that `40a6905` and `a44d2af` are in. That is the real test
   of §1–§3, none of which this run reached.

## 9. Also noted

`pi` 0.84.1 repaints the full viewport on large tool results — measured 320 KB of terminal writes in
10s (~4–5 full frames/sec on a 165×50 pane) against a ~650 B/s baseline, triggered by tool results
landing rather than by any timer. `npm view` confirms 0.84.1 is latest, so there is no upgrade path.
Narrowing the pane is the cheap mitigation. `terminal.clearOnShrink` is real but defaults to `false`
and *adds* redraws — not the cause, and not the fix.
