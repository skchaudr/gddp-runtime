```json
{
  "schema_version": "2.0",
  "scope": "project",
  "description": "Master index of system invariants and current implementation boundaries across all gddp-runtime architectural surfaces.",
  "folders": {
    "deploy": "deploy/AGENTS.md",
    "entities": "entities/AGENTS.md",
    "events": "events/AGENTS.md",
    "jobs": "jobs/AGENTS.md",
    "node_status_history": "node_status_history/AGENTS.md",
    "scripts": "scripts/AGENTS.md"
  },
  "invariants": [
    {
      "id": "system.human-authority-on-graph-truth",
      "name": "Human Authority on Graph Truth",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#1-human-authority-on-graph-truth",
      "rule": "Preserve all node acceptance and graph truth modifications exclusively for human operators.",
      "current_implementation": "Human operator uses gddp node browse to accept nodes; evaluators produce verdict receipts but cannot mark nodes accepted.",
      "drift_pattern": "Automated scripts or evaluators modifying node YAML status to accepted.",
      "source": "docs/invariants/invariants.md#1-human-authority-on-graph-truth"
    },
    {
      "id": "system.intent-preservation-and-node-integrity",
      "name": "Intent Preservation and Node Integrity",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#2-intent-preservation--node-integrity",
      "rule": "Restrict implementation and evaluation strictly to the declared scope of the target node.",
      "current_implementation": "Target node YAML defines exact scope and criteria; discovered out-of-scope work records as separate proposal YAMLs.",
      "drift_pattern": "Expanding node scope during implementation or retries without human-approved graph amendments.",
      "source": "docs/invariants/invariants.md#2-intent-preservation--node-integrity"
    },
    {
      "id": "system.evaluator-and-verification-integrity",
      "name": "Evaluator and Verification Integrity",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#3-evaluator--verification-integrity",
      "rule": "Allow the evaluation harness to formulate independent verdict receipts on all execution returns.",
      "current_implementation": "Two-lane evaluation runs against candidate commits and writes immutable receipts under .gddp/receipts/.",
      "drift_pattern": "Preempting evaluation when intermediate gates or unit tests encounter failures.",
      "source": "docs/invariants/invariants.md#3-evaluator--verification-integrity"
    },
    {
      "id": "system.storage-and-evidence-doctrine",
      "name": "Storage and Evidence Doctrine",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#4-storage--evidence-doctrine",
      "rule": "Treat durable files and git refs as primary evidence, treating databases as disposable caches.",
      "current_implementation": "Verdict receipts and git trees serve as durable truth; db/queue.db indexes runtime records and can regenerate freely.",
      "drift_pattern": "Relying on database rows as truth while omitting durable filesystem receipts.",
      "source": "docs/invariants/invariants.md#4-storage--evidence-doctrine"
    },
    {
      "id": "system.execution-isolation-and-infrastructure-boundaries",
      "name": "Execution Isolation and Infrastructure Boundaries",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#5-execution-isolation--infrastructure-boundaries",
      "rule": "Confine all automated code mutations to isolated worktrees.",
      "current_implementation": "Executors operate inside isolated worktree directories under .worktrees/ or temporary directories.",
      "drift_pattern": "Executing mutative tasks directly in the primary workspace checkout.",
      "source": "docs/invariants/invariants.md#5-execution-isolation--infrastructure-boundaries"
    },
    {
      "id": "system.development-and-agent-workflow-invariants",
      "name": "Development and Agent Workflow Invariants",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#6-development--agent-workflow-invariants",
      "rule": "Author changes on dedicated branches with conventional commits and agent co-authorship trailers.",
      "current_implementation": "Feature work branches from main, records commits with agent co-authorship metadata, and documents handoffs in .handoffs/.",
      "drift_pattern": "Committing unstructured changes directly to main without agent co-authorship metadata.",
      "source": "docs/invariants/invariants.md#6-development--agent-workflow-invariants"
    }
  ],
  "current_implementation": [
    {
      "id": "system.single-armed-control-plane-host",
      "name": "Single Armed Control Plane Host Operational Model",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Keep an active control plane armed to coordinate dispatch and intake while avoiding concurrent runner conflicts.",
      "current_implementation": "Currently deployed on sab-mini as the sole armed runner host using macOS launchd; multi-host distributed queue coordination is planned for future iterations.",
      "drift_pattern": "Treating single-host runner topology as an immutable architectural invariant rather than current deployment reality.",
      "source": "deploy/mini-heartbeat/bin/arm.sh"
    }
  ]
}
```
