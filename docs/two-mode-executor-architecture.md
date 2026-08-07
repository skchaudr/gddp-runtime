# Two-Mode Executor Architecture

**Status:** Proposed implementation shape for the agreed two-mode executor
decision. This document records architecture; it does not authorize runtime
implementation or change graph truth.

## Decision

GDDP supports two executor lifecycle modes while retaining one attempt,
reconciliation, evaluation, and review pipeline:

1. **One-shot mode** retains the existing GDDP-owned subprocess lifecycle for
   Pi and other bounded corrective work. One `NodePacket` starts one process;
   the process returns a durable result commit/ref and exits.
2. **Persistent mode** attaches to an externally supervised Factory/Droid
   mission. The external supervisor owns the long-lived process, session,
   resume/restart behavior, worktree/session state, validator, and UAT. GDDP
   sends one immutable `NodePacket` at a time and consumes stable receipts and
   evidence from that mission.

The invariant across both modes is:

> An attempt is `NodePacket` + evidence + `VerdictReceipt`, not a process.

A persistent mission may perform many attempts during its lifetime. A one-shot
process normally performs one attempt, but process lifetime is still an
implementation detail rather than attempt identity.

GDDP remains the intent-preservation and graph-integrity layer. It owns graph
planning, job and attempt identity, leases, immutable per-attempt evidence,
commit verification, evaluation, and review routing. Only a human changes final
graph truth.

## Proposed shape

Both modes continue through the existing `ExecutorAdapter` surface:
`dispatch`, `status`, `collect`, and `cancel`.

```text
live graph -> NodePacket -> selected adapter -> durable result/evidence
                                      |
                                      v
                         existing reconciler/evaluator
                                      |
                                      v
                    VerdictReceipt -> human review -> graph truth
```

The one-shot path continues through `LocalSubprocessAdapter` and
`local_agent_executor.py`. GDDP creates the process and isolated worktree,
captures a result commit under a per-attempt ref, and supervises termination.

The persistent path adds one `factory_persistent` adapter. Its methods have
narrow meanings:

- `dispatch`: submit the `NodePacket` and an opaque lease token to an already
  attached mission. It never starts Factory or Droid.
- `status`: read supervisor-owned assignment state and terminal receipt state.
- `collect`: validate the `MissionReceipt`, hash its referenced artifacts, and
  return the result commit/ref through the existing reconciler path.
- `cancel`: request cancellation of this assignment only. It never terminates
  the mission.

The persistent adapter is a transport boundary, not a second scheduler or a
replacement Factory orchestrator. Factory retains its native orchestration,
workers, validation loops, UAT, and mission context. GDDP consumes those
capabilities through inspectable artifacts.

## Core records

### `MissionPacket`

The supervisor-owned bootstrap/attachment contract for one persistent mission.
It is created once when the mission is started or attached, outside the
per-attempt spool.

Minimum proposed fields:

- `schema_version`
- `mission_id`
- `project_id`
- repository identity and path/ref
- graph reference and content hash at attachment time
- supervisor and native session reference
- capacity and isolation declaration
- Factory artifact roots
- stop conditions

It does not contain a preplanned node list. GDDP continues reading the live
graph and deciding which `NodePacket` is eligible next.

### Existing `NodePacket`

`scripts/adapters/executor_protocol.py` already defines the immutable,
executor-neutral description of one node attempt. Its current transport shape
contains:

- job, execution-attempt, node, and attempt-index identity
- title, goal, and why
- constraints and acceptance criteria
- required artifacts
- previous cited findings for a correction attempt
- expected base commit SHA

Both modes use this existing record. Persistent lifecycle state must not be
added to it.

### `MissionReceipt`

The supervisor-produced return envelope for one persistent assignment. It
projects Factory's existing output into GDDP without rebuilding Factory's
orchestration.

Minimum proposed fields:

- `schema_version`
- `mission_receipt_id`
- `mission_id`
- native session reference and external attempt handle
- GDDP `execution_attempt_id`
- stable `completion_id`
- mission/assignment state and terminal outcome
- expected base commit SHA, result commit SHA, and result ref
- path plus SHA-256 references to existing Factory validator, UAT, handoff,
  progress, and transcript artifacts when present
- generation timestamp and producer identity/version

The receipt contains no GDDP verdict and no graph/node status. It is executor
evidence, not evaluator evidence and not graph truth.

### Attempt record

One attempt record is:

```text
NodePacket
  + normalized evidence manifest
      + result commit/ref
      + MissionReceipt in persistent mode
      + referenced Factory artifacts by path and SHA-256
      + one-shot output artifacts in one-shot mode
  + VerdictReceipt
```

The `execution_attempt_id` is the stable identity joining these records. A
retry creates a new attempt identity and folder; it never overwrites the prior
attempt.

### Existing `VerdictReceipt`

`scripts/runtime/verification/schemas.py` remains the evaluator-owned record of
criteria and intent/integrity evidence. It remains evidence for human review,
never an instruction to change graph truth.

The smallest backward-compatible extension is three optional fields:

- `execution_attempt_id`
- `evidence_manifest_sha256`
- `mission_receipt_id`

