# AGENTS.md — gddp-runtime

Evaluator produces evidence + guards intent/integrity; only a human moves a node to complete. 

`gddp` is the single operator-facing control plane. Runtime job reads and
writes route through `scripts/jobs_status.py`; that backend may update runtime
job/queue state but must never update graph/node status.

**Heartbeat entrypoint (agents):** never invoke
`python -m scripts.runtime.heartbeat.runner` (or the runner module) directly.
Use the mini-heartbeat kit only — `deploy/mini-heartbeat/bin/` (`arm.sh`,
`smoke.sh`, launchd) which sources `deploy/mini-heartbeat/env/gddp.env` via
`common.sh`. Raw runner calls skip `GDDP_LOCAL_SUBPROCESS_ARGV` / spool and
create failed jobs before any executor launches.

The goal has always been: *preserve* forward agentic momentum by detecting when a project is about to drift from user intent or project integrity. 

Not spec-driven-development; the mission here is create a agentic harness that oversees the execution of a graph of project nodes. It's entire purpose is to detect drift, both of intent or project integrity. 

The tools it will need in a "production" environment are per-project capabilities, but the baseline capabilities it will need are read-only tooling. 

Harness design and implementation + running nodes through the loop and creating project graphs is the current stage with ambition of overnight runs resulting in a continuous, semi-automated pipeline, with human intervention only when necessary.

Past versions of the runtime loop: 
GitHub webhook intake → classify → scope → queue → execute pipeline.
Python scripts in `scripts/`, deploy configs in `deploy/`, docs in `docs/`.
No requirements.txt — scripts use stdlib + Flask (see `deploy/setup.sh`).

Semi-autonomous pipeline with human-in-the-loop review and agentic evaluation is the goal. The evaluator is live: a two-lane verification pass (deterministic + semantic criteria lane, intent/integrity lane) combined worst-of into a verdict receipt. Verdicts are evidence for human review — the evaluator is the second-to-last gate, never the last.  

Portfolio brief + system narrative: [`PROJECT-BRIEF.md`](PROJECT-BRIEF.md).

Intent & architecture doctrine (read these before working on the evaluator or the graph):
- [`docs/Tests-can-fail-nodes-can-pass.md`](docs/Tests-can-fail-nodes-can-pass.md) — node status reflects accepted graph progress, not temporary implementation perfection. Tests are evidence, not graph truth. Criteria are evidence, not graph truth. Evaluator verdicts are evidence, not graph truth. Only human-accepted node status is graph truth. Do not reinterpret a failing implementation test as proof that an accepted node is false.
- [`docs/GDDP-becomes-small-and-real.md`](docs/GDDP-becomes-small-and-real.md) — GDDP is the intent-preservation and graph-integrity layer around work, not the executor and not the agent harness. GDDP does not rebuild the loop; it constrains, interprets, and verifies the loop.

## Canonical node workflow

The draft canonical graph begins with `neutral-executor-contract`, followed by
`direct-executor-round-trip` and `immediate-evaluator-round-trip`.
`concurrent-node-flow` and `graph-frontier-operations` build on the usable
evaluator loop.

The five capability nodes remain drafts until Sab has reviewed the complete set
and explicitly accepted their final definitions. Discussion, draft text,
discovered implementation context, and requested revisions do not constitute
node approval or authorization to implement, commit, or publish them.

- Treat a node as the unit of project intent. Jobs, sessions, commits, tests,
  artifacts, and verdicts are evidence from attempts to satisfy it.
- Treat every node as a human-owned proposal, not a commitment. Acceptance is
  not assumed. Human review may accept, revise, split, supersede, rewire, defer,
  or abandon a node; only the human changes graph truth.
- When implementation evidence shows that revising, splitting, superseding, or
  rewiring a node would preserve intent materially faster, safer, or more
  cleanly, stop before further implementation and submit a graph-amendment
  proposal. State why the current shape is costly, the alternative, the
  time/risk and dependency/frontier effects, and what existing work remains
  usable. Do not silently change the node or assume its current shape must land.
- Never mark a node complete from executor success, passing tests, or an
  evaluator verdict. Only the human accepts a node.
- Use one executor-neutral node packet and returned-result contract across
  all current and future executors.
- Prefer a direct executor transport for the short node round trip. Preserve
  any mediated pathway as inherited infrastructure rather than the required
  command bus.
- Attach discoveries to the current node as evidence. Create a new dependency,
  follow-up, or corrective node when the discovery creates bounded work.
- Treat real project work as the source of discovered capability, integration,
  corrective, and retry work.
- Preserve the distinction between a retry attempt against an existing node and
  a newly authored retry node until the graph design explicitly chooses one.
- Keep infrastructure subordinate to the operating loop. It must improve node
  turnaround, concurrency, durable return, recovery, observability, or
  integrity.
- Move real project nodes as soon as the minimum loop supports them. Do not wait
  for every supporting subsystem to be theoretically complete.
- Dispatch independent ready nodes concurrently within declared capacity and
  isolation constraints.
