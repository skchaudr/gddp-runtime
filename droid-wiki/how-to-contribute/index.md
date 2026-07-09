# How to contribute

GDDP Runtime is a solo project. There is no CODEOWNERS file, no formal pull-request process, and no external contribution channel. The operator (Sab) manages all work through the GDDP graph itself, not through GitHub issues or PRs from outside contributors.

If you are an agent or collaborator working in this repo, you are operating inside the graph-driven workflow, not submitting patches to an open-source project. The sections below describe how work actually moves through this system.

## Work pickup

Work is defined as nodes in `gddp-config` project graphs, not as GitHub issues or a backlog spreadsheet. The runtime reads those graphs, finds ready nodes, and dispatches them to executor agents. There is no "claim an issue" step for humans. The operator writes graph truth in `gddp-config`; the runtime executes against it.

If you are an agent session starting work, the first thing you do is read [`/Users/sab-mini/repos/gddp-runtime/AGENTS.md`](../../AGENTS.md) and follow the start-of-session contract: check `git status`, classify inherited state, verify the branch. See [Development workflow](development-workflow.md) for the full loop.

## PR process

Pull requests here are executor output, not contributor submissions. When Jules or another executor completes a node, it opens a PR against the target repository. That PR merging triggers the return router, which creates a structured receipt and routes the job to `awaiting_review`. The PR itself is evidence, not graph truth. See [Patterns and conventions](patterns-and-conventions.md) for the invariants that govern this flow.

There is no code review tooling beyond the human review gate. The evaluator runs a two-lane verification pass (deterministic probes plus semantic and integrity review) and produces a verdict receipt. That verdict is evidence for the human reviewer. The human decides whether graph truth advances.

## Review expectations

The human review gate is the last step. When a job reaches `awaiting_review`, the operator inspects:

- the `results` row in `db/queue.db`
- the matching job row and queue state
- the artifacts under `jobs/<job-id>/`
- the merged PR or executor output

The operator chooses one of five actions: accept, retry, block, defer, or reopen/supersede. Accept means updating graph truth manually in `gddp-config`. Retry re-dispatches the job. Block records a blocker without advancing the graph. Defer leaves the job for later. See [Development workflow](development-workflow.md) for the full decision path.

## Definition of done

A node is done when the human accepts it in graph truth. Not when the PR merges. Not when the evaluator passes. Not when tests go green. The doctrine in [`docs/Tests-can-fail-nodes-can-pass.md`](../../docs/Tests-can-fail-nodes-can-pass.md) is explicit: node status reflects accepted graph progress, not temporary implementation perfection. Tests, criteria, and evaluator verdicts are all evidence. Only human-accepted node status is graph truth.

For a work session (agent or human), the end-of-session contract in `AGENTS.md` defines done: validation run, clean git status, changes committed and pushed, and a handoff left for the next session.

## Pages in this section

- [Development workflow](development-workflow.md) - how work moves through the graph-driven loop
- [Testing](testing.md) - the 212-test suite and what it covers
- [Debugging](debugging.md) - inspecting SQLite state, replay utilities, common issues
- [Tooling](tooling.md) - build system, dev tools, and deployment scripts
- [Patterns and conventions](patterns-and-conventions.md) - invariants, coding style, naming

## Related pages

- [Getting started](../overview/getting-started.md) - install, initialize, run the dry flow
- [Deployment](../deployment.md) - systemd, cron, and the Big Pi runbook
