# Dispatch Concurrency Cap Node Proposal

Recovered from Claude Explore agent `Map concurrency cap enforcement point`:

`~/.claude/projects/-Users-sab-mini-repos-gddp-runtime/b78dc9ef-6d67-4319-af0b-157974386108/subagents/agent-ad62d758294acaae3.jsonl`, line 31, completed 2026-07-15T19:58:06Z.

```yaml
node_id: enforce-dispatch-concurrency-cap
title: Enforce max_concurrent_jobs during heartbeat planning
type: capability

goal: |
  Make heartbeat job reservations obey each project's
  execution_policy.max_concurrent_jobs value.

why: |
  The graph declares an executor concurrency limit, but runtime currently
  parses and ignores it. One heartbeat can reserve and dispatch every eligible
  event, violating human-owned execution policy.

acceptance_criteria:
  - The planner reads max_concurrent_jobs from ProjectGraph.execution_policy.
  - Existing project jobs in ready or running count against capacity.
  - Jobs from other projects and awaiting_review jobs do not consume capacity.
  - Jobs reserved earlier in the same tick count against later reservations.
  - When capacity is reached, no extra job is created and the event remains retryable.
  - Missing max_concurrent_jobs preserves existing uncapped behavior.
  - Tests cover cap=2 with three eligible events, existing active capacity, cross-project jobs, awaiting_review, and same-tick accounting.
  - python3 -m pytest -q passes.

constraints:
  - Enforce in runner.py planning, not inside scope_checker.py.
  - Preserve per-node duplicate-job and dependency guards.
  - Do not change graph truth, receipt semantics, or human review behavior.
  - Document that cross-process enforcement is best-effort, not DB-serialized.
  - Do not fix the separate context_reader.py dispatched-status defect here.

required_artifacts:
  - decision.md
  - result-summary.md
  - patch.diff
  - graph-update.yaml
```

Implementation point: `scripts/runtime/heartbeat/runner.py::_plan_dispatches`, after per-node scope passes and before `build_job`/`insert_job`. Compute active capacity once per tick, then include `len(planned_dispatches)` so same-tick reservations count.
