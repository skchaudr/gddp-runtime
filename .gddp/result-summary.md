# Result Summary: neutral-executor-contract

execution_attempt_id: job_20260814T04460933529bf8213815:attempt:0
Base: e2e5f30536e66b8ce09125b70e297fad88102823

## Goal

Produce a reviewable definition of the executor-neutral node packet, execution-attempt identity, and shared returned-result shape.

## Acceptance evidence

| Criterion | Evidence |
| --- | --- |
| **executor-neutral-packet** | `NodePacket` fields + `to_json_value()`/`to_json()`; same packet built by `dispatcher._build_node_packet` for every transport; renderers (`session_prompt`, Jules action body) preserve semantics; deep freeze proven in tests. Documented in `docs/executor-contract.md` §1. |
| **execution-attempt-identity** | Format `{job_id}:attempt:{attempt_index}` in packet builder and `state_recorder.execution_attempt_id`; column on `executor_sessions`; wire-shape test asserts attempt id is present and executor-free. §2 of the contract doc. |
| **shared-result-shape** | `DispatchResult`, `SessionStatus`, `PatchResult` are the only collect/dispatch receipts; patch vs commit-ref handoffs share one type; direct registry is `ExecutorAdapter`-conformant; mediated `jules` is separate. Field lock tests pin the shapes. §3. |
| **evidence-only-no-graph-mutation** | Reconciler/return_router route to `awaiting_review` only; `graph_updater` is human-merged evidence PR; adapters' `collect` docstring and local/pi prompts forbid graph/DB mutation. §4. |

## What this attempt changed

- Added durable contract: `docs/executor-contract.md`
- Added wire-shape lock tests in `scripts/adapters/test_executor_contract.py` (packet keys, result fields, session state vocabulary)
- Refreshed `.gddp/decision.md`, `.gddp/result-summary.md`, `.gddp/patch.diff` for this attempt

Inherited implementation (packet, adapters, session lifecycle, registries) remains on base commit as system context; this attempt defines and locks the contract rather than re-implementing the spine.

## Verification observed

```text
env -u PYTHONPATH -u PYTHONHOME /opt/homebrew/bin/python3 -m pytest \
  scripts/adapters/test_executor_contract.py -q
# 37 passed

env -u PYTHONPATH -u PYTHONHOME /opt/homebrew/bin/python3 -m pytest \
  scripts/adapters/test_executor_contract.py \
  scripts/adapters/test_jules_action_adapter.py \
  scripts/runtime/heartbeat/test_executor_sessions.py -q
# 103 passed
```

## Residual risks / known gaps (out of scope to silently fix here)

- `MissionAdapter._packet_node` historically dropped `previous_findings` when projecting mission nodes (mission-mode research review). Contract now states adapters must forward findings; fixing mission projection is separate bounded work if still open on HEAD.
- Jules remote cancel may be unsupported depending on CLI/API surface; cancel remains best-effort.
- Subagent fanout (`xai/grok-4.6`) was not available in this harness session (no `subagent` tool); review was parent-local against live code + tests.

## Human gate

Sab reviews this evidence and chooses accept / retry / revise / defer / abandon.
Only human acceptance updates graph truth for `neutral-executor-contract`.
