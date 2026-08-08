# Parallel dispatch

Active contributors: Saboor

## Purpose

Parallel dispatch starts independent ready nodes together while preventing overlapping heartbeat processes from exceeding project capacity or reserving the same node twice.

## How it works

The project may set `execution_policy.max_concurrent_jobs` to a positive integer. `scripts/runtime/heartbeat/runner.py` counts jobs for the repository whose job or queue state is `ready` or `running`. If the setting is omitted, initial dispatch has no configured job cap; evaluator concurrency uses its own default.

Planning remains serialized. For each classified event, the runner:

1. resolves the node's expected base;
2. opens `BEGIN IMMEDIATE`;
3. counts existing capacity consumers;
4. rechecks node scope while holding the write lock;
5. inserts the job, queue record, and an `executor_sessions` row in `dispatching` state;
6. commits the reservation before any external executor is launched.

If capacity is full, the event returns to `received` and remains eligible for a later heartbeat. The transaction prevents two heartbeat processes from both observing the same final slot. The scope recheck prevents duplicate node reservations, and `awaiting_review` is considered active by `scripts/runtime/heartbeat/scope_checker.py`.

After all reservations are durable, `_execute_dispatches()` launches groups through a `ThreadPoolExecutor`. Ordinary adapters receive one job per future. Engagement-capable adapters receive compatible groups keyed by executor and expected base. Worker threads do not share the coordinator's SQLite connection; `_record_outcomes()` applies state changes sequentially afterward.

Reservation finalization is compare-and-set: `scripts/runtime/heartbeat/state_recorder.py` changes a session only while it remains `dispatching`. A late result cannot overwrite cancellation or recovery state. Reservations left uncertain after a heartbeat failure expire into `dispatch_failed` and require operator recovery rather than an unsafe automatic duplicate launch.

## Key files

- `scripts/runtime/heartbeat/runner.py` — capacity calculation, transactional planning, concurrent launch, and sequential outcome recording.
- `scripts/runtime/heartbeat/scope_checker.py` — duplicate-job and dependency guards.
- `scripts/runtime/heartbeat/state_recorder.py` — durable reservation and compare-and-set finalization.
- `scripts/runtime/heartbeat/dispatcher.py` — adapter selection and node-packet dispatch.
- `scripts/runtime/heartbeat/test_parallel_dispatch.py` — concurrency, grouping, and existing-capacity tests.

## Modification points

Change `execution_policy.max_concurrent_jobs` in graph-owned project configuration to tune capacity. Extend adapter engagement capability through `scripts/runtime/heartbeat/dispatcher.py`; do not introduce adapter-specific concurrency outside the reservation path. Changes to capacity-consuming states, reservation leases, or lock scope belong in `scripts/runtime/heartbeat/runner.py` and `scripts/runtime/heartbeat/state_recorder.py` and should include competing-heartbeat tests.

See [Heartbeat](../systems/heartbeat.md), [Executor adapters](../systems/executor-adapters.md), [Event, job, and queue record](../primitives/event-job-queue.md), [Executor session](../primitives/executor-session.md), and [Mission engagements](mission-engagements.md).
