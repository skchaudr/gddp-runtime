# 106 — The orchestrator has no context contract; the evaluator does

Not a session handoff. This is a diagnosis note from reading three live orchestrator
session logs (2026-08-20 / 08-23 / 08-24) plus the adapter and evaluator source.
No code was changed. Everything below points at files in this repo.

## What we were chasing, and what it actually was

The visible problem was cost and a persistent orchestrator carrying 120K–180K of
context. The assumption was that Pi's compaction was the culprit — it compacts too
late, so build something that compacts earlier.

That was the wrong layer. The orchestrator's context is large because it spends its
run discovering what GDDP is. In the 08-20 session it made **29 `read` calls and 120
`bash` calls, against 16 `subagent` dispatches**. What it read: `context.md`,
`vocabulary.md`, `LOOP.md`, the invariants doc, the node and evaluator entity specs,
the runtime decision-loop spec, the architecture doc, and several design essays. The
bash calls were directory walks, file-tree listings, and line counts over
`scripts/runtime/`.

It is not an orchestrator that got heavy while orchestrating. It ran an unbounded
research task, and dispatching was the small part.

## The gap, stated plainly

The evaluator was given a context contract. The orchestrator was not.

**Evaluator** (`scripts/runtime/verification/semantic/`):

- `context_builder.py::build_canonical_pointers()` hands it a bounded set of file
  *paths* — readme, project brief, invariants, foundational node, direct
  `depends_on`/`unlocks` neighbors. The docstring states the rule: *a read call is
  evidence, an embedded blob is not.* Target-repo `AGENTS.md` is explicitly never
  included. Missing files are marked `UNAVAILABLE` rather than dropped.
- `prompt.py` orders the prompt in four zones, least to most volatile: protocol,
  project, node, attempt. Each zone is internally byte-stable; the zones are never
  merged, because one combined `json.dumps(sort_keys=True)` would hoist
  `deterministic_result` ahead of `graph` and bust the cached prefix on every
  evaluation. That failure mode is written down in the comment.
- `orchestrator.py::_compute_context_coverage()` and `_extract_accessed_paths()`
  record which pointers were actually opened. Asserted on the receipt in
  `test_orchestrator.py`.

**Orchestrator** (`scripts/adapters/pi_rpc_adapter.py`):

- `_PACKET_PREAMBLE` (L72–112) — about 40 lines of behavioral prose. It says how to
  act: dispatch workers, don't implement, run a watcher, close with reviewers. It
  says nothing about what the project is.
- No pointer list. No zone ordering. No coverage record.

So it's told what to do and left to find out what it's doing it to. The instructions
even say workers investigate and the orchestrator does not — but with no context
handed in, investigating is the only way to start. The equipment wins over the
instruction.

Worth being precise: **neither** agent is briefed. The evaluator opens its own
pointer files too. The difference is that the evaluator's excavation is fenced to
five or so named paths and measured afterwards, while the orchestrator's is
unbounded and nobody is counting.

## Why compaction can't fix this

If you summarize away the docs the orchestrator just read, it has no durable copy of
its own instructions, so it reads them again. You'd be paying a summarizer to forget
things the agent immediately re-fetches. That's why the ceiling tuning kept not
landing — it was adjusting how fast to forget, when the problem is that the
orchestrator has to rediscover who it is every time it wakes up.

## The second-order version of the same problem

When the runtime doesn't own orchestration efficiency, the harness pays for it. Pi's
native compaction fires at `contextWindow - reserveTokens` (default 16384), so around
184K on a 200K model. The orchestrator therefore carried near-ceiling context on
every single tool call for the life of each run.

| session | requests >1K ctx | p50 ctx | p90 ctx | max | total input |
|---|---|---|---|---|---|
| 2026-08-20 | 205 | 176,894 | 233,371 | 245,760 | 34,365,343 |
| 2026-08-23 | 147 | 120,144 | 174,590 | 185,471 | 16,172,338 |
| 2026-08-24 | 81 | 116,216 | 159,252 | 160,964 | 8,906,047 |

