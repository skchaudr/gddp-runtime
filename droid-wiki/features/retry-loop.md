# Retry loop

Not every non-pass verdict should go straight to a human. When the evaluator finds concrete, fixable problems, evidence-referenced findings with file paths and line numbers, the runtime can give the executor another shot instead of wasting a human review cycle. The retry loop is the mechanism that decides when to re-dispatch and when to hand off.

The logic is split across two files: `retry_budget.py` answers the yes-or-no question "should this verdict trigger a retry?", and `return_router.py` does the actual re-dispatch with findings injected into the new issue body.

## The four conditions

`should_retry()` in `retry_budget.py` returns `True` only when all four conditions hold:

1. **The combined verdict is non-pass.** A `pass` verdict never triggers a retry; the job routes to `awaiting_review` for normal human acceptance.
2. **The integrity findings have evidence references.** The function `has_evidence_references()` searches each finding's summary and the integrity output's reasoning for file paths (anything matching `[\w/]+\.\w+`, e.g. `src/foo.py`, `lib/common.zsh`) or line references (`foo.py:42`). Findings without evidence references, things like "the code feels wrong," route to `awaiting_review` because the executor has nothing concrete to fix.
3. **`retry_budget > 0` in the project's `project.yaml`.** The budget is read from `execution_policy.retry_budget` in the project graph config. A budget of 0 disables retries entirely. This dial is human-owned, set per project, and lives in `gddp-config` (never mutated by the runtime).
4. **`attempt < max_attempts`.** The `attempt` and `max_attempts` columns on the `jobs` table track how many times this job has been dispatched and the hard ceiling. The effective cap is `min(retry_budget, max_attempts)`: the budget is the primary dial, and `max_attempts` is a backstop.

If any condition fails, the job routes to `awaiting_review` and the human sees the findings.

## How the budget is structured

The retry budget is deliberately a single human-controlled dial. `retry_budget` is the actual count: budget=1 means one retry, budget=3 means three. `max_attempts` exists as a backstop on the jobs table (defaulting to 3) so a misconfigured budget cannot create an infinite loop. The effective cap is the lower of the two, computed as `min(retry_budget, max_attempts)`.

The budget check is isolated in one wrappable function (`should_retry`) so that future modes can replace the heuristic without touching the return router. The current heuristic is simple: if there are file paths or line references in the findings, the executor has something to work with.

## Re-dispatch with findings

When `should_retry()` returns `True`, the return router calls `_redispatch_with_findings()` in `return_router.py`. The flow:

1. **Increment the attempt counter.** The job's `attempt` column is bumped by one in SQLite.
2. **Build the job payload with findings.** The previous verdict, integrity verdict, findings list, and reasoning are attached to the job dict under a `_previous_findings` key. The dispatcher's adapter picks this up and includes it in the new GitHub issue body, so the executor sees exactly what the evaluator flagged.
3. **Dispatch.** The job is sent to the executor adapter via `heartbeat/dispatcher.py`, same as the original dispatch.
4. **Handle failure.** If the dispatch fails, the job falls back to `awaiting_review` so the human can inspect the findings and decide manually. The job never sits in limbo: a failed re-dispatch is recoverable, not silent.

The return from `_redispatch_with_findings()` carries a `redispatched` status with the new issue URL, or a `needs_review` status with `dispatch_attempted: true` and the error if the dispatch failed.

## Why this is not automatic graph advancement

The retry loop re-dispatches work to the executor. It does not advance the node, change the project graph, or mark anything as complete. The node stays in its current state. The executor produces another PR, that PR merges, and the return router runs the whole flow again: parse, verify, write receipt, check retry budget. If the budget is exhausted or the findings are still non-pass, the job lands at `awaiting_review` for a human.

## Proven live (2026-07-11/12)

The loop has fired for real once, by design. The canary node `canary-retry-proof`
(`job_20260711T17104259`) buried one acceptance criterion — a `docs/echo-usage.md`
file — in the criteria list while omitting it from the goal and required
artifacts, so the executor would miss it on attempt one. It did; the evaluator
judged the criterion fail with a file-path evidence reference; `should_retry()`
said yes; attempt two landed with all three criteria met. Two result rows in
the `results` table (2026-07-11T17:35Z and 2026-07-12T07:16Z) are the receipt.
Trail: `.handoffs/037-mini-clean-baseline-startup.md`, artifacts in
`jobs/job_20260711T17104259/`.

## Key source files

| File | Purpose |
|---|---|
| `scripts/runtime/verification/retry_budget.py` | The budget check: `should_retry()` and `has_evidence_references()`. One wrappable function so modes can replace the heuristic. |
| `scripts/runtime/return_router.py` | `_redispatch_with_findings()` increments the attempt, injects findings into the job payload, dispatches, and falls back to `awaiting_review` on failure. |

## Related pages

- [Receipt-based return](receipt-based-return.md)
- [Features](index.md)
- [Architecture](../overview/architecture.md)
- [Verification system](../systems/verification.md)
- [Return router system](../systems/return-router.md)