- Preserve the distinction between dependency edges and evidence links. The
  graph remains a DAG; receipts and traces explain why its frontier changed.
- Treat GitHub, Jules, Codex, and other executors as replaceable transports and
  workers. They do not own graph truth.
- When work is discovered outside the graph, stop before further implementation,
  record the current evidence, and put the remaining work into the graph. Do not
  retroactively claim the earlier work was graph-governed.

## Project snapshot

- **Language:** Python 3.11+ (stdlib + Flask)
- **Install:** `pip install flask` (see `deploy/setup.sh` for full pi-big setup)
- **Test:** `python3 -m pytest -q` (suite)
- **Lint:** none configured
- **Heavy dirs excluded from git:** `db/`, `jobs/`, `events/` (runtime state, never committed)
- **Key files:** `scripts/intake_server.py`, `scripts/runtime/`

## Agent-driven development workflow

The default reader of this repo is often another agent. Optimize for the next
session being able to start immediately, not for the current session merely
appearing done.

### Start-of-session contract

1. Run `git status --short --branch` before editing. If it is not clean, stop
   and classify the existing state as tracked changes, untracked files, ignored
   generated files, or branch divergence.
2. Do not overwrite, delete, rename, reformat, or "clean up" inherited changes
   until you know whether they are user work, another agent's work, or generated
   noise. If unsure, ask.
3. Verify branch and upstream before work: `git branch --show-current`,
   `git rev-parse --abbrev-ref --symbolic-full-name @{u}` when available, and
   `git fetch --prune` before merge/rebase decisions.
4. If work continues from another branch, first understand whether it should be
   merged, rebased, abandoned, or left as a PR branch. Do not create parallel
   branches for the same task without a reason recorded in the handoff.
5. **Production host, step zero:** on any armed control plane (`sab-mini`,
   `pi-big`, etc.), run `git pull --ff-only` before anything else. Repo files
   on production change only via git — never `scp`, never remote edits. Session
   is not done until `git status --porcelain` is empty and HEAD matches
   `origin/main`.

### During-work rules

- Keep changes scoped to the requested task. Separate formatting-only churn from
  functional/doc changes unless the formatter is the task.
- Update `.gitignore` as soon as a tool creates repeatable local noise
  (`node_modules/`, `dist/`, caches, local logs, generated media, temp exports),
  but do not hide meaningful source artifacts just to get a clean status.
- Co-author ALL Git commits with `<agent-name> + <model>` this is so crucial and must happen, failure of this weakens traceability 
- Make small commits at coherent checkpoints. A repo with hours of uncommitted
  agent work is an unsafe handoff state.
- Prefer existing project commands from this file. If a command is missing or
  dependencies are unavailable, run the smallest relevant validation you can and
  record the limitation.
- Never force-push, rewrite shared history, delete remote branches, or discard
  worktree changes unless the operator explicitly authorizes that exact action.
- Inherited uncommitted changes are evidence, not debris. Commit and push them
  unless you can prove they are noise. They may be the only copy.


### Handoff requirement

At the first natural checkpoint after the initial task is complete, or sooner if
context-window reset would help, create/update a handoff so the next session can
resume without archaeology.

- Use the root `.handoffs/` folder. If it does not exist, create it.
- Keep `.handoffs/000-template.md` as the canonical template. Do not overwrite it
  with session notes.
- For each substantive session, create the next numbered handoff file, e.g.
  `.handoffs/001-brief-description.md`.
- Fill only the `Agent Section`. Do not write below `Do NOT edit this file past
  this point`; that section is reserved for Sab.
- Keep the handoff short and empirical: date, branch, touched files, git state,
  artifacts, and exact resume point.
- A handoff is required before claiming completion if the repo had merges,
  branch changes, conflicts, generated artifacts, failing validation, or any
  state the next agent would otherwise need to rediscover.

### End-of-session contract

Before saying "done":

1. Run the relevant validation/build/test commands documented above, or explain
   exactly why they could not run.
2. Run `git status --short --branch`. The target state is clean and synced with
   upstream. If anything remains, it must be intentionally ignored or explicitly
   called out with a path and reason.
3. Commit all intended changes. Do not leave staged, unstaged, or untracked task
   artifacts for the next session to interpret.
4. Push the working branch. If the task is meant to land on `main`, merge it to
   `main`, push `main`, and verify local `main` equals `origin/main`.
5. Leave a concise handoff in the final response: branch, commit, pushed status,
   validation run, changed surfaces, and any residual risk.

### Not-done triggers

Do not report completion if any of these are true:

- uncommitted task changes remain;
- local commits are not pushed;
- the branch is diverged and unresolved;
- merge conflicts or stash entries remain;
- validation failed and no explicit follow-up decision exists;
- generated files, logs, caches, screenshots, or media are untracked and
  unclassified.

The standard is: the next agent can clone/pull, read this file, run the listed
commands, and continue without first becoming a repository janitor.

Co-author ALL Git commits with `<agent-name> + <model>` this is so crucial and must happen, failure of this weakens traceability 

