# Research prompt — GDDP orchestrator topology

The original message from Sab that lead to this prompt being written, and the eventual response by ChatGPT. 

--- 
 Do not take me too literal when you say "IT ONLY SEES:" and then literally
  only include mostly what I said, you are arbitrarily constraining it

  It monitors worker health, GDDP plumbing health (safe workarounds, quick
  fixes, or flagging for help), node health, and graph health -> these are
  all distinct things

  Whatever it's allocated context window is something WE determine, if all
  the above can be done with <100k tokens, great

  <50k tokens, great

  Then the difficult part; choose, do we compact and move it forward or start
  brand new, that's the big thing for me, we are balancing cost/efficacy

  This entire thing is about striving for excellent effinecy *and* impact,
  never sacrificing capability at great cost for great efficiency, and
  willingness to sacrifice SOME efficiency for great capability

  Maybe the orchestrator operates on a heartbeat like system

  It is woken up, it is given context, it makes decision, and it is pulsed
  again later

  If a worker goes down, the evaluator flags important details, etc, it
  ensures it makes the appropriate decisions,then back to sleep (sleep =
  context wipe, but maybe for short-term decisions it is allowed to do an
  appropriate 'wait' to ensure success of the next unblocking action needed
  to justify another sleep)

  I need to research and explore out of the various orchestator
  possibilities, which is more promising, our current setup, the setup we
  were working towards with frequent compacting with a reasonable context
  window, or a heartbeat style system ranging from strict sleeps to
  sleeps-with-some-waits

  Generate a prompt for me so I can have Grok web and ChatGPt process this
  and lay out the pros and cons and make a recommendation 

---

Copy everything below the line into Grok (web) and ChatGPT. Same prompt,
both models. Ask each for a recommendation, not a synthesis of the other.

---

You are advising on the control-loop topology for a **graph orchestrator**
in GDDP (Graph-Driven Development Process). GDDP is a human-in-the-loop
control plane: a DAG of **nodes** (units of project intent). A runtime
**heartbeat** dispatches work to **executors** (agent transports). An
**evaluator** judges returned work and writes a verdict receipt. Only a
human accepts a node; executors and evaluators never write graph truth.

I need you to compare **three live options** for the orchestrator — the
component that allocates work, watches health, and intervenes — and
recommend one for a first production trial. Do not invent a fourth
product. Do not propose a capability-gate that refuses dispatch. Do not
tell me to wait for a full observability platform.

## What the orchestrator is responsible for

Four distinct health surfaces. They are not the same thing and must not
be collapsed into “are the workers alive.”

1. **Worker health** — the agents actually doing node work (including
   subagents). Progressing, stalled, crashed, waiting, off-path.
2. **GDDP plumbing health** — the runtime that dispatches, persists
   attempts, routes returns. Safe workarounds, quick fixes, or flag for
   a human. The orchestrator may patch a stuck pipe; it may not redesign
   the control plane mid-run.
3. **Node health** — is *this* node’s attempt satisfying its contract in
   reasonable time, or is the cut wrong (too coarse / too fine / too many
   or too few executors)?
4. **Graph health** — frontier, dependencies, whether the run is still
   serving the graph or has become node-hyper-fixated / scope-expanded.

It is graph-aware. It is not the executor (it does not implement the
node). It is not the evaluator (it does not accept nodes). It is not a
dumb liveness ping.

It **is** allowed to decide fan-out: a node advised for up to N executors
might reasonably need 2, or a slice into 6, given time and progress. That
is a first-class decision, not a hardcoded recipe.

It **is** steerable on **local** runs (operator message mid-cycle). Remote
async executors (e.g. Jules: own sandbox, far from this VM, optional
relay) are **not** the focus of this trial and must not drive the
topology choice. Local execution must account for every executor that
runs. That is accounting, not a deny-list.

## Efficiency / capability doctrine (non-negotiable)

Strive for excellent **efficiency and impact**.

- Never sacrifice capability at great cost just to look efficient.
- Willing to sacrifice **some** efficiency for **great** capability.
- Context window size is **ours to set**. If the four health surfaces
  can be done well in <100k tokens, good. If <50k, better. Those are
  targets, not a moral argument that the orchestrator “should only see”
  a tiny checklist. Do not arbitrarily shrink its job to save tokens.

The hard operational question, every time context pressure appears:

> **Compact and continue this session, or start brand new?**

That is a cost/efficacy decision, not a purity decision. I want the
recommendation to treat that as the crux.

## Option A — current setup (persistent project orchestrator)

One long-lived agent process per project (Pi RPC “Fork A”). Nodes arrive
as packets / turns on the same session and the same worktree. Mid-turn
steer exists. A four-zone prompt is already built (stable protocol →
project pointers → node → volatile attempt) plus per-turn
`prompt_cache_report.json` and `context_coverage.json`. Compaction is
capped (~96k on the current preset).