The evaluator lanes, worst-of combination, receipt sink, and review routing
remain otherwise unchanged.

## Persistent attempt folder

Persistent mode uses one append-only folder per GDDP attempt:

```text
<persistent-spool>/jobs/<job-id>/attempt-<attempt-index>/
├── packet.json
├── dispatch.json
├── mission-receipt.json
├── evidence-manifest.json
├── verdict-receipt.json
└── seal.json
```

- `packet.json` is the exact immutable `NodePacket` transport.
- `dispatch.json` records the adapter, mission reference, lease token/digest,
  transport submission identity, and dispatch timestamps.
- `mission-receipt.json` is the validated supervisor return envelope.
- `evidence-manifest.json` normalizes result commit/ref and every referenced
  artifact path/hash used for evaluation.
- `verdict-receipt.json` is the evaluator output for this attempt.
- `seal.json` records the final file hashes and seals the folder as immutable.

Files are created append-only until sealing; sealed contents are immutable.
An exact replay of the same `completion_id` and digest is a no-op. A conflicting
completion for the same attempt is quarantined for human review.

The persistent spool must contain no PID, process group, restart counter,
heartbeat, or other process-supervision state. That state belongs to the
external supervisor. The existing one-shot spool may retain `supervisor.pid`,
`pid`, `stdout`, `stderr`, and `exit.json` because GDDP owns that process
lifecycle.

Factory artifacts are reused by reference and SHA-256. GDDP does not copy their
semantics into a new orchestration format or rerun Factory validators/UAT. A
later hash mismatch makes the evidence unverifiable and routes the attempt to
review; it does not authorize GDDP to repair Factory state.

## Ownership by mode

| Surface | One-shot mode | Persistent mode | Final authority |
|---|---|---|---|
| Graph planning and eligible frontier | GDDP | GDDP | Human owns accepted graph truth |
| Job and attempt identity | GDDP | GDDP | GDDP runtime record |
| Attempt lease | GDDP | GDDP; opaque token passed to supervisor | GDDP runtime record |
| Process lifetime | GDDP local adapter | External supervisor | Mode owner |
| Mission/session resume and restart | Per-attempt process only | External supervisor | External supervisor |
| Worktree and native session state | GDDP wrapper | External supervisor | Mode owner |
| Result commit/ref creation | GDDP wrapper | External supervisor, asserted in `MissionReceipt` | GDDP verifies |
| Validator and UAT loops | Bounded executor work | Factory/Droid supervisor | Supervisor produces evidence |
| Attempt spool and evidence manifest | GDDP | GDDP | GDDP |
| Factory artifacts | Not applicable | Supervisor creates; GDDP references and hashes | Supervisor source, GDDP verification |
| Base/result ancestry verification | GDDP | GDDP | GDDP |
| Evaluation and `VerdictReceipt` | GDDP | GDDP | Evaluator evidence only |
| Review routing | GDDP | GDDP | Human decides |
| Node completion / graph truth | Human | Human | Human only |

## Failure and budget behavior

There are separate accounting domains:

- **Attempt/criteria budget** counts distinct attempts to satisfy the node.
- **Plumbing budget** counts infrastructure retries before useful terminal
  work evidence exists. The live one-shot runtime already separates this with
  `jobs.plumbing_attempt`.
- **Queue transport retry count** handles repeated poll/collect/parse work for
  the same persistent attempt and lease.
- **Supervisor-internal budget** belongs to Factory/Droid validation and UAT;
  GDDP observes its terminal receipt but does not count its internal loops.

| Condition | Owner and required action | Attempt budget | Plumbing / transport budget |
|---|---|---:|---:|
| Evaluator finds cited criteria or intent/integrity failure | GDDP may allocate a new attempt with the same node and `previous_findings`; otherwise route to review | +1 for the new attempt | No change |
| Attempt budget exhausted | GDDP stops dispatch and routes `awaiting_review` | No further increment | No change |
| One-shot process fails after durable terminal state | Existing reconciler records failure and may allocate a correction attempt | +1 if retried | No change |
| One-shot process dies before durable exit state | Existing reconciler retries the same work attempt | No change | +1 plumbing retry |
| Persistent native session crashes but supervisor can resume | Supervisor resumes the same mission and assignment | No change | No change |
| Supervisor emits an explicit terminal assignment failure | GDDP records the receipt; a policy-approved retry gets a new attempt | +1 if retried | No change |
| Supervisor crashes or disappears | At lease expiry GDDP parks for reconciliation; it must not infer node failure or start duplicate work | No change | No change |
| Lease expires | GDDP revokes authority and parks; a reclaim uses a new lease token and reconciles any late receipt | No change | No change |
| Poll, collect, or receipt parse fails transiently | Persistent adapter retries the same attempt/lease | No change | +1 queue transport retry |
| Authentication is unavailable | Park `needs_operator`; preserve session and attempt evidence | No change | No change |
| Factory validator/UAT retries internally | Supervisor continues inside the same GDDP attempt | No change | Supervisor-owned only |
| Evaluator bridge fails | Retry the evaluator once as transient plumbing, then persist evaluator-error evidence and route to review | No executor retry | Evaluator retry only |
| Cancellation | GDDP atomically revokes the lease; adapter cancels only the assignment; mission survives | No change | No change |
| Exact duplicate completion | Idempotency check returns the already recorded result | No change | No change |
| Conflicting completion for one attempt | Quarantine both identities/digests and route to human review | No change | No automatic retry |
| Artifact hash or commit ancestry mismatch | Preserve the mismatch as integrity evidence and route to human review | No automatic increment | No automatic retry |

