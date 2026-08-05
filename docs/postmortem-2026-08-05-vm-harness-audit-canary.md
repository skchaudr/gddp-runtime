# Post-mortem: vm-harness-audit canary (2026-08-04 → 05, khoj-38)

## What happened

First droid-executed graph through the full GDDP loop. 5/5 nodes provisional,
all executed by `droid exec` (Grok 4.5 via Hermes :8645), fully autonomous
after the systemd timer was armed (~90 min wall for 5 nodes incl. fires).
Four runtime bugs + one platform bug surfaced and were fixed upstream mid-run:

1. `185e6fe` — YAML `Key:`-prefixed constraint scalars parse as dicts; verifier crashed
2. `66f4ae5` — frontier check ran before evaluation finalize; provisional landed too late, project went dormant
3. `9991c8e` — GraphReader cache made the post-finalize re-check read stale state
4. `727bb7a` — droid sessions labeled `local_subprocess`; failure-retries silently re-routed to pi
5. systemd unit — default `KillMode=control-group` reaped freshly-dispatched executors at tick end (fix: `KillMode=process`, upstreamed in `d45afaf`)

## What went well

- Verify-by-doing throughout; every fix landed in code, not as a workaround — all future graphs benefit
- Doctrine held under pressure: no graph surgery, human gates intact, retries re-attempted unchanged nodes
- VM prep (env, keys, proxies, resolver fixes) meant dispatch worked on first inject
- The loop found its own bugs — the canary audited GDDP while GDDP audited the VM

## What didn't: the delegation failure

Ran the whole night serially in one session. Concrete costs:

1. **No quality layer on droid's output.** Reports were checked for existence
   and verdicts, not content. Nobody verified in real-time that node-04's
   "PTY transcript" was a real PTY capture, or that node-02's extension
   inventory wasn't hallucinated. The evaluator's binary lane can't judge
   that; a parallel read-only reviewer per report could have. This is the
   single biggest miss — we proved the loop, but only half-proved the work.
2. **Serial diagnosis under fire.** Each bug was diagnosed, fixed, tested,
   and deployed by one thread while the loop waited. Diagnosis needed live
   VM state (correct to keep in-session), but fix implementation + test
   could have been delegated with a crisp repro while loop-watch continued.
3. **The session hunt** (lost thread) was 30+ min of serial searching that
   fanned out naturally into 3 independent searches (pi stores / Factory /
   remote machines).
4. **Relay-style collaboration.** Claude participated via operator
   copy-paste between panes — lossy, unscoped, and it produced unverifiable
   hypotheses (one right: KillMode; one ghost: the "fix" that never landed).
   pi-subagents/intercom existed the whole time and would have given each
   helper a bounded scope with verifiable outputs.

## Where serial was correct

- The bug chain was genuinely sequential: each bug only became reachable
  after the previous fix unblocked the loop.
- Live-state diagnosis required the ssh/session context; remote guessing
  without it is what produced the ghost fix.

## Open gaps found (not yet fixed)

- **`gddp project validate` still passes non-string criteria/constraints.**
  The verifier tolerates them now, but the validator should reject them at
  authoring time — that's the layer where the error is cheapest.
- Retry budget semantics for executor-failure redispatch are unclear
  (attempts 0–3 fired despite `retry_budget: 2`); worth pinning down.
- Droid observability: no live view into a running exec. `droid exec -o
  stream-json` into the spool would give the heartbeat/operators a tail-able
  stream.

## Lessons → execution graph run

1. **Per-node reviewer fanout is now standard.** As each node lands
   provisional, spawn a read-only reviewer (cheap model — doctrine tier b)
   to grade report content against criteria. Evaluator judges binaries;
   reviewers judge substance; human judges acceptance.
2. **Fire protocol:** diagnosing session keeps loop-watch; fix + test
   delegate to a subagent with a written repro; Claude/Codex get scoped
   assignments via intercom, not relay paste.
3. **Arm the scheduler before dispatch 1.** Manual ticks deferred the
   KillMode bug to node-04; armed from birth it would have fired on node-01,
   cheaper.
4. **Semi-autonomy dial is per-project policy already** (`frontier_auto_advance`,
   human-gated acceptance) — monumental projects get gates, binary-criteria
   graphs get flow. Tonight proved both halves work.
