# Provisional status and frontier advance

Active contributors: Saboor

## Purpose

Provisional flow separates scheduler momentum from human-owned graph truth. A qualifying evaluation may mark a node `provisional`, which satisfies dependencies, while `complete` remains a human-only decision.

## Provisional promotion

`scripts/runtime/heartbeat/reconciler.py` always routes evaluated work to `awaiting_review`, then calls `maybe_mark_provisional()` in `scripts/runtime/heartbeat/provisional_gate.py`. Promotion requires:

- combined verdict `pass`;
- `integrity.intent_preserved` equal to true;
- `integrity.graph_integrity_preserved` equal to true;
- no integrity request for human review.

Confidence is not a permission threshold. A node with `human_gate: true` never auto-promotes. Terminal `complete` and `deferred` nodes are untouched, and failures to write provisional state are non-fatal. The evaluator itself does not edit graph files; the heartbeat reconciliation layer performs this scheduler-visible write.

## Frontier advance

Projects opt in with `execution_policy.frontier_auto_advance: true`. `scripts/runtime/heartbeat/frontier.py` finds `pending` nodes whose dependencies are all `complete` or `provisional`, excluding `human_gate` nodes. It atomically rewrites them to `ready` and inserts explicit tagged dispatch events into the event ledger.

The frontier skips nodes with active jobs and nodes that already have a pending frontier event. It takes a status snapshot at tick start, so one invocation advances one graph layer. The heartbeat checks the frontier before planning and again after evaluation finalization, ensuring newly provisional work can produce the next dispatch event without waiting for unrelated intake.

If a human rejects a provisional dependency back to `ready`, dependency satisfaction is recomputed from the live graph and the dependent is blocked at scope on its next planning pass.

## Base chaining

A provisional dependency's commit may not be present in the checkout's current `HEAD`. `_chained_base()` in `scripts/runtime/heartbeat/runner.py` therefore bases the dependent on the latest recorded result commit for one provisional dependency. Complete dependencies use `HEAD`.

Dispatch is deferred when the provisional dependency has no recorded result commit. More than one provisional dependency is refused because the runtime has no implicit merge mechanism; a human must merge or accept first.

## Gate tokens

`scripts/runtime/gates.py` writes `.gddp/gates/<node-id>.token` in the target checkout when a node becomes provisional. The JSON token contains the node id, issue time, and, when available, a receipt path and SHA-256. Writes use a unique same-directory temporary file followed by atomic replacement.

Gate tokens are mission admission evidence, not lifecycle truth. Readers reject absent, corrupt, or node-mismatched tokens. Provisional promotion and frontier advance can self-heal a missing token from stored receipt evidence. Human rejection or deferral revokes the token so mission dependents re-block.

## Key files and modification points

- `scripts/runtime/heartbeat/provisional_gate.py` — eligibility and graph status write.
- `scripts/runtime/heartbeat/frontier.py` — pending-to-ready transition and event injection.
- `scripts/runtime/heartbeat/runner.py` — provisional base chaining.
- `scripts/runtime/heartbeat/scope_checker.py` — satisfied dependency statuses.
- `scripts/runtime/gates.py` — token write, read, validation, and revocation.

Change promotion policy only in `provisional_eligible()`. Change frontier opt-in or duplicate rules in `advance_frontier()`. Base-composition work belongs at `_chained_base()` rather than in adapters.

See [Heartbeat](../systems/heartbeat.md), [Node and graph truth](../primitives/node-and-graph.md), [Gate token](../primitives/gate-token.md), and [Human review](human-review.md).
