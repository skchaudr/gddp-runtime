```json
{
  "schema_version": "2.0",
  "scope": "events",
  "description": "System invariants and current implementation boundaries governing operational event telemetry and runtime observability streams.",
  "invariants": [
    {
      "id": "events.telemetry-uncommitted-and-ephemeral",
      "name": "Telemetry Uncommitted and Ephemeral",
      "is_invariant": true,
      "invariant": "docs/invariants/invariants.md#4-storage--evidence-doctrine",
      "rule": "Keep all telemetry streams, raw webhook deliveries, and event logs untracked and excluded from git commits.",
      "current_implementation": "Raw webhook deliveries land under events/raw/ (ignored by git); event ingestion populates the events table in SQLite.",
      "drift_pattern": "Staging and committing raw event payloads from events/ into repository history.",
      "source": "docs/invariants/invariants.md#4-storage--evidence-doctrine"
    }
  ],
  "current_implementation": [
    {
      "id": "events.graceful-degradation-without-events",
      "name": "Graceful Degradation Without Events",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Ensure core runtime logic, dispatching, and queue processing operate reliably even with empty or purged event storage.",
      "current_implementation": "Heartbeat runner derives candidate dispatches from graph YAML files and queue records; missing local event payloads do not halt queue operations.",
      "drift_pattern": "Coupling dispatch decisions or graph progress to historical event files.",
      "source": "events/context.md#2-invariants"
    },
    {
      "id": "events.informational-telemetry-boundary",
      "name": "Informational Telemetry Boundary",
      "is_invariant": false,
      "invariant": "n/a",
      "rule": "Rely on durable receipts and graph YAMLs as authorities of record, treating event logs purely as live observability.",
      "current_implementation": "Webhook events trigger initial dispatch evaluations, while final state transitions depend entirely on execution results and verdict receipts.",
      "drift_pattern": "Deriving queue state or execution success directly from event logs rather than receipts.",
      "source": "events/context.md#1-event-telemetry--purpose"
    }
  ]
}
```
