# NodePacket: Immutable Node Execution Attempt

A **NodePacket** is an executor-neutral, immutable description of one node execution attempt. It carries everything an executor needs to attempt a node, including constraints, acceptance criteria, and findings from prior attempts.

## NodePacket Structure

Defined in `scripts/adapters/executor_protocol.py`:

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | `str` | Associated job identifier |
| `execution_attempt_id` | `str` | Durable attempt identifier (e.g., `job_id:attempt:0`) |
| `node_id` | `str` | Target node identifier |
| `title` | `str` | Human-readable node title |
| `goal` | `str` | What this attempt must accomplish |
| `why` | `str` | Rationale for this node |
| `constraints` | `tuple[FrozenJSON, ...]` | Hard boundaries (immutable) |
| `acceptance_criteria` | `tuple[FrozenJSON, ...]` | What must be true (immutable) |
| `required_artifacts` | `tuple[str, ...]` | Files that must exist |
| `attempt_index` | `int` | Attempt number (0-based) |
| `previous_findings` | `Mapping[str, FrozenJSON] \| None` | Evaluator findings from prior attempts |
| `expected_base_commit_sha` | `str \| None` | Git base commit at dispatch time |

**Source:** `scripts/adapters/executor_protocol.py` (NodePacket dataclass, lines ~50-90)

## Immutability

NodePacket is a **frozen dataclass** with deep-frozen JSON fields:

```python
@dataclass(frozen=True)
class NodePacket:
    constraints: tuple[FrozenJSON, ...]
    acceptance_criteria: tuple[FrozenJSON, ...]
    previous_findings: Mapping[str, FrozenJSON] | None
```

**Freeze mechanism:**

- `Mapping` → `MappingProxyType` (read-only view)
- `Sequence` → `tuple` (immutable)
- Primitives (`str`, `int`, `float`, `bool`, `None`) → unchanged

**Source:** `_freeze_json()` in `scripts/adapters/executor_protocol.py` (lines ~20-40)

**Why immutability matters:**

- Executors cannot accidentally modify the packet
- Transport serialization is deterministic
- Replay and auditing are safe

## Serialization

### to_json_value()

Returns the exact transport shape for this packet:

```python
{
    "job_id": str,
    "execution_attempt_id": str,
    "node_id": str,
    "title": str,
    "goal": str,
    "why": str,
    "constraints": list,
    "acceptance_criteria": list,
    "required_artifacts": list,
    "attempt_index": int,
    "previous_findings": dict | None,
    "expected_base_commit_sha": str | None,
}
```

### to_json()

Deterministic JSON serialization:

```python
json.dumps(self.to_json_value(), sort_keys=True, separators=(",", ":"))
```

**Source:** `scripts/adapters/executor_protocol.py` (lines ~90-120)

## Execution Attempt Identity

### execution_attempt_id

Format: `<job_id>:attempt:<attempt_index>`

Example: `job-abc123:attempt:0`

**Purpose:** Durable identifier for this specific attempt, independent of executor session IDs.

**Backfill:** Old sessions predate first-class attempt identity. The runtime backfills `execution_attempt_id` from `created_at` ordering.

**Source:** `scripts/init_db.py` (lines ~200-220)

### attempt_index

0-based attempt number. Increments on each retry.

**Source:** `scripts/runtime/heartbeat/state_recorder.py` (`allocate_retry_attempt`)

## Previous Findings

When a node fails evaluation and retries, the evaluator's findings are attached to the next NodePacket:

```python
previous_findings: Mapping[str, FrozenJSON] | None
```

**Structure:**

```json
{
  "criterion-1": {
    "status": "fail",
    "evidence": ["file.py:42", "test_file.py:10"],
    "reasoning": "Expected X but found Y"
  }
}
```

**Purpose:** Gives the executor concrete evidence to fix, not just "try again."

**Source:** `scripts/runtime/heartbeat/state_recorder.py` (retry allocation)

## Expected Base Commit

```python
expected_base_commit_sha: str | None
```

**Purpose:** Records the git commit the executor was built on. Enables diff-based evidence downstream.

**Usage:**

- Dispatcher sets this from `git rev-parse HEAD` at dispatch time
- Reconciler verifies the result commit is a descendant
- Evaluator uses it to compute `base..HEAD` diff

**Source:** `scripts/runtime/heartbeat/dispatcher.py` (packet construction)

## Systems That Produce/Consume

### Producers

- **Dispatcher** (`scripts/runtime/heartbeat/dispatcher.py`) — creates NodePackets from jobs

### Consumers

- **Executor adapters** — receive packets and dispatch to executors
  - `scripts/adapters/jules_cli_adapter.py`
  - `scripts/adapters/jules_api_adapter.py`
  - `scripts/adapters/mission_adapter.py`
  - `scripts/adapters/local_subprocess_adapter.py`

## Relationships

```
Job (1) → (0..*) NodePacket
NodePacket (1) → (1) Executor Session
NodePacket (1) → (0..1) Evidence Manifest
```

## Key Invariants

1. NodePacket is immutable after creation
2. `execution_attempt_id` is durable across executor restarts
3. `previous_findings` carries evaluator feedback to retries
4. `expected_base_commit_sha` binds the packet to a git state
5. One job can spawn multiple NodePackets (retries, parallel candidates)

## Example

```python
packet = NodePacket(
    job_id="job-abc123",
    execution_attempt_id="job-abc123:attempt:0",
    node_id="neutral-executor-contract",
    title="Define executor-neutral contract",
    goal="Create a transport-agnostic interface for executor adapters",
    why="All executors must implement the same lifecycle protocol",
    constraints=(
        "Do not modify existing executor implementations",
        "Must support Jules CLI, Jules API, and Droid",
    ),
    acceptance_criteria=(
        "ExecutorAdapter protocol defined",
        "NodePacket dataclass defined",
        "SessionRef dataclass defined",
    ),
    required_artifacts=("scripts/adapters/executor_protocol.py",),
    attempt_index=0,
    previous_findings=None,
    expected_base_commit_sha="abc123def456",
)
```
