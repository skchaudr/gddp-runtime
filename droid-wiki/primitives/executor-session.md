# Executor Session: Lifecycle, Completion Identity, Quarantine

An **executor session** represents one attempt to execute a job on a remote executor (Jules CLI, Jules API, Droid, local subprocess, etc.). Sessions track state transitions, completion identity, and quarantine for digest conflicts.

## SessionRef

A durable reference to an executor session.

Defined in `scripts/adapters/executor_protocol.py`:

| Field | Type | Description |
|-------|------|-------------|
| `executor` | `str` | Executor name (e.g., `jules_cli`, `droid`, `local_subprocess`) |
| `session_id` | `str` | Executor-specific session identifier |

**Source:** `scripts/adapters/executor_protocol.py` (SessionRef dataclass, lines ~125-130)

## SessionStatus

Result of polling a session.

Defined in `scripts/adapters/executor_protocol.py`:

| Field | Type | Description |
|-------|------|-------------|
| `state` | `Literal[...]` | Current state (see below) |
| `error` | `str \| None` | Error message (if any) |

### Session States

| State | Meaning |
|-------|---------|
| `dispatched` | Session sent to executor, not yet running |
| `running` | Executor actively working |
| `awaiting_reply` | Executor asked a question, waiting for answer |
| `needs_operator` | Executor needs human intervention |
| `completed` | Executor finished successfully |
| `crashed` | Executor process died unexpectedly |
| `failed` | Executor returned an error |
| `missing` | Session not found on executor |
| `poll_error` | Error polling session status |

**Source:** `scripts/adapters/executor_protocol.py` (SessionStatus dataclass, lines ~135-150)

## Executor Session Record (queue.db)

### Schema (queue.db `executor_sessions` table)

| Field | Type | Description |
|-------|------|-------------|
| `session_db_id` | `TEXT PRIMARY KEY` | Internal session identifier |
| `job_id` | `TEXT NOT NULL` | Associated job (FK to jobs) |
| `executor` | `TEXT NOT NULL` | Executor name |
| `session_id` | `TEXT NOT NULL` | Executor-specific session ID |
| `state` | `TEXT` | Current state (see below) |
| `execution_attempt_id` | `TEXT NOT NULL` | Durable attempt identifier |
| `attempt_index` | `INTEGER NOT NULL` | Attempt number (0-based) |
| `expected_base_commit_sha` | `TEXT` | Git base commit at dispatch |
| `result_commit_sha` | `TEXT` | Git commit after patch application |
| `patch_path` | `TEXT` | Path to retrieved patch file |
| `completion_id` | `TEXT` | Stable executor completion identity |
| `completion_digest_sha256` | `TEXT` | SHA-256 digest of normalized completion evidence |
| `completion_quarantine_reason` | `TEXT` | Evidence conflict requiring human review |
| `evidence_manifest_path` | `TEXT` | Path to per-node evidence manifest |
| `error` | `TEXT` | Error message (if any) |
| `created_at` | `TEXT NOT NULL` | ISO timestamp of creation |
| `updated_at` | `TEXT NOT NULL` | ISO timestamp of last update |

**Source:** `scripts/init_db.py` (executor_sessions table, lines ~160-190)

### Executor Session States

These states are **distinct from SessionStatus states** and track the runtime's view of the session:

| State | Meaning |
|-------|---------|
| `dispatched` | Session sent to executor |
| `running` | Executor actively working |
| `needs_operator` | Executor needs human intervention |
| `completed` | Executor finished |
| `failed` | Executor returned error |
| `collected` | Artifacts retrieved from executor |
| `evaluated` | Evaluator processed this session |
| `completion_duplicate` | Exact replay of a prior completion |
| `completion_quarantined` | Digest conflict; awaiting human review |

**Source:** `scripts/runtime/heartbeat/state_recorder.py` (`update_executor_session_state`)

## Session Lifecycle

```
dispatched → running → completed → collected → evaluated
              ↓           ↓
         needs_operator  failed
              ↓
         crashed (if process dies)
```

### State Transitions

1. **dispatched** — Dispatcher creates session record after sending NodePacket to executor
2. **running** — Reconciler polls session and sees it's active
3. **completed** — Reconciler polls session and sees it finished
4. **collected** — Reconciler retrieves artifacts (patch, evidence manifest)
5. **evaluated** — Evaluator processes the session and writes a verdict receipt

### Retry Behavior

- A job can have multiple sessions (retries, parallel candidates)
- Each session has a unique `execution_attempt_id` and `attempt_index`
- Failed sessions do not block the job; the dispatcher creates a new session

## Completion Identity

### completion_id

A stable, executor-provided identifier for a completed session.

**Purpose:** Detects exact replays and digest conflicts.

**Example:** Factory Droid mission ID, Jules session completion token.

### completion_digest_sha256

A SHA-256 digest of normalized completion evidence.

**Purpose:** Binds the completion identity to specific evidence (patch, manifest, commit).

