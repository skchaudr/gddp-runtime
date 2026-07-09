# Development workflow

Work in GDDP Runtime moves through a graph-driven loop, not a ticket queue. This page covers the full cycle, the local dry-run flow, and the branch/commit/test cycle for day-to-day development.

## The graph-driven workflow

The runtime reads project graphs from `gddp-config`, dispatches work to executor agents, records state in SQLite, evaluates returned work, and halts at a human review gate. The cycle is:

1. **Nodes in gddp-config.** The operator defines project graphs as YAML files in `gddp-config/graphs/<project-id>/project.yaml`. Each node has a status (`ready`, `in_progress`, `complete`, `blocked`). The runtime reads these graphs but never mutates them. Graph truth is human-owned.

2. **Heartbeat dispatches.** The heartbeat runner (`scripts/runtime/heartbeat/runner.py`) wakes on a cron tick (every 5 minutes on Big Pi), reads the project graph, finds ready nodes whose dependencies are complete and which have no active jobs, classifies pending events, and dispatches work to executor adapters. See the [Heartbeat system](../systems/heartbeat.md) page for details.

3. **Executor works.** The Jules adapter opens a GitHub issue on the target repository with a bounded work packet derived from the node's goal and context. The executor agent works on that issue and opens a PR when done.

4. **PR merges.** When the PR merges, GitHub sends a webhook to the intake server (`scripts/intake_server.py`), which normalizes the event and writes it to the `events` table. The return router picks up the merged-PR event and converts it into a structured receipt in the `results` table.

5. **Receipt and verification.** The return router runs the two-lane evaluator on the returned work. The criteria lane runs deterministic probes and a semantic LLM agent. The integrity lane checks for intent drift and project integrity. The two lanes combine worst-of into a verdict receipt. See the [Verification system](../systems/verification.md) page for the full evaluator architecture.

6. **Human review.** The job routes to `awaiting_review` regardless of verdict. The operator inspects the receipt, the artifacts, and the merged PR, then chooses one of five actions: accept, retry, block, defer, or reopen/supersede. Accept means updating graph truth manually in `gddp-config`. Only this human action advances node status.

7. **Accept, retry, or block.** Accept moves the node to complete in `gddp-config` and may unblock downstream nodes. Retry re-dispatches the job from persisted runtime state. Block records a blocker without advancing the graph. The runtime does not perform any of these actions automatically.

The key invariant: the runtime produces evidence. The human moves graph truth. See [`docs/Tests-can-fail-nodes-can-pass.md`](../../docs/Tests-can-fail-nodes-can-pass.md) and [`docs/GDDP-becomes-small-and-real.md`](../../docs/GDDP-becomes-small-and-real.md) for the doctrine behind this separation.

## Local dry-run flow

The dry run (`scripts/dry_run.py`) walks one mock GitHub PR event through the full pipeline without calling real executors, the GitHub API, or any LLM. It uses SQLite only and mocks the verification bridge. The flow is:

inject event, classify, scope check, create job, queue, simulate result, write artifacts, simulate merged PR, return router.

```bash
python3 scripts/dry_run.py
```

This is the fastest way to practice the runtime loop locally. It validates that the pipeline plumbing works end to end without dispatching real work or spending API credits. The `setup.sh` script runs it as part of the initial setup check.

## Branch, commit, and test cycle

Day-to-day development follows the standard cycle: branch, edit, test, commit, push.

```bash
git checkout -b <descriptive-branch-name>
# make changes
python3 -m pytest -q          # 212 tests, should all pass
git add <files>
git commit -m "<message>"
git push -u origin <branch>
```

### Start-of-session contract

`AGENTS.md` defines a start-of-session contract that every agent session must follow before editing:

1. **Run `git status --short --branch`** before editing. If it is not clean, stop and classify the existing state: tracked changes, untracked files, ignored generated files, or branch divergence.
2. **Do not overwrite, delete, rename, reformat, or "clean up" inherited changes** until you know whether they are user work, another agent's work, or generated noise. If unsure, ask.
3. **Verify branch and upstream** before work: `git branch --show-current`, `git rev-parse --abbrev-ref --symbolic-full-name @{u}` when available, and `git fetch --prune` before merge/rebase decisions.
4. **If work continues from another branch**, first understand whether it should be merged, rebased, abandoned, or left as a PR branch. Do not create parallel branches for the same task without a reason recorded in the handoff.

### During-work rules

- Keep changes scoped to the requested task. Separate formatting-only churn from functional changes unless the formatter is the task.
- Update `.gitignore` as soon as a tool creates repeatable local noise, but do not hide meaningful source artifacts to get a clean status.
- Make small commits at coherent checkpoints. A repo with hours of uncommitted agent work is an unsafe handoff state.
- Prefer existing project commands from `AGENTS.md`. If a command is missing or dependencies are unavailable, run the smallest relevant validation and record the limitation.
- Never force-push, rewrite shared history, delete remote branches, or discard worktree changes unless the operator explicitly authorizes that exact action.

### Handoff requirement

At the first natural checkpoint, create or update a handoff in `.handoffs/` so the next session can resume without archaeology. Keep `.handoffs/000-template.md` as the canonical template. Fill only the Agent Section. Keep it short and empirical: date, branch, touched files, git state, artifacts, and exact resume point.

### End-of-session contract

Before claiming done: run validation (`python3 -m pytest -q`), check `git status --short --branch` (target is clean and synced), commit all intended changes, push the working branch, and leave a concise handoff. See [`/Users/sab-mini/repos/gddp-runtime/AGENTS.md`](../../AGENTS.md) for the full not-done triggers list.

## Related pages

- [Testing](testing.md) - the 212-test suite and what it covers
- [Patterns and conventions](patterns-and-conventions.md) - invariants and coding style
- [Getting started](../overview/getting-started.md) - install and first run
- [Decision loop](../systems/decision-loop.md) - the engine that wakes, reads context, decides, acts
