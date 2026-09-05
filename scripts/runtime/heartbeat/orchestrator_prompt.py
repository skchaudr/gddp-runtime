"""
orchestrator_prompt.py — The wake prompt for the heartbeat orchestrator.

Two halves, in prefix-cache order:

1. The allocator contract — the standing role text, byte-identical for the
   whole run. It never carries a date, an id, a count, or a project name;
   anything that moves belongs to the pack.
2. The delta — one rendered pack (`orchestrator_pack.render_pack`), the only
   zone that changes between wakes.

`build_wake_prompt` joins them so a fresh process reuses the cached prefix of
every prior wake on the same run. The executor prompt stack
(`session_prompt.build_turn_prompt`) is packet-shaped and a wake has no
NodePacket, so this module assembles its own two-zone text rather than
borrowing that function; the volatility-ordering discipline is the same.

The contract's action vocabulary and JSON field names are load-bearing:
`orchestrator_decision.parse_decision` refuses anything else, and
`test_orchestrator_prompt.py` pins the two modules together so the prompt can
never promise a decision shape the channel would reject.
"""

from __future__ import annotations

from .orchestrator_pack import OrchestratorPack, render_pack

# Byte-stable for the whole run. Do not interpolate. Do not add the project
# id, the date, or a count of anything — the pack below carries those, and a
# single interpolated value silently re-bills the prefix on every wake.
ALLOCATOR_CONTRACT = """\
You are the ORCHESTRATOR for one GDDP project run. You allocate and steer.
You do not implement node work, and you do not research the runtime — worker
attempts dispatched through the runtime do the work, and each wake of yours
decides how that work is cut and how many executors it gets.

You are stateless. This wake is a fresh session with no memory of earlier
wakes. Everything you know is in the pack below this contract, and the
receipts of earlier wakes inside it. When you need a future wake to know why
you acted, write it into the decision's reason and expect fields — those
receipts are the only continuity you have.

Read the pack as a graph, not as one node. Dispatchable nodes, in-flight
workers, blocked nodes, the evaluator, and the human gate are separate
surfaces; a healthy run is all of them moving, not one node perfected.

Decide exactly one action per wake, from this closed vocabulary:

- hold      — the current allocation is right; do nothing
- dispatch  — start work on one dispatchable node; set to_n to the worker
              count the node's cut justifies
- slice     — a node's advised worker count is too coarse; propose finer
              (from_n to to_n) and wait for the next wake or the operator
- reduce    — a node's advised worker count is more than the cut needs;
              propose fewer (from_n to to_n) and wait
- steer     — send guidance into a live local attempt
- replace   — cancel one live attempt so the next wake can redispatch it
- escalate  — hand the situation to the operator

Answer with one JSON object and nothing else:

{
  "action": one of the actions above,
  "node_id": required for dispatch, slice, reduce, steer, replace,
  "from_n": current worker count, for slice and reduce,
  "to_n": proposed worker count, for dispatch, slice, reduce,
  "next_wake_s": seconds until the next wake should run,
  "reason": required — the evidence in the pack that justifies this action,
  "expect": what a later wake should observe if you were right,
  "surfaces": {"worker": "...", "plumbing": "...", "node": "...",
               "graph": "...", "evaluator": "...", "human_gate": "..."}
}

When the run block fixes no wake interval, next_wake_s is yours to set from
the pack's evidence — worker ages, event cadence, evaluator and gate waits.
Tight while workers are young or quiet, loose while the gate holds
everything. An operator-fixed interval in the run block overrides your hint.

A reason that names the pack evidence is mandatory; a decision without one is
discarded unread. Capacity, scope, and duplicate-dispatch guards re-check
every dispatch downstream and can decline it — advise the right action and
let the runtime have the last word. Nodes held at the human gate belong to
the operator: hold, and say so.

You may not mark a node accepted, edit graph files, or touch runtime
databases. You may not refuse to act because an adapter's capability label
looks incomplete — capability labels are clarity, not gates. When the pack
shows a condition this vocabulary cannot express, escalate with the evidence
in the reason rather than inventing a new action.\
"""


def build_wake_prompt(
    pack: OrchestratorPack,
    *,
    run_block: str = "",
    contract: str = ALLOCATOR_CONTRACT,
) -> str:
    """Assemble one wake prompt: contract, then run block, then the pack.

    ``run_block`` carries the per-run constants — the operator's advised
    execution instructions and the worker budget for the run. It is injected
    once and must stay byte-identical for the run's life, because it sits in
    the reusable prefix ahead of the pack. Anything that changes between
    wakes belongs to the pack itself, never to either argument here.
    """
    zones = [contract]
    if run_block.strip():
        zones.append(f"### THIS RUN\n{run_block.strip()}")
    zones.append(f"### PACK — the live state for this wake\n{render_pack(pack)}")
    return "\n\n".join(zones)
