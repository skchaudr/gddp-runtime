# Primitives: Domain Objects in gddp-runtime

This directory documents the core domain objects that flow through the gddp-runtime system. Each primitive represents a distinct concept with specific lifecycle, ownership, and relationships.

## Primitive Categories

### Graph Layer
- **[Node and Graph Truth](node-and-graph.md)** — Nodes as units of intent, graph truth, provisional statuses
- **[Gate Token](gate-token.md)** — Per-node admission signals for mission-mode execution

### Transport Layer
- **[Node Packet](node-packet.md)** — Executor-neutral, immutable node execution attempts
- **[Event, Job, Queue Record](event-job-queue.md)** — Intake events, bounded work packets, leasing lifecycle

### Execution Layer
- **[Executor Session](executor-session.md)** — Session lifecycle, completion identity, quarantine
- **[Engagement](engagement.md)** — Multi-node mission engagements, evidence manifests

### Verification Layer
- **[Verdict Receipt](verdict-receipt.md)** — Two-lane evaluation receipts (criteria + integrity)

## Data Flow

```
Event (intake) → Job (bounded work) → Queue Record (lifecycle)
                                          ↓
                                    Node Packet (immutable attempt)
                                          ↓
                                    Executor Session (remote execution)
                                          ↓
                                    Evidence Manifest (per-node artifacts)
                                          ↓
                                    Verdict Receipt (two-lane evaluation)
                                          ↓
                                    Gate Token (provisional admission)
                                          ↓
                                    Graph Truth (human-accepted node status)
```

## Key Design Principles

1. **Evidence over authority** — Tests, verdicts, and evaluator results are evidence; only human-accepted node status is graph truth
2. **Immutability where it matters** — NodePackets and verdict receipts are frozen; executor sessions track state transitions
3. **Completion identity** — SHA-256 digests bind normalized completion evidence; conflicts trigger quarantine
4. **Quarantine over laundering** — Digest conflicts preserve both envelopes and route to human review
5. **Gates are admission, not lifecycle** — Gate tokens signal readiness; they never block or raise into callers

## Source Locations

| Primitive | Primary Source |
|-----------|---------------|
| NodePacket, SessionRef, PatchResult, Engagement* | `scripts/adapters/executor_protocol.py` |
| Events, Jobs, Queue Records, Results, Executor Sessions | `scripts/init_db.py` |
| VerdictReceipt, Lane Outputs | `scripts/runtime/verification/schemas.py` |
| NodeData, ProjectGraph | `scripts/runtime/heartbeat/graph_reader.py` |
| Gate Tokens | `scripts/runtime/gates.py` |
| Completion Discipline | `scripts/runtime/heartbeat/completion_discipline.py` |
| Mission Evidence | `scripts/adapters/mission_evidence.py` |
| Engagement Dispatch | `scripts/adapters/mission_adapter.py` |

## Active Contributors

- Saboor

---

Each page documents fields, states, producers, consumers, and concrete source file paths.