Those totals are floors, not totals. The 08-20 run had 14 failed calls — 6 request
timeouts, 6 fetch failures, 1 connection error, 1 rate-limit rejection — plus 3
aborts. A failed request records no usage, so each of those sent a full context and
appears nowhere in the numbers above. Timeout probability climbs with context size,
so the blowup manufactures its own retries, each charged at the largest size the
session had reached.

## Fixes, cheapest first

1. **Call `build_canonical_pointers()` from the orchestrator preamble.** The function
   already exists and is already tested. The orchestrator just never calls it. This is
   the smallest diff with the largest effect.
2. **Make the orchestrator model explicit at the call site.** `_DEFAULT_MODEL =
   "xai/grok-4.5"` at `pi_rpc_adapter.py` L62 is a silent hardcoded fallback, and the
   prime suspect for a chosen cheap model not taking effect.
3. **Reorder the preamble stable-first**, porting the zone pattern from
   `semantic/prompt.py`. Port the pattern, not the code.
4. **Add `.pi/settings.json` to this repo** with `compaction.reserveTokens` sized
   against the pinned orchestrator model's window. That gives an absolute ceiling with
   no code. Pi's `ExtensionContext` exposes no `settingsManager`, so static config is
   the only route — an extension cannot set this at runtime.
5. **Borrow the coverage measurement** so orchestrator context growth is observable
   live instead of reconstructed from session logs after the fact.

`_DEFAULT_IDLE_TIMEOUT_S = 43200.0` (L70, 12h) is deliberate and correct for
cross-packet continuity — it is not a bug. But it does mean nothing the orchestrator
excavates is ever released, which amplifies items 1 and 3.

## On the harness side, for the record

Native Pi compaction is in-place: it appends a `CompactionEntry` and rebuilds from
`firstKeptEntryId` in the same session. It does not end the session — that behavior
is specific to oh-my-pi.

The 08-25 interruptions in `~/.pi` had two independent causes, both already removed
in that repo at `d538b20`. `refutation-verifier.ts` returned `{systemPrompt}` without
spreading `event.payload`, wiping `messages` and `model` from the request — that is
the red-error-with-no-agent-response failure, and it was not compaction.
`early-compaction.ts` called `ctx.compact()` on `turn_end`, which fires at tool-loop
boundaries *inside* a live run, rewriting history underneath the running loop.

If harness compaction is ever rebuilt: trigger on `agent_settled` ("fired after an
agent run has fully settled and no automatic retry, compaction, or queued
continuation will run"), guard with `ctx.isIdle()` and `ctx.hasPendingMessages()`
plus a cooldown, and leave native's `threshold` trigger in place as a backstop rather
than cancelling it. No auto-continue is needed because nothing is in flight at that
point.

Do not port oh-my-pi's compaction subsystem on the strength of the prior handoff's
description of it. That description was never checked against source — oh-my-pi is
not on this machine, `~/.omp` is only its data directory. The one local measurement
available deflates its cheap-tier claim: `~/.omp/snapcompact-savings.jsonl` holds
three records totalling 2,442 saved tokens across its entire logged life.

But the standing conclusion is that the harness should not be rebuilt to bail out the
runtime. Fixes 1–3 are the real work.

## Two corrections, so they aren't inherited

Earlier in the session I argued that the context window was *not* the expensive part,
on the grounds that most input tokens were cached reads. That was wrong. A cache
discount is per token and you pay it on every request, so 205 requests at a 177K
median is the dominant term regardless. Compacting at a sane ceiling would have cut
that run's input tokens roughly 4x.

I also claimed retries weren't involved, citing tool-call counts. Tool-call counts
cannot show that — a retry resends context without adding a tool call. See the 14
failed calls above.

## Not yet read

`docs/proposals/pure-orchestration-not-execution.md` exists and was never opened this
session. Read it before acting on the fix list; it may already specify some of this.
`.handoffs/097-prefix-cache-prompt-templates.md` is the prior prefix-cache work and is
presumably where the evaluator's zone ordering came from.