A retry re-attempts the same `NodePacket` intent with a new attempt identity and
cited findings. Work discovered outside the node remains a continuation
proposal; neither mode may silently widen the node.

## Minimal implementation path

1. **Preserve one-shot as the default.** Do not change the current
   `LocalSubprocessAdapter`, `local_agent_executor.py`, commit-ref handoff, or
   one-shot spool contract.
2. **Define the persistent envelopes.** Add `MissionPacket` and
   `MissionReceipt` beside the executor protocol, plus the three optional
   `VerdictReceipt` provenance links. Keep `NodePacket` unchanged.
3. **Add one persistent adapter.** Implement `factory_persistent` behind the
   current adapter protocol and register it through the existing dispatcher.
   The adapter attaches to a configured mission transport; it never starts or
   supervises Factory.
4. **Add only nullable runtime metadata.** Reuse `executor_sessions` as the row
   per attempt, adding nullable `mission_id`, `completion_id`, and
   `evidence_manifest_path`. Add a unique partial index for non-null
   `completion_id`. Do not add a missions table initially.
5. **Activate existing lease fields.** Use `queue_records.lease_owner`,
   `lease_expires_at`, and `retry_count` for claim, renewal, revocation, and
   same-attempt transport retries. The lease owner presented to Factory is an
   opaque token, not a PID.
6. **Reuse reconciliation and evaluation.** Feed verified result commits/refs
   into the current reconciler, commit ancestry checks, evaluator bridge,
   receipt sink, results store, and `awaiting_review` routing.
7. **Prove the boundary with a fake supervisor.** Test no PID in the persistent
   spool, one folder per attempt, immutable sealing, lease expiry, crash resume,
   attempt-only cancellation, exact duplicate replay, conflicting completion
   quarantine, artifact hash failure, and evaluator reuse.
8. **Pilot one human-selected node.** Attach to one existing Factory mission
   and run one node through completion, crash recovery, cancellation, and
   duplicate-completion probes. Keep automatic graph advancement parked at
   human review during the pilot.
9. **Expand only after the live contract is proven.** Repeated `NodePacket`
   assignment to one mission, a mission registry, or broader concurrency comes
   after the transport and receipt questions below have observed answers.

Graph configuration needs only another allowed executor value,
`factory_persistent`. Host runtime configuration maps project/repository to an
attached mission transport. Mission IDs and lifecycle state do not belong in
graph YAML.

## Critical unresolved Factory transport and receipt questions

These questions require live Factory evidence. The adapter must not encode
guesses for them.

1. **Submission:** What stable external operation submits the next
   `NodePacket` to an already-running mission: CLI resume, daemon IPC/WebSocket,
   or a filesystem inbox?
2. **Status and cancellation:** How does an external caller read assignment
   status and cancel one assignment without ending or corrupting the mission?
3. **Canonical identity:** Which value survives reconnect and restart as the
   canonical mission identity: Factory mission directory, native session UUID,
   or `state.json` `missionId` (`mis_*`)?
4. **Terminal receipt contract:** Which existing Factory files are stable,
   terminal receipts, what event makes each safe to hash, and which fields
   distinguish assignment completion from an intermediate validator/UAT pass?
5. **Commit contract:** How do Factory's worktree, expected base, result commit,
   and branch/ref map to GDDP's existing ancestry and per-attempt ref checks?
6. **Crash and replay semantics:** After Factory or its supervisor restarts,
   how are the current assignment, its stable `completion_id`, and an already
   written receipt rediscovered without duplicate execution?
7. **Isolation and capacity:** What does Factory guarantee when one mission
   accepts sequential or concurrent assignments, and which native state is
   mission-wide versus worktree/assignment-specific?
8. **Artifact stability:** Which validator, UAT, handoff, transcript, progress,
   and feature artifacts are contractual enough to reference; can any be
   rewritten after apparent completion; and how is that mutation detected?

Until those facts are verified, the design chooses only the boundary:
`factory_persistent` consumes an external submit/status/cancel/receipt contract.
It does not choose or invent that contract.

## Explicit non-goals

- Rebuilding Factory mission orchestration inside GDDP
- Treating a process, mission, session, commit, test, or verdict as graph truth
- Storing persistent-mode PID or supervision state in GDDP's attempt spool
- Preplanning a mission's node list in `MissionPacket`
- Adding a second scheduler, evaluator, reconciler, or missions database before
  demonstrated need
- Copying Factory's internal artifact model when path/hash references provide
  sufficient evidence
- Automatically accepting a node from executor success or `VerdictReceipt`
