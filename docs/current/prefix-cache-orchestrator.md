# Prefix-cache orchestrator — trial contract

Operator description, 2026-09-03. This is the thing to launch, not a new
runtime. Four-zone prompt + coverage + steer already exist. The standing
role does not match.

## What it is

A **stateless, graph-aware allocator**. Each cycle is a short, prefix-stable
prompt plus a small live delta. It decides how work is cut and how many
executors run, then stops. It does not implement the node. It does not keep
a chat across nodes.

Different from:

- **one-turn-per-node executor** — that process *does* the node and dies
- **persistent-across-nodes executor** — that process accumulates node chat
  (today’s `pi_rpc` Fork A)
- **dumb liveness supervisor** — alive? / nudge? / escalate? only
- **Jules / remote async** — out of scope for this trial. Local runs are
  steerable. Remote observability is not a launch blocker.

Local checkout: every local executor that runs must leave an attempt handle.
That is accounting, not a gate.

## Standing prefix (byte-identical every cycle)

This is the only prose the model should see every time. It must not grow.

1. You allocate and steer. You do not implement. You do not research GDDP.
2. Graph-aware, not node-hyper-fixated. Neighborhood and frontier, not the
   node body.
3. Advised execution instructions for *this run* (injected once, stable for
   the run).
4. Subagent / executor budget for this run (a number, not a recipe).
5. Action vocab, closed:

   - `hold` — current cut is fine; do nothing
   - `dispatch N` — start N executors on the advised cut
   - `slice` — this node’s advised N is too coarse; propose a finer cut
     (e.g. 3 → 6) with why, then wait for the next cycle / operator
   - `reduce` — advised N is too much; propose fewer (e.g. 3 → 2)
   - `steer` — mid-run message into a live local executor
   - `replace` — kill + redispatch one local executor
   - `escalate` — operator; do not invent a new job type

6. You may not mark nodes accepted. You may not edit graph YAML. You may
   not refuse a run because an adapter’s capability label is incomplete.

## Per-cycle delta (the only thing that changes)

- Frontier: ready / in-flight / blocked counts, plus node ids — not YAML
- In-flight: attempt id, executor name, age, last event mtime
- Advised N for the node under attention, and wall-time so far
- Operator steer, if any

No worker transcripts. No prior-cycle narrative. No embedded file blobs
(pointers only — same rule as the evaluator).

## Prefix-cache rule

`protocol` + run instructions + budget stay byte-identical for the whole
run. `project` pointers stay byte-identical for the graph. Only the delta
zone moves. If a cycle needs a new fact, it is a pointer or a count, not a
paste.

Existing machinery: `session_prompt.build_turn_prompt` (protocol / project
/ node / attempt), `prompt_cache_report.json`, `context_coverage.json`.
Reuse those. Do not add a second prompt stack.

## What has to change before a trial is a trial of *this*

Today `_PACKET_PREAMBLE` in `scripts/adapters/pi_rpc_adapter.py` says the
opposite: orchestrator of *this node session*, not graph-level, persistent
across packets, fixed recipe (5 workers + watcher + four named reviewers).
Launching as-is trials Fork A, not this.

The tune is that protocol text (and a thinner “node” zone: frontier +
advised N, not full packet JSON). Heartbeat, dispatch, steer.jsonl, attempt
dirs stay.

## Trial

One local project, one ready node, `pi_rpc` or `cursor_cli` via override.
Steer mid-run. After the cycle, read `prompt_cache_report.json` and
`context_coverage.json`. Success is: prefix reused, actions stayed inside
the vocab, no research-into-GDDP drift, fan-out was a number not a
hardcoded review panel.

Jules / relay / remote progress is a later run, not this one.
