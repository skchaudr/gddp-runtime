# Heartbeat orchestrator — build plan for trial 1

Written 2026-09-04. Follows the ChatGPT recommendation appended to
`orchestrator-topology-research-prompt.md` (Option C: event-driven wake plus
periodic backstop, bounded waits after interventions) and the trial contract in
`prefix-cache-orchestrator.md`.

This is a plan against the runtime as it exists today, with every citation
checked this session. Where the trial contract assumed a surface that is absent,
this plan says so and sizes the build.

---

## 0. The ownership rule that shapes everything

Sleep is a context wipe, which for a per-turn transport means the process ends.
A worker held inside the orchestrator's own session ends when the orchestrator
sleeps. Two consequences follow, and they decide the architecture:

1. **Workers are separate GDDP attempts.** Each worker gets its own attempt dir
   under a spool root, its own pid, its own `events.jsonl` / `exit.json`. They
   outlive orchestrator sleep, and wake N+1 can read them.
2. **The orchestrator allocates and stops.** It decides *which* nodes run,
   *how many* workers each gets, and *whether the cut is right*. Node
   implementation belongs to the dispatched executor attempts.

The alternative — orchestrator holds its workers as subagents — forces the
session to stay alive for the length of the work. That is Option A, and Option A
already produced the 120k–180k context balloon and the role drift into
researching GDDP.

This also settles the `native_subagents=False` declaration on
`cursor_cli_adapter.py:183`: it stops mattering, because the orchestrator's
workers arrive through dispatch rather than through a subagent tool.

---

## 1. The loop, mapped to code that exists

```
launchd StartInterval <operator-set per run; the plist's 300s is the
  inherited plumbing pulse, an arbitrary agent pick — see below>
  → runner.run_heartbeat()                    runner.py:142
      phase 0  reconcile_sessions()           runner.py:191   [exists]
      phase F  advance_frontier()             runner.py:201   [exists]
      phase O  orchestrator wake              ← NEW
      phase A  _plan_dispatches()             runner.py:218   [exists]
      phase B  _execute_dispatches()          runner.py:232   [exists]
      phase C  _record_outcomes()             runner.py:238   [exists]
      phase E  evaluation finalize            runner.py:244   [exists]
```

One wake per tick, inserted between frontier advance and dispatch planning. The
orchestrator reads reconciled state (phase 0 just refreshed it), writes a
decision, and phase A executes that decision through the existing reservation
and capacity path.

The pulse mechanism already exists and is already external: launchd fires the
runner on an interval (`deploy/mini-heartbeat/launchd/com.gddp.heartbeat.plist:77`).
GDDP is a poll-based reconciliation loop today, so Option C matches the runtime's
existing shape rather than adding a new one.

The interval is set per run, by the operator or by the orchestrator; this
plan asserts no default. The 300s in the plist predates the orchestrator —
it was chosen for the reconciler's plumbing pulse. When the operator fixes a
run's interval, that value wins. When the operator sets nothing, the
orchestrator sets its own wait through `next_wake_s` on the decision
receipt, and the pack carries the evidence for the estimate: worker ages,
event cadence, evaluator and gate waits.

### Wake → act → wait → sleep, per cycle

| Step | Mechanism today |
| --- | --- |
| Wake | New heartbeat phase assembles a pack and dispatches one fresh `cursor_cli` attempt |
| Act | Model emits `decision.json` inside its attempt dir |
| Wait (optional) | Same turn stays alive only while its own action has a pending immediate consequence |
| Sleep | Turn ends; `exit.json` written; context gone |

Fresh context costs one line: omit the `--resume` token. `build_argv` adds
`--resume` only when a token is present (`cursor_cli_adapter.py:309`), and
`Continuity` defaults to `FRESH`. So statelessness is the default path, and
persistence would be the thing requiring work.

---

## 2. What the trial needs built

Ranked by whether a trial is possible without it.

### G1 — Decision receipt + applier  *(blocking)*

Today an orchestrator decision has no representation and no path to effect.
Dispatch is driven by rows in the `events` table, claimed and classified in
`_plan_dispatches` (`runner.py:345`).

Build: a typed `decision.json` written by the wake, and an applier that
translates it into event rows, mirroring `frontier._inject_dispatch_event`
(`frontier.py:283`). Phase A then plans and dispatches them unchanged, and
`max_concurrent_jobs` enforcement at `runner.py:487` stays authoritative — the
orchestrator advises, the reservation transaction decides.