Observed failure of this shape: the model used the session to *research
GDDP and reinterpret its job* instead of allocating workers. Context
grew to 120k–180k+; one session burned tens of millions of input tokens.
The standing instructions still describe a **node-session** overseer with
a fixed worker/reviewer recipe, and they explicitly say it is *not* the
graph-level orchestrator. So “current setup” is persistent + prefix
machinery + the wrong role text + proven drift.

Prefix cache only pays if the leading bytes stay identical. Persistence
helps cache *and* lets narrative / role-drift accumulate.

## Option B — frequent compact, keep the session

Same long-lived process as A, but we treat compaction as the product:
aggressively collapse back toward a canonical supervisor summary each
cycle (role, four health surfaces, frontier, in-flight handles,
intervention counts). Reasonable window (design for <100k, prefer <50k
if quality holds). The session continues; memory is the compacted
summary, not the raw transcript.

Questions I need you to answer for B:

- When does a model-written summary become a lie (lost fan-out rationale,
  lost plumbing incident, lost graph constraint)?
- Does prefix cache survive compaction, or does each compact bust the
  KV prefix and erase the cost argument for staying in-session?
- How do you decide compact-forward vs kill-and-fresh *inside* B?

## Option C — heartbeat / pulse (sleep = context wipe)

The orchestrator is not a standing conversation. It is woken on a pulse
(timer, worker-down, evaluator flag, operator steer, plumbing alarm).
It is given a assembled context pack. It decides. It goes back to sleep.

**Sleep = context wipe.** Next pulse is a new assembly, not a continued
chat.

A pulse may include a **short wait** before sleep: stay awake only long
enough to see whether the unblocking action it just took actually
unblocked (dispatch landed, steer absorbed, plumbing workaround held).
That wait is justified by the next action’s success, not by “keep chatting.”
Range to evaluate: **strict sleep** (decide and die) ↔ **sleep-with-wait**
(decide, brief confirm, then die).

This is closer to how GDDP’s **evaluator** already works and stays
stable: fresh process, pointer contract (paths not blobs), bounded tools,
typed receipt, coverage measurement. The evaluator does not accumulate
across nodes. I want the orchestrator to be able to use that *shape*
without becoming the evaluator.

Questions I need you to answer for C:

- What must be in the assembled pack so four health surfaces are real
  and not a cargo-cult checklist?
- What is the latency / miss cost if a worker dies between pulses?
- When is a wait-before-sleep worth it vs just pulsing again?
- How does prefix cache work if every pulse is a new session but the
  pack’s prefix is byte-identical?

## What I already know (do not re-derive as if new)

- Executors and the orchestrator are different jobs. One-turn-per-node
  and persistent-across-nodes are executor topologies. This question is
  the orchestrator’s topology.
- A prior “requires_capabilities / deny the run” idea is rejected.
  Labels on adapters are fine; refusing production runs is not.
- I will not wait for a magical live-observability layer. I want to
  trial an orchestrator against the current runtime (attempt dirs,
  events.jsonl, steer, coverage files, heartbeat).
- Human accepts nodes. Orchestrator may escalate. It may not flip graph
  status.

## Deliverable

For each of A, B, C:

1. How it handles the four health surfaces.
2. How it handles compact-vs-fresh (or why that question is N/A).
3. Cost shape (tokens, cache, idle time, miss/latency).
4. Failure mode that actually matches our history (role drift, context
   balloon, node-hyper-fixation, plumbing blindness).
5. What a **first trial** looks like in one local project / one ready
   node — smallest change, not a platform rewrite.

Then: **one recommendation** for the first trial, and the conditions
under which you would switch to a different option after evidence.
Be concrete. Cite general systems knowledge (prefix/KV cache, compaction
lossiness, wakeup/sleep control loops, evaluator-style stateless judges)
and apply it to this setup. If you assume something about GDDP that I
did not state, label it ASSUMPTION.

End with a short “do not do” list (things that look like rigor but
would delay a trial or shrink the orchestrator’s job into a ping).


----------------------------------------------------------------------------

## Reasoned Response: Try heartbeat-plus-wait

The evidence points pretty strongly toward C: heartbeat/pulse, with bounded waits when an intervention needs immediate verification.

The important correction is that this is not a conversational-memory problem. In a non-interactive orchestrator run, the question is whether retaining an inference context across control cycles improves the orchestrator’s alertness, availability, and decision quality enough to justify its cost and degradation risk.

Research and systems practice give us three useful findings.

First, long context is useful, but long-running context is not equivalent to better state awareness. Models degrade as relevant information competes with accumulated material, even when everything technically fits inside the context window. Compaction can restore usable context density, but summarization is lossy: causal details, constraints, and rationale are exactly the kinds of things that can disappear while the resulting summary still looks perfectly reasonable.

That matters for B because the valuable continuity isn’t “what did we talk about?” It’s operational continuity:

Why did I fan this node from 2 → 5 workers?
What plumbing anomaly did I just work around?
What result am I currently waiting to verify?
Why did I decide this apparent worker stall wasn’t actually a stall?

If B repeatedly compresses those decisions, the orchestrator’s future efficacy depends on a model-written representation remaining faithful. That’s a real liability.

