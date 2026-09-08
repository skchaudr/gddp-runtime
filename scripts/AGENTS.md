{
  "schema_version": "2.0",
  "scope": "scripts",
  "description": "System invariants and current implementation boundaries governing runtime scripts, control plane commands, and verification harnesses.",
  "invariants": [
    {
      "id": "scripts.evaluation-precedes-admission-control",
      "name": "Evaluation Precedes Admission Control",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#3-evaluator--verification-integrity",
      "rule": "Allow the evaluator to examine evidence and formulate verdicts across all completed attempts regardless of intermediate check results.",
      "current_implementation": "Evaluation pipeline executes full verification pass producing verdict receipts, even when individual tests or linters return failures.",
      "drift_pattern": "Terminating or short-circuiting the evaluation pipeline early because an intermediate script or gate check reported issues.",
      "source": "docs/invariants/invariants.md#3-evaluator--verification-integrity"
    },
    {
      "id": "scripts.frozen-infrastructure-discipline",
      "name": "Frozen Infrastructure Discipline",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#5-execution-isolation--infrastructure-boundaries",
      "rule": "Maintain frozen surfaces without modification unless an approved node explicitly targets them.",
      "current_implementation": "Frozen surfaces (scripts/intake_server.py, scripts/adapters/jules_*, scripts/rollback.py, scripts/export_evaluations.py) remain unmaintained unless specifically governed by a node.",
      "drift_pattern": "Refactoring scripts/intake_server.py or legacy adapters during unrelated tasks.",
      "source": "docs/invariants/invariants.md#5-execution-isolation--infrastructure-boundaries"
    }
  ],
  "current_implementation": [
    {
      "id": "scripts.canonical-gddp-control-plane",
      "name": "Canonical GDDP Control Plane",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Execute job and queue operations through gddp jobs commands, treating backend scripts as underlying implementation details.",
      "current_implementation": "/Users/sab-mini/bin/gddp wraps scripts/jobs_status.py and provides subcommands for list, show, set, and retry.",
      "drift_pattern": "Instructing operators to invoke scripts/jobs_status.py directly or writing ad-hoc python scripts to manipulate database rows.",
      "source": "AGENTS.md"
    },
    {
      "id": "scripts.tests-can-fail-nodes-can-pass",
      "name": "Tests Can Fail, Nodes Can Pass",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Treat test suites as implementation evidence while evaluating overall node satisfaction against project intent.",
      "current_implementation": "Evaluator checks whether failing tests indicate temporary implementation imperfections rather than intent defects before deciding verdicts.",
      "drift_pattern": "Rejecting a node outright or assuming graph failure solely because an ancillary test failed.",
      "source": "docs/decisions/Tests-can-fail-nodes-can-pass.md"
    },
    {
      "id": "scripts.verify-before-building-architecture",
      "name": "Verify Before Building Architecture",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Verify runtime behavior and system state with live tests and empirical inspection prior to formulating architectural proposals.",
      "current_implementation": "Engineers and agents use sub-second deterministic tests and direct state inspections to confirm assumptions before proposing architectural additions.",
      "drift_pattern": "Assuming system behavior, encountering failure, and creating complex workarounds around unverified assumptions.",
      "source": "AGENTS.md#common-failure-pattern-2026-07-30"
    }
  ]
}