Closed action vocabulary, per the trial contract:
`hold`, `dispatch`, `slice`, `reduce`, `steer`, `replace`, `escalate`.

Shape follows ChatGPT's decision-receipt point — the rationale is the payload,
because the next wake has no memory of why:

```json
{
  "wake_id": "…",
  "action": "slice",
  "node_id": "…",
  "from": 3, "to": 6,
  "reason": "two independent implementation slices plus verification",
  "expect": "independent progress on both slices",
  "surfaces": {"worker": "ok", "plumbing": "ok", "node": "coarse", "graph": "ok",
               "evaluator": "idle", "human_gate": "2 waiting"}
}
```

These receipts accumulate on disk. They are the operational continuity that
replaces held inference state, and they are inspectable in a way a compacted
transcript is not.

### G2 — Health pack assembler  *(blocking)*

No aggregate frontier API exists. `get_ready_nodes()` returns full `NodeData`
from per-node YAML (`graph_reader.py:279`), which is far more than a pack wants.

Build one function returning six rows, all from cheap reads:

| Surface | Source |
| --- | --- |
| Worker | attempt dirs: `events.jsonl` mtime, `exit.json` presence, pid liveness, age |
| Plumbing | handle minted, session/pid alive, `result.json` movement, return routed |
| Node | advised N vs wall-time vs event cadence for the node under attention |
| Graph | status counts + ready ids from `project.yaml`; deps via `SATISFIED_DEP_STATUSES` (`scope_checker.py:28`) |
| Evaluator | `executor_sessions.state` in `collected` / `evaluated`; `results` rows |
| Human gate | `jobs.queue_state = 'awaiting_review'` |

Evaluator and human gate stay as their own rows. Plumbing means the pipe's
health — handle minting, liveness, artifact movement, return routing. Plumbing
anomalies earn a retry on the same pipe or a flag; control-plane redesign
mid-run belongs to the operator.

Pointers and counts only, matching the evaluator's policy in
`build_canonical_pointers` (`context_builder.py:15`). Blobs stay on disk.

### G3 — Worker budget in the packet  *(blocking)*

`advised N` has zero representation anywhere. Grep for
`worker_budget|advised|max_workers|fan_out` across `scripts/` returns only
evaluator thread-pool sizing. Pi's "up to 5 concurrent" lives as English prose
inside `_PACKET_PREAMBLE` (`pi_rpc_adapter.py:97`).

Build: a `worker_budget` integer on the dispatch envelope, rendered into the
executor's prompt. Without it, `dispatch N` / `slice` / `reduce` are opinions the
runtime discards, and the orchestrator's central decision goes nowhere.

### G4 — Orchestrator preamble  *(blocking)*

`_CURSOR_PREAMBLE` (`cursor_cli_adapter.py:100-120`) says
"You are the only agent working this node" and instructs implementation. Correct
for an executor, opposite of an allocator.

Build: a second preamble, byte-stable for the whole run, fed through the
existing `session_prompt.build_turn_prompt` (`session_prompt.py:111`), which is
already transport-neutral. One prompt stack, two preambles.

### G5 — Per-dispatch model  *(small, enables the trial config)*

`self.model` resolves once from `GDDP_CURSOR_CLI_MODEL` at adapter construction
(`cursor_cli_adapter.py:156`). One env var covers every `cursor_cli` dispatch, so
an orchestrator on one model and executors on another needs the model to travel
per dispatch. The plumbing is already there — `command={"model": …}` flows
through `dispatch()` (`cursor_cli_adapter.py:219`); the value just needs to come
from the dispatch rather than the environment.

### G6 — Wake attempts stay outside the node job ledger  *(design)*

An orchestrator wake is an attempt with no node to satisfy. Recording it as a
job would consume `max_concurrent_jobs` and mix allocator turns into a node's
attempt history. Give wakes their own spool root and session kind, keeping
`jobs` and `executor_sessions` about node work.

---

## 3. What stays untouched

Confirmed present, reused as-is:

- Pulse mechanism — launchd interval, operator-set per run (no default asserted)
- Fresh-context dispatch — `Continuity` defaults to `FRESH`
- Attempt spool, `events.jsonl`, `exit.json`, `result.json` — `local_attempt.py`
- Preemptive cancel — `cancel_attempt`, `cursor_cli_adapter.py:250`
- Capacity ceiling — `runner.py:487`
- Cache + coverage measurement — `prompt_cache_report.json` (`prompt_topology.py:306`),
  `context_coverage.json` (`local_attempt.py:552`)
- Evaluator, verdicts, receipts, human review drain

---

## 4. Steer, resolved

`cursor_cli` declares `midturn_steering=False` (`cursor_cli_adapter.py:181`),
and for a heartbeat orchestrator that declaration is a fit rather than a
limitation: sleep *is* the steer boundary. `steer.jsonl` gets drained into the
next wake's pack, so an operator message lands on a fresh, fully-assembled
cycle. Worst-case steer latency equals the pulse interval.

Mid-turn steer into a long-running *executor* remains a `pi_rpc` capability
(`pi_rpc_adapter.py:612`) and stays available for executor attempts.

---

## 5. Token budget, stated honestly

`cursor-agent` exposes no max-input-token flag. So "up to X tokens" is a
**measured target**, read from `prompt_cache_report.json` and
`context_coverage.json` after each wake, enforced by keeping the pack pointer-only
and counts-only. Target ≤50k for the pack; treat a wake above that as a signal
that the assembler started pasting instead of pointing.

Prefix layout, per the caching argument:

```
orchestrator contract  (byte-identical all run)   ─┐
run instructions + budget                          ├─ reusable prefix
project pointers       (byte-identical all graph)  ─┘
─────────────────────────────────────────────────
six health rows        (moves every wake)
recent decision receipts
operator steer
```

A fresh process keeps cache benefit as long as those leading bytes stay
identical, which is the point ChatGPT made against B's efficiency claim.

---

## 6. Trial 1 configuration

One local project, one ready node.

| Role | Model | Why |
| --- | --- | --- |
| Orchestrator | `cursor-grok-4.6-high` | Judgment on a small pack; fast; disciplined multi-step |
| Executor | `composer-2.5` | Implementation throughput on a bounded node cut |

Model strings verified against `cursor-agent --list-models` this session. Note
`cursor-grok-4.6` alone is absent — effort suffix is required
(`-low` / `-medium` / `-high` / `-xhigh`, each with a `-fast` variant).
`composer-2.5-fast` also exists.

### Sequence

1. Heartbeat tick finds a ready node.
2. Wake 1: pack shows one ready node, zero in-flight, capacity free. Decision:
   `dispatch` with a worker budget.
3. Applier injects the event; phase A reserves; phase B dispatches one
   `composer-2.5` executor attempt.
4. Wake 2..k on subsequent ticks: pack shows the attempt's age, event cadence,
   and exit state. Decisions: `hold` while healthy, `slice` / `reduce` /
   `replace` / `escalate` otherwise.
5. Executor finishes → reconciler collects → evaluator runs → `awaiting_review`.
6. Wake k+1 sees the human-gate row occupied and holds.

### Success criteria

- Every wake stayed inside the action vocabulary
- Zero drift into researching GDDP or implementing the node
- Pack held under target; prefix reuse visible in `prompt_cache_report.json`
- Fan-out arrived as a number with a recorded reason
- Each dispatched executor left an attempt handle
- Wake k+1 reconstructed the situation from receipts plus pack, with no held
  inference state

### The decisive comparison against B

Per ChatGPT: given equal access to GDDP state, does carrying and compacting the
prior inference improve the next decision's quality or speed? Evidence for B
would be C repeatedly holding the facts while failing to recover the causal
situation. Evidence for C is the run above completing without that failure.

---

## 7. Build order

1. G2 pack assembler, with a `--dry-run` that prints the pack and exits.
   Reviewable before a single token is spent.
2. G1 decision schema plus applier, tested against injected events.
3. G4 orchestrator preamble.
4. G3 worker budget through the envelope.
5. G5 per-dispatch model.
6. G6 wake spool root.
7. Wire the phase into `run_heartbeat`, behind an env flag, default off.
8. Trial.

Steps 1–2 carry the design risk. Steps 3–7 are wiring. The bounded-wait
refinement stays deliberately last: strict sleep first, and add the wait once a
wake demonstrates a decision whose consequence lands inside seconds.
