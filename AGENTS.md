# AGENTS.md — gddp-runtime

Evaluator produces evidence + guards intent/integrity; only a human moves a node to complete. 

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

## Project snapshot

- **Language:** Python 3.11+ (stdlib + Flask)
- **Install:** `pip install flask` (see `deploy/setup.sh` for full pi-big setup)
- **Test:** `python3 -m pytest -q` (suite); `python3 scripts/dry_run.py` for an
  end-to-end fake flow (SQLite only)
- **Lint:** none configured
- **Heavy dirs excluded from git:** `db/`, `jobs/`, `events/` (runtime state, never committed)
- **Key files:** `scripts/intake_server.py`, `scripts/dry_run.py`, `scripts/runtime/`

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
