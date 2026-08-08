# Explicit node routing

Active contributors: Saboor

## Purpose

Explicit node routing prevents an untrusted or ambiguous intake event from spending executor budget. GDDP does not infer which graph node an issue “probably” means: forward execution requires a `node: <id>` tag naming a node that is currently ready.

## How it works

`scripts/runtime/heartbeat/classifier.py` processes only `issue.opened` events. It searches the event URL and branch and, when a raw webhook payload is available, the issue title and body. The accepted syntax is case-insensitive and permits separators such as `node: auth-bug`, `node auth-bug`, or `node-auth-bug`.

The captured identifier must exactly match one of the ready nodes supplied by `scripts/runtime/heartbeat/graph_reader.py`. An event with no tag, an unknown tag, a tag for a non-ready node, an unreadable payload, or the wrong event type returns no classification and is recorded as ignored by the heartbeat. There is deliberately no priority-based or semantic fallback.

The classifier normally selects the first execution mode declared by the node. A manual dispatch may include `routing.selected_executor`; the classifier honors that choice only if it appears in the node's allowed execution modes. An invalid preselection is ignored auditably rather than silently falling back to another executor.

Frontier-generated events use the same path. `scripts/runtime/heartbeat/frontier.py` creates an `issue.opened` event with a URL of the form `frontier-dispatch://node: <id>`, so automatic advancement does not bypass classification.

## Key files

- `scripts/runtime/heartbeat/classifier.py` — tag sources, parsing, ready-node match, and executor recommendation.
- `scripts/runtime/heartbeat/runner.py` — claims events, invokes classification, and records ignored events.
- `scripts/runtime/heartbeat/graph_reader.py` — supplies ready nodes and validates allowed execution modes.
- `scripts/runtime/heartbeat/test_classifier.py` — explicit-tag and no-fallback behavior.
- `scripts/runtime/heartbeat/test_classifier_routing.py` — operator executor preselection.

## Integration and modification points

Change `_NODE_TAG_RE` or `_tag_sources()` in `scripts/runtime/heartbeat/classifier.py` to alter accepted syntax or trusted tag locations. Change `_pick_executor()` only when changing executor-selection policy; do not add guessed-node fallback there. New intake sources should normalize to the event schema and preserve a raw payload path if title or body routing is required.

Routing hands a matched node to scope, capacity reservation, and dispatch. See [Heartbeat](../systems/heartbeat.md), [Event, job, and queue record](../primitives/event-job-queue.md), and [Parallel dispatch](parallel-dispatch.md).
