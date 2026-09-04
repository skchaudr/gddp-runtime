# Research prompt — GDDP orchestrator topology

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
