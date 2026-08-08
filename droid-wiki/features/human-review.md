# Human review

Active contributors: Saboor

## Purpose

Human review is the authority boundary between runtime evidence and graph truth. Executors may finish, tests may pass, and the evaluator may return `pass`, but none of those facts completes a node.

## How work reaches review

Both return paths converge on `awaiting_review`:

- The mediated path in `scripts/runtime/return_router.py` evaluates a merged PR and writes a result row.
- The direct path in `scripts/runtime/heartbeat/reconciler.py` collects a commit or patch, pins the resulting commit for evaluation, writes the result, and marks the executor session evaluated.
- Mission results with incomplete, conflicting, or quarantined evidence bypass normal evaluation and park in review with the available evidence preserved.
- Evaluator crashes and unpinned-subject errors are also visible review records rather than reasons to strand a job.

`awaiting_review` counts as active in `scripts/runtime/heartbeat/scope_checker.py`, preventing duplicate dispatch while a human decision is outstanding. A qualifying pass may also make the graph node `provisional`, but the job remains in the review queue.

## Operator actions

The operator reviews the node's stated intent, returned commit or PR, criterion findings, integrity findings, provenance, context coverage, and receipt. The human may accept, reject for another attempt, defer, revise, split, supersede, or rewire the node. Graph changes are made through the graph control plane; runtime state is reconciled afterward.

The important distinction is:

- graph/node status records accepted project truth;
- job and queue status record the runtime handling of one execution attempt.

Changing a runtime job to `complete` does not change graph YAML. Conversely, the heartbeat's review reconciliation observes terminal graph status and drains the corresponding runtime job.

## `jobs_status.py`

`scripts/jobs_status.py` is the backend for runtime job reads and writes. It never writes graph/node status.

Useful surfaces are:

- `python3 scripts/jobs_status.py list --state awaiting_review` — list the human queue;
- `python3 scripts/jobs_status.py show <job-id-or-node-id> --full` — show evaluator reasoning, criterion and integrity findings, provenance, context coverage, decision history, and executor attempts;
- `python3 scripts/jobs_status.py results` or `results --all` — summarize receipt rows;
- `python3 scripts/jobs_status.py set <ref> <state> --reason "..."` — make an audited runtime state change.

A state change requires a reason and normally confirmation. Moving an `awaiting_review` job to runtime `complete` records an `accept_node` decision row, but it still does not mutate the graph.

## Key files and modification points

- `scripts/jobs_status.py` — operator runtime state backend and evidence display.
- `scripts/runtime/heartbeat/reconciler.py` — direct-return review routing and graph-status reconciliation.
- `scripts/runtime/return_router.py` — mediated-return review routing.
- `scripts/runtime/heartbeat/scope_checker.py` — duplicate guard for review-held nodes.
- `scripts/runtime/heartbeat/provisional_gate.py` — optional scheduler-visible promotion.

Add review display fields in `print_evaluation()` and `_print_executor_attempts()`. Add runtime state-transition policy in `apply_state_change()` without crossing into graph mutation. Graph acceptance tooling belongs outside this backend.

See [Intake and control plane](../systems/intake-and-control-plane.md), [Verification](../systems/verification.md), [State persistence](../systems/state-persistence.md), and [Evaluation pipeline](evaluation-pipeline.md).
