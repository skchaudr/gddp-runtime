```json
{
  "schema_version": "2.0",
  "scope": "node_status_history",
  "description": "System invariants and current implementation boundaries governing historical transition records and operator audit trails.",
  "invariants": [
    {
      "id": "node_status_history.audit-trail-distinct-from-graph-state",
      "name": "Audit Trail Subordinate to Graph Truth",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#1-human-authority-on-graph-truth",
      "rule": "Read current graph frontier status from node YAML definitions in gddp-config, using node_status_history purely for historical audit context.",
      "current_implementation": "Active node statuses reside in gddp-config/graphs/<project>/nodes/*.yaml, while historical operator decisions append to JSONL files in node_status_history/.",
      "drift_pattern": "Querying node_status_history to determine current readiness or frontier dispatchability.",
      "source": "docs/invariants/invariants.md#1-human-authority-on-graph-truth"
    }
  ],
  "current_implementation": [
    {
      "id": "node_status_history.append-only-evidence",
      "name": "Append-Only Audit Evidence",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Preserve all historical status transition records as immutable, append-only logs.",
      "current_implementation": "node_status_history/<project>.jsonl records chronological JSON objects documenting operator and transition details.",
      "drift_pattern": "Deleting or editing past JSONL entries to scrub failed attempts or alter timestamps.",
      "source": "node_status_history/context.md#2-invariants"
    },
    {
      "id": "node_status_history.tooling-managed-transitions",
      "name": "Tooling-Managed Transitions",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Generate status history entries exclusively through established control plane commands and designated scripts.",
      "current_implementation": "scripts/node_status_history.py appends transition entries during gddp node browse and CLI commands.",
      "drift_pattern": "Manually authoring arbitrary lines in node_status_history JSONL files outside control plane tooling.",
      "source": "node_status_history/context.md#2-invariants"
    }
  ]
}
```
