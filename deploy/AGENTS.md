{
  "schema_version": "2.0",
  "scope": "deploy",
  "description": "System invariants and current implementation boundaries governing deployment, service management, and host synchronization.",
  "invariants": [
    {
      "id": "deploy.frozen-deployment-surfaces",
      "name": "Frozen Deployment Surfaces",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#5-execution-isolation--infrastructure-boundaries",
      "rule": "Preserve frozen deployment surfaces (deploy/rig1-heartbeat/, deploy/deploy.sh) dormant and untouched unless explicitly targeted by a human-approved node.",
      "current_implementation": "Legacy deploy scripts remain dormant in repository without active maintenance; active local execution relies on deploy/mini-heartbeat/.",
      "drift_pattern": "Speculatively refactoring or fixing frozen deployment surfaces without explicit node governance.",
      "source": "docs/invariants/invariants.md#5-execution-isolation--infrastructure-boundaries"
    }
  ],
  "current_implementation": [
    {
      "id": "deploy.always-on-control-plane",
      "name": "Always-On Active Control Plane",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Maintain continuous control plane availability for event intake and heartbeat processing.",
      "current_implementation": "Currently operated as a single armed host (sab-mini) via launchd and deploy/mini-heartbeat kit to avoid uncoordinated concurrent queue polling across hosts.",
      "drift_pattern": "Treating single-machine deployment as permanent system law rather than an operational constraint of uncoordinated local runners.",
      "source": "deploy/mini-heartbeat/bin/arm.sh"
    },
    {
      "id": "deploy.mini-heartbeat-kit-execution",
      "name": "Mini-Heartbeat Kit Execution Entrypoint",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Launch heartbeat runs via deploy/mini-heartbeat/bin/ (arm.sh, smoke.sh, launchd) to load required runtime environment variables and attempt spools.",
      "current_implementation": "deploy/mini-heartbeat/bin/common.sh sources deploy/mini-heartbeat/env/gddp.env and configures GDDP_LOCAL_SUBPROCESS_ARGV for the runner.",
      "drift_pattern": "Calling scripts/runtime/heartbeat/runner.py directly in ad-hoc shells without required environment and spool configuration.",
      "source": "AGENTS.md#heartbeat-entrypoint-agents"
    },
    {
      "id": "deploy.git-fast-forward-host-sync",
      "name": "Git Fast-Forward Host Synchronization",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Synchronize control plane hosts by pulling tracked commits with fast-forward updates.",
      "current_implementation": "Production host code changes arrive via git pull --ff-only on origin/main prior to armed heartbeat executions.",
      "drift_pattern": "Applying out-of-band scp, rsync, or untracked manual edits directly on production hosts.",
      "source": "AGENTS.md#agent-driven-development-workflow"
    }
  ]
}
