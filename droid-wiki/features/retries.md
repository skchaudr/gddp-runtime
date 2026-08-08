# Retries

Active contributors: Saboor

## Purpose

Retries re-attempt the same node without changing its intent. GDDP distinguishes evidence-bearing work failures from executor plumbing failures so infrastructure noise does not consume the human-owned work budget.

## Corrective work retries

On the mediated return path, `scripts/runtime/verification/retry_budget.py` permits automatic correction only when all of these conditions hold:

1. the combined verdict is not `pass`;
2. criteria or integrity findings contain actionable evidence;
3. `execution_policy.retry_budget` is positive;
4. the current attempt is below both the project retry budget and the job's `max_attempts` backstop.

Actionable evidence is a repository file path, optionally with a line number, or an affected graph node id in an integrity finding. Findings such as “the code feels wrong” route to human review instead of work. This prevents an executor from being asked to repair an uncited model impression.

`scripts/runtime/return_router.py` persists a fix-list in `jobs.previous_findings`. It includes the combined and integrity verdicts, integrity findings and reasoning, and criteria findings. `scripts/runtime/heartbeat/state_recorder.py` atomically increments `jobs.attempt`, inserts a new `dispatching` executor session, and passes the unchanged job plus previous findings through the executor-neutral `NodePacket`.

Direct executor failures also use work attempts when the worker actually failed. They preserve the same node and increment the attempt index; they do not rewrite acceptance criteria or graph dependencies.

## Plumbing retries

Failures such as a reaped process, host fault, spawn error, or missing durable exit state indicate that work was not reliably attempted. `allocate_plumbing_retry()` uses the separate `jobs.plumbing_attempt` counter, currently bounded by `DEFAULT_PLUMBING_RETRY_BUDGET` of 3. The replacement keeps the current work `attempt_index`, so superseded-session protection still identifies one live attempt.

Authentication failures are not useful retries. `scripts/runtime/heartbeat/reconciler.py` parks them as `needs_operator` without consuming budget because repeating against revoked or missing credentials cannot succeed.

Poll errors are transient and normally wait for the next heartbeat. An uncertain expired dispatch reservation is terminalized and routed to operator recovery rather than automatically launching a possible duplicate.

## Key files

- `scripts/runtime/verification/retry_budget.py` — evaluator retry eligibility and evidence-reference checks.
- `scripts/runtime/return_router.py` — fix-list construction and mediated redispatch.
- `scripts/runtime/heartbeat/reconciler.py` — executor failure classification and replacement.
- `scripts/runtime/heartbeat/state_recorder.py` — atomic work and plumbing attempt allocation.
- `scripts/adapters/executor_protocol.py` — immutable `previous_findings` field in `NodePacket`.

## Modification points

Adjust project work policy through `execution_policy.retry_budget`. Change actionable-citation recognition in `has_evidence_references()` and `has_criteria_evidence()` only with tests for false positives and uncited findings. Add infrastructure signatures to `classify_plumbing_failure()` rather than charging them to work attempts. A retry must never mutate node scope; discovered out-of-scope work becomes a human-reviewed continuation proposal.

See [Heartbeat](../systems/heartbeat.md), [Executor adapters](../systems/executor-adapters.md), [Node packet](../primitives/node-packet.md), [Executor session](../primitives/executor-session.md), and [Human review](human-review.md).
