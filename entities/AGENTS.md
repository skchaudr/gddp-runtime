{
  "schema_version": "2.0",
  "scope": "entities",
  "description": "System invariants and current implementation boundaries governing domain entities, node authority, and evaluation boundaries.",
  "invariants": [
    {
      "id": "entities.sole-acceptance-authority",
      "name": "Sole Acceptance Authority on Graph Truth",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#1-human-authority-on-graph-truth",
      "rule": "Reserve node acceptance transitions exclusively for human operators using gddp control plane tooling.",
      "current_implementation": "Human operators invoke gddp node browse or update node YAML files in gddp-config directly; runtime evaluators only emit verdict receipts.",
      "drift_pattern": "Allowing evaluators, executors, or automated test suites to mark graph nodes accepted.",
      "source": "docs/invariants/invariants.md#1-human-authority-on-graph-truth"
    },
    {
      "id": "entities.automated-gates-second-to-last",
      "name": "Automated Gates are Second-to-Last",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#1-human-authority-on-graph-truth",
      "rule": "Treat all test results, execution receipts, and evaluator verdicts as advisory evidence presented for human review.",
      "current_implementation": "Evaluator compiles two verification lanes (deterministic criteria lane and semantic intent/integrity lane) into a verdict receipt for human operator review.",
      "drift_pattern": "Equating green test passes or positive verdicts with completed graph truth.",
      "source": "docs/invariants/invariants.md#1-human-authority-on-graph-truth"
    },
    {
      "id": "entities.node-atomic-unit-of-intent",
      "name": "Node as Atomic Unit of Intent",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#2-intent-preservation--node-integrity",
      "rule": "Scope all implementation, validation, and evaluation strictly to the declared boundaries and criteria of the target node.",
      "current_implementation": "Nodes declared in gddp-config/graphs/<project>/nodes/*.yaml define criteria, dependencies, context files, and execution policies.",
      "drift_pattern": "Expanding node boundaries during execution or treating uncommitted ideas as part of node scope.",
      "source": "docs/invariants/invariants.md#2-intent-preservation--node-integrity"
    },
    {
      "id": "entities.context-separation-evaluator",
      "name": "Context Separation Between Execution and Evaluation",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#3-evaluator--verification-integrity",
      "rule": "Construct evaluation contexts independently from project intent and graph truth, isolating the evaluator from executor scratchpads and transient prompts.",
      "current_implementation": "Evaluator harness isolates prompt construction from worker session scratchpads, feeding project context and target node criteria directly.",
      "drift_pattern": "Feeding executor conversation histories or worker reasoning directly into evaluator prompts.",
      "source": "docs/invariants/invariants.md#3-evaluator--verification-integrity"
    },
    {
      "id": "entities.node-immutability-during-retries",
      "name": "Node Immutability During Retries",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#2-intent-preservation--node-integrity",
      "rule": "Maintain node YAML definitions intact during retry attempts, injecting previous evaluator findings into executor prompts as corrective tasks.",
      "current_implementation": "Retry execution retains the original node YAML definition unchanged and appends evaluator critique findings as a fix-list.",
      "drift_pattern": "Modifying acceptance criteria or loosening constraints in node YAML to force failing retries to pass.",
      "source": "docs/invariants/invariants.md#2-intent-preservation--node-integrity"
    }
  ],
  "current_implementation": [
    {
      "id": "entities.provisional-traversal-gating",
      "name": "Provisional Traversal Gating",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Use project-level configuration to govern whether provisional evaluator passes advance the frontier automatically.",
      "current_implementation": "Configured per graph in project.yaml via frontier_auto_advance; set to false in gddp-dogfood to hold execution at human review boundaries.",
      "drift_pattern": "Assuming provisional status automatically advances the execution frontier across all projects.",
      "source": "gddp-config/graphs/gddp-dogfood/project.yaml"
    }
  ]
}