**Normalization:**

- Strips whitespace
- Lowercases hex
- Validates 64-character length

**Source:** `scripts/runtime/heartbeat/completion_discipline.py` (`_normalize_digest`)

### Completion Discipline

When a session completes, the runtime submits the completion identity for comparison:

**Source:** `scripts/runtime/heartbeat/completion_discipline.py` (`submit_completion`)

**Decision outcomes:**

| Action | Meaning |
|--------|---------|
| `proceed` | Null completion identity; no records-discipline changes |
| `stored` | First time seeing this completion; record it |
| `duplicate` | Exact replay of a prior completion (same digest) |
| `quarantined` | Digest conflict; preserve both envelopes, route to human review |

### Duplicate Detection

If the same `completion_id` and `completion_digest_sha256` appear in multiple sessions:

- The first session retains its state
- Subsequent sessions are marked `completion_duplicate`
- No quarantine; this is an exact replay

### Digest Conflict (Quarantine)

If the same `completion_id` appears with **different** digests:

- Both sessions are marked `completion_quarantined`
- `completion_quarantine_reason` records the conflict
- Both jobs are routed to `awaiting_review`
- Human must decide which completion is correct

**Quarantine preserves both envelopes** — it does not discard or launder evidence.

**Source:** `scripts/runtime/heartbeat/completion_discipline.py` (lines ~100-180)

## Quarantine

### What Triggers Quarantine?

1. **Digest conflict** — Same `completion_id`, different `completion_digest_sha256`
2. **Push guard violation** — Feature branch reachable from protected branch (see `mission_push_guard.py`)

### Quarantine State

Sessions in quarantine:

- `state` = `completion_quarantined`
- `completion_quarantine_reason` = human-readable explanation
- `error` = same as reason (for visibility)

**Jobs in quarantine:**

- `status` = `awaiting_review`
- Cannot proceed to evaluation
- Human must review and decide

### Quarantine Recovery

Human reviewer can:

1. **Accept one completion** — mark the other session as failed
2. **Reject both** — mark both sessions as failed, retry the job
3. **Investigate** — examine evidence manifests, patches, commit SHAs

## Evidence Manifest

### evidence_manifest_path

Path to a per-node evidence manifest file.

**Structure:** JSON file containing:

- `feature_id` — node ID
- `base_sha` — git base commit
- `result_sha` — git result commit
- `worker_session_id` — executor session ID
- `completion_id` — stable completion identity
- `completion_digest_sha256` — digest of normalized evidence
- `review_required` — boolean (routes to human review)
- `review_reason` — why review is required
- `completion_quarantine_reason` — digest conflict reason (if any)

**Source:** `scripts/adapters/mission_evidence.py` (`collect_mission_evidence`)

### Manifest Collection

After a session completes, the reconciler:

1. Retrieves the patch or commit-ref from the executor
2. Collects evidence (handoffs, progress logs, receipts)
3. Writes a per-node evidence manifest
4. Records the manifest path in the session record

**Source:** `scripts/runtime/heartbeat/reconciler.py` (collection phase)

## Systems That Produce/Consume

### Producers

- **Dispatcher** (`scripts/runtime/heartbeat/dispatcher.py`) — creates session records
- **Reconciler** (`scripts/runtime/heartbeat/reconciler.py`) — updates session state
- **Completion discipline** (`scripts/runtime/heartbeat/completion_discipline.py`) — compares completions

### Consumers

- **Reconciler** — polls sessions, collects artifacts
- **Evaluator** — reads session records and evidence manifests
- **Human reviewer** — investigates quarantined sessions

## Relationships

```
Job (1) → (0..*) Executor Session
Executor Session (1) → (1) NodePacket
Executor Session (1) → (0..1) Evidence Manifest
Executor Session (1) → (0..1) PatchResult
Executor Session (1) → (0..1) Verdict Receipt
```

## Key Invariants

1. One job can have multiple sessions (retries, parallel candidates)
2. Completion identity is stable and executor-provided
3. Digest conflicts trigger quarantine, not auto-resolution
4. Quarantine preserves both envelopes; it does not launder evidence
5. Evidence manifests are per-node, not per-session
6. Sessions are immutable after `evaluated` state

## Example

```python
session_ref = SessionRef(
    executor="factory_mission",
    session_id="mission-abc123",
)

# After completion
session_record = {
    "session_db_id": "session-xyz789",
    "job_id": "job-abc123",
    "executor": "factory_mission",
    "session_id": "mission-abc123",
    "state": "collected",
    "execution_attempt_id": "job-abc123:attempt:0",
    "attempt_index": 0,
    "expected_base_commit_sha": "abc123def456",
    "result_commit_sha": "def456abc789",
    "completion_id": "mission-completion-001",
    "completion_digest_sha256": "a1b2c3d4e5f6...",
    "evidence_manifest_path": "/path/to/manifest.json",
}
```
