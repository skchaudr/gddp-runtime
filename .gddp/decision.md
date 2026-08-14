# Decision: neutral-executor-contract

Date: 2026-08-14
Node: neutral-executor-contract
execution_attempt_id: job_20260814T04460933529bf8213815:attempt:0
Disposition: ready for human review; not accepted or complete

## Decision

Freeze one executor-neutral contract for all current and future executors:

1. **Packet** — immutable JSON-serializable `NodePacket` (`scripts/adapters/executor_protocol.py`) is the sole semantic description of a node attempt. Adapters render it; they do not redefine it. `previous_findings` travels with retries.
2. **Attempt identity** — `execution_attempt_id = {job_id}:attempt:{attempt_index}`, persisted on `executor_sessions` before dispatch, independent of which executor runs the work.
3. **Returned result** — every collect path returns `PatchResult` (patch handoff or commit-ref handoff) after `DispatchResult` / `SessionStatus` lifecycle types. Engagement adapters return `list[PatchResult]` with the same element shape.
4. **Evidence boundary** — executor output and evaluator verdicts update runtime job/session state only (including `awaiting_review`). Graph node status changes only by human action.

Direct transports (`jules_api`, `local_subprocess`, `droid`, `factory_mission`, `pi_rpc`) implement the lifecycle protocol. The Jules GitHub-action path stays in `MEDIATED_ADAPTERS` as inherited infrastructure, not the required command bus.

Canonical write-up: `docs/executor-contract.md`. Wire-shape locks live in `scripts/adapters/test_executor_contract.py`.

## Boundary

This attempt does not mutate `gddp-config`, accept the node, mark it complete, or write runtime databases. Passing tests are evidence for Sab's review only.