Second, persistent context does have a genuine computational advantage through prefix/KV caching. Stable accumulated prefixes can make subsequent inference substantially cheaper. But compaction changes the prefix from the compaction point onward. You can preserve caching for stable instructions/tool definitions/project material before that point, but you don’t retain the full economic advantage of the old accumulated context after rewriting it.

That weakens the main efficiency argument for B relative to C, because C can also exploit prefix caching:

stable orchestrator contract
stable tools
stable project/GDDP pointers
-----------------------------  <- reusable prefix
assembled current state
recent events
current intervention state

A new process or inference cycle doesn’t inherently mean “no cache.” What matters to prompt caching is reusable prefix content.

Third, the systems analogy favors wake → observe current state → decide → act → sleep when the controller’s authoritative state exists outside the controller. Supervisors, reconciliation loops, schedulers, and controllers commonly operate this way. The controller doesn’t need to remain cognitively alive between events for the system to remain supervised.

And GDDP already gives you most of the machinery that makes that topology attractive: heartbeat, attempt state, events.jsonl, evaluator outputs, graph state, steering, coverage artifacts, executor handles, etc.

So C isn’t attractive because “fresh context is pure.” It’s attractive because the orchestrator can be fully reconstituted into an alert operational state when something requires its attention.

The pulse therefore shouldn’t be tiny. Give it whatever it actually needs to assess all four surfaces:

worker health + plumbing health + node health + graph health + recent consequential history.

If that’s 20k, great. If it’s 55k, fine. If experiments show that 90k materially improves decisions, use 90k. The optimization target is decision quality per cost, not minimum context.

Where I think your original idea gets especially strong is sleep-with-wait rather than strict sleep.

Suppose the orchestrator wakes because worker A appears stalled. It determines that the worker isn’t dead—the dispatch plumbing failed—and performs a safe retry.

Immediately wiping context is unnecessarily inefficient because the orchestrator already has the complete causal situation loaded. If confirmation should arrive in 10 seconds, keeping that inference episode alive long enough to observe whether the retry worked preserves useful situational continuity.

But once the retry succeeds and the worker is expected to spend 15 minutes implementing something, there is no corresponding benefit to retaining that context for 15 minutes.

So the boundary becomes operational:

Keep the current inference alive while its next useful observation is the immediate consequence of an action it just took. Otherwise sleep and reconstruct on the next meaningful event.

That produces something closer to:

worker-down / evaluator flag / plumbing event / timer / operator steer
                              │
                              ▼
                       WAKE ORCHESTRATOR
                              │
                    assemble operational state
                              │
                              ▼
                  assess all four health surfaces
                              │
                         decide / act
                              │
                  immediate consequence pending?
                       /               \
                     yes                no
                      │                  │
                 short wait            sleep
                      │
                    verify
                      │
                    sleep

The main weakness of C is therefore not lost conversational continuity. It’s whether your context assembler can reconstruct enough operational continuity.

That’s the empirical question.

For example, if the orchestrator previously chose six workers rather than three because of a particular decomposition hypothesis, the next pulse may need that rationale. If GDDP only records worker_count=6, C is informationally weaker than the continuing inference that made the decision.

But the answer doesn’t necessarily require retaining the inference context. You can persist the relevant control decision:

{
  "decision": "fan_out",
  "from": 3,
  "to": 6,
  "reason": "two independent implementation slices plus verification",
  "expect": "independent progress on both slices"
}

Now the next orchestrator receives the operational fact and its causal significance.

That is the piece I think most strongly separates B and C.

B says:

Preserve enough of the previous inference that the next inference remains effective.

C says:

Preserve the consequences and rationale of previous control decisions, then construct the next inference when supervision is required.

Given GDDP’s architecture, the second representation looks more natural and more inspectable.

I would therefore run C first, using event-driven wakes plus a periodic heartbeat as the backstop, and allow bounded waits after interventions.

I would compare it directly against B rather than spending much more time on A. A has already demonstrated the important pathology: 120k–180k+ contexts, enormous repeated input, and enough accumulated material that the orchestrator stopped behaving primarily as an orchestrator. That doesn’t prove persistence cannot work, but it gives B the burden of demonstrating that aggressive compaction actually fixes it.

The decisive experiment between B and C isn’t token count either.

It’s:

Given equivalent access to GDDP state, does retaining and compacting the previous inference materially improve the quality or speed of the orchestrator’s next control decision?

If C repeatedly wakes, reconstructs the situation correctly, catches worker/plumbing/node/graph problems, makes good fan-out decisions, and appropriately follows through on interventions, then persistence isn’t buying enough to justify itself.

If C repeatedly has the facts but nevertheless struggles to recover important causal situations that B handles naturally, then you’ve found evidence that continuous inference state itself has operational value, and B becomes much more interesting.

Based on what you’ve built so far, I’d expect C with bounded waits to win. It gives the orchestrator full capability when there’s something to orchestrate, lets context size be determined empirically, preserves short-lived situational continuity when it actually matters, and stops paying to carry an inference episode once that episode has ceased being operationally useful.
