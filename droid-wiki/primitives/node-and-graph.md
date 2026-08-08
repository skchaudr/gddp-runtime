# Node and Graph Truth

A **node** is the unit of project intent. Everything else — jobs, sessions, commits, tests, artifacts, verdicts — is evidence from attempts to satisfy that intent.

## NodeData Structure

Defined in `scripts/runtime/heartbeat/graph_reader.py`:

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | `str` | Unique identifier (e.g., `neutral-executor-contract`) |
| `title` | `str` | Human-readable node name |
| `status` | `str` | Current graph status (see below) |
| `type` | `str` | Node category (e.g., `capability`, `implementation`) |
| `why` | `str` | Rationale for this node's existence |
| `depends_on` | `list[str]` | Dependency node IDs (DAG edges) |
| `acceptance_criteria` | `list[str]` | What must be true for this node to be satisfied |
| `constraints` | `list[str]` | Hard boundaries that must not be violated |
| `allowed_execution_modes` | `list[str]` | Executors permitted to attempt this node |
| `required_artifacts` | `list[str]` | Files/evidence that must exist before acceptance |
| `priority` | `str` | Scheduling hint (e.g., `normal`, `high`) |
| `unlocks` | `list[str]` | Nodes this one enables when complete |

**Source:** `scripts/runtime/heartbeat/graph_reader.py` (NodeData dataclass, lines ~120-140)

## Node Statuses

### Graph Statuses (gddp-config)

These statuses live in project graph YAML. Only `complete` represents human acceptance. Runtime currently writes scheduler statuses `ready` and `provisional`, creating a real boundary tension because scheduling state and accepted truth share the same files.

| Status | Meaning |
|--------|---------|
| `pending` | Node defined but not yet ready for execution |
| `ready` | Dependencies satisfied; eligible for dispatch |
| `provisional` | Evaluator passed; awaiting human review |
| `complete` | Human accepted; node satisfied |
| `deferred` | Human decided to postpone |

**Source:** gddp-config YAML files (e.g., `graphs/<project-id>/nodes/<node-id>.yaml`)

### Runtime Job Statuses (queue.db)

These are **separate from graph status** and track executor lifecycle:

| Status | Meaning |
|--------|---------|
| `ready` | Job created, not yet dispatched |
| `running` | Executor session active |
| `awaiting_result` | Session completed, collecting artifacts |
| `awaiting_review` | Evaluator queued or in progress |
| `complete` | Job finished (does not imply node acceptance) |
| `failed` | Executor crashed or returned error |

**Source:** `scripts/init_db.py` (jobs table, status column)

## Graph Truth vs. Evidence

**Critical distinction:**

- **Graph truth** = human-accepted completion in gddp-config YAML
- **Evidence** = everything else (tests, verdicts, commits, artifacts)

**Doctrine from `docs/Tests-can-fail-nodes-can-pass.md`:**

> Node status reflects accepted graph progress, not temporary implementation perfection. Tests are evidence, not graph truth. Criteria are evidence, not graph truth. Evaluator verdicts are evidence, not graph truth. Only human-accepted node status is graph truth.

**Implications:**

- A node can be `complete` even if some tests fail (if the human accepted it)
- A node can be `provisional` after a qualifying evaluator pass (awaiting human review)
- The runtime never marks a node `complete`; only the human does
- Evaluator verdicts are input to human decision, not autonomous authority

## Provisional Status

When a node passes evaluation, the runtime marks it `provisional` in the graph YAML:

**Producer:** `scripts/runtime/heartbeat/provisional_gate.py` (`maybe_mark_provisional`)
**Consumer:** Human reviewer (via gddp-config edits)

**What provisional means:**

- Combined verdict is `pass`, intent is preserved, graph integrity is preserved, and the evaluator did not require human review
- Gate token written to `.gddp/gates/<node-id>.token`
- Dependents may start execution (if their other dependencies are met)
- Node is not yet `complete` — human must accept

**Revocation:** A human status change away from `provisional` revokes the gate token and restores dependency blocking as appropriate.

**Source:** `scripts/runtime/gates.py` (`write_gate`, `revoke_gate`)

## ProjectGraph Structure

Defined in `scripts/runtime/heartbeat/graph_reader.py`:

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `str` | Unique project identifier |
| `project_name` | `str` | Human-readable project name |
| `repo` | `str` | Git repository (owner/name) |
| `nodes` | `list[dict]` | Summary rows from project.yaml |
| `execution_policy` | `dict` | Mission sizing (engagement size, max pairs) |

**Source files:**

- Project: `gddp-config/graphs/<project-id>/project.yaml`
- Nodes: `gddp-config/graphs/<project-id>/nodes/<node-id>.yaml`

## Ready Node Selection

**Producer:** `GraphReader.get_ready_nodes()` in `scripts/runtime/heartbeat/graph_reader.py`

**Selection criteria:**

1. Node status is `ready` in project.yaml
2. Node has a detail YAML file in `nodes/<node-id>.yaml`
3. Dependencies are satisfied (checked by scope_checker, not graph_reader)

**Policy enforcement:**

- `mission_engagement_size` — max nodes per engagement (default 1)
- `mission_max_pairs` — max ready pairs to select (default 5)
- Execution mode allowlist enforced at load time

**Source:** `scripts/runtime/heartbeat/graph_reader.py` (lines ~50-100)

## Systems That Produce/Consume Nodes

### Producers

- **Human operator** — writes node YAML files in gddp-config
- **Graph amendment proposal** — agent suggests node changes (does not write)
- **Provisional gate** — marks node `provisional` after evaluator pass

### Consumers

- **GraphReader** — loads nodes for frontier selection
- **Dispatcher** — creates jobs from ready nodes
- **Evaluator** — verifies node satisfaction
- **Human reviewer** — accepts/rejects provisional nodes

## Relationships

- **Node → Job**: One node can spawn multiple jobs (retries, parallel candidates)
- **Node → Executor Session**: One job can have multiple sessions (attempts)
- **Node → Gate Token**: One node gets one gate token when provisional
- **Node → Node**: Dependency edges (DAG), evidence links (receipts, traces)

## Key Invariants

1. Only the human writes accepted `complete`
2. Runtime currently writes scheduler statuses `ready` and `provisional` into graph YAML
3. Storing scheduler state beside accepted truth is an explicit architecture boundary, not proof that runtime is read-only
4. Dependency edges form a DAG; evidence links are separate
5. Gate tokens are admission signals, not lifecycle gates
