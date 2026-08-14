# Executor-neutral contract

Node: `neutral-executor-contract`
Status: definition ready for human review (not accepted; not complete)

This document freezes the semantic contract GDDP uses to send work to any
executor and receive evidence back. Implementation lives in
`scripts/adapters/executor_protocol.py` and the heartbeat dispatcher/reconciler.
Adapters are transports. They do not own node meaning or graph truth.

## 1. Node packet (criterion: executor-neutral-packet)

One immutable, JSON-serializable `NodePacket` describes a single node execution
attempt. The same packet is the authority for every transport. An adapter may
*render* the packet into a prompt, issue body, mission file, or stdin JSON; it
must not drop, rename, or reinterpret the semantic fields below.

| Field | Meaning |
| --- | --- |
| `job_id` | Runtime job that owns this attempt |
| `execution_attempt_id` | Stable attempt identity (see §2) |
| `node_id` | Graph node being attempted |
| `title` | Human-readable node title |
| `goal` | What this attempt must produce |
| `why` | Why the node exists / intent context |
| `constraints` | Ordered constraint list (JSON values) |
| `acceptance_criteria` | Ordered criteria list (JSON values) |
| `required_artifacts` | Artifact names the attempt must leave |
| `attempt_index` | Zero-based attempt ordinal for this job |
| `previous_findings` | Optional cited fix-list from a prior verdict |
| `expected_base_commit_sha` | Commit the result must build on, when known |

Rules:

- Packet is deeply frozen after construction (`NodePacket` is a frozen dataclass;
  nested JSON is frozen via `MappingProxyType` / tuples).
- Transport serialization is `NodePacket.to_json_value()` /
  `NodePacket.to_json()` (deterministic key order).
- Retry reuses the same node intent and injects findings through
  `previous_findings`; it does not rewrite goal, criteria, or constraints.
- Adapters must forward `previous_findings` when projecting a packet into an
  executor-native form. Dropping the fix-list breaks the retry contract.

## 2. Execution-attempt identity (criterion: execution-attempt-identity)

Every dispatch is one attempt. Attempt identity is executor-independent.

- Format: `{job_id}:attempt:{attempt_index}`
- Helpers: `dispatcher._build_node_packet`, `state_recorder.execution_attempt_id`
- Persisted on `executor_sessions.execution_attempt_id` **before** dispatch is
  treated as accepted work
- A new attempt gets a new `attempt_index` and therefore a new
  `execution_attempt_id`; prior rows remain evidence
- Session refs (`SessionRef(executor, session_id)`) are transport handles only.
  Join keys for evidence are `execution_attempt_id` / `job_id` / `node_id`

Retries, cancellations, poll errors, and controller restarts must not invent a
second live attempt for the same ordinal. Failed and cancelled attempts stay
visible.

## 3. Shared returned-result shape (criterion: shared-result-shape)

All executors return through the types in `executor_protocol.py`. Direct
lifecycle adapters implement `ExecutorAdapter`:

| Stage | Type | Role |
| --- | --- | --- |
| dispatch | `DispatchResult` | success, `SessionRef`, optional issue URL, error |
| poll | `SessionStatus` | normalized state + optional error |
| collect | `PatchResult` | success payload or error; **no apply, no commit, no graph write** |
| cancel | `bool` | best-effort; may be unsupported |

### Normalized session states

`dispatched` · `running` · `awaiting_reply` · `needs_operator` · `completed` ·
`crashed` · `failed` · `missing` · `poll_error`

Unknown executor-native states map to `poll_error` (fail closed).

### `PatchResult` success shapes

Exactly one of these handoff modes on success:

1. **Patch handoff** (remote/patch-only): `patch_text` and/or `patch_path`, with
   optional `base_commit_sha`
2. **Commit-ref handoff** (local/direct): `result_commit_sha` and `result_ref`,
   optional `worktree_path` when retained for recovery

Shared optional evidence fields on either mode:

- `feature_id` — engagement fan-out join key
- `evidence_manifest_path`
- `completion_id` / `completion_digest_sha256` / `completion_quarantine_reason`
- `review_required`
- `error` when `success` is false

Engagement (multi-node) adapters may return `list[PatchResult]` from collect
variants; each element remains one node-scoped result.

### Direct vs mediated registry

- **Direct** (`dispatcher.ADAPTERS`): `jules_api`, `local_subprocess`, `droid`,
  `factory_mission`, `pi_rpc` — full lifecycle conformers
- **Mediated / inherited** (`dispatcher.MEDIATED_ADAPTERS`): `jules` action path
  — preserved infrastructure, not the required command bus, and not claimed as
  a full `ExecutorAdapter` lifecycle conformer

New executors are adapters over this contract. They are not a rewrite of packet,
attempt identity, or result types.

## 4. Evidence-only boundary (criterion: evidence-only-no-graph-mutation)

Executor output is evidence. It never becomes graph truth by itself.

Allowed runtime effects of collect / evaluate / return:

- write attempt spool, patches, commit-refs, receipts
- update runtime job / queue / `executor_sessions` rows
- route a job to `awaiting_review` (or evaluator-triggered retry within budget)

Forbidden without a human:

- marking a graph node complete
- editing `gddp-config` node status as an automatic side effect of success
- treating a passing test suite or evaluator verdict as acceptance

`graph_updater` may open an **evidence PR** proposing completion; only a human
merges or otherwise accepts. Evaluator verdicts and executor success remain
inputs to human review.

## Wire-shape lock

Contract tests in `scripts/adapters/test_executor_contract.py` pin:

- `NodePacket.to_json_value()` key set and attempt-id format
- deep immutability of decoded packets
- semantic field preservation across direct and mediated renderers
- direct registry membership vs mediated separation
- local collect returning `PatchResult` without graph I/O

## Authority

| Layer | Authority |
| --- | --- |
| Graph node status | Human only |
| Node intent fields | Human-owned node definition → packet |
| Attempt identity | GDDP runtime (`execution_attempt_id`) |
| Executor session handle | Adapter (`SessionRef`) |
| Work product | `PatchResult` + artifacts (evidence) |
| Judgment | `VerdictReceipt` (evidence for human) |
