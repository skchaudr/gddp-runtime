## What This Is

GDDP is a system for turning software projects into explicit maps of work,
then using agents to move through those maps without losing human control.

Most agentic developer tools today fall into two camps. Inline assistants
like Cursor, Windsurf, and Copilot's agent mode operate synchronously
inside a single editor session — useful for line-by-line work but bounded
by whatever the developer happens to be looking at. Async cloud agents
like Jules, Devin, and Codex go further: they take a task description,
open PRs, and ship code while you sleep. But they decide their own scope.
You give them a goal and trust the model to figure out what counts as done.

GDDP sits between those camps with a different premise: **scope is not the
agent's job**. Work is decomposed up front into a dependency graph with
explicit acceptance criteria, constraints, and bounded scopes. Agents read
nodes from that graph, execute the work, and produce structured receipts.
The system does not automatically declare work complete. It stops at
review: a human decides whether to accept, retry, or block each piece of
work before graph truth advances.

This is the runtime repository: the execution and orchestration machinery.
It reads human-owned project truth from a separate configuration repository
(`gddp-config`), dispatches bounded work to executor adapters, persists
runtime state and structured receipts in SQLite, and stops at review. It
does not define project truth, and it does not automatically mutate graph
state on the return path.

---

## Why This Matters

### For Engineers

This is a working control plane for **bounded agent autonomy**. The
interesting word is "bounded."

If you've used Jules or Devin, you know the async model: write a prompt,
get a PR, review the diff, and hope the agent picked the right scope. If
you've used Cursor or Claude Code, you know the synchronous model: agent
runs in your editor, you steer turn by turn. Both work. Neither answers
the question of *who decides what the agent should do next on a project
that spans weeks and multiple repos.*

GDDP's answer: a human-owned project graph in `gddp-config`, with each
node carrying its own scope, acceptance criteria, and dependency edges.
The runtime's job is to find ready nodes (deps complete, no active jobs),
build a job payload from the node spec, and dispatch to an executor
adapter. Today that adapter routes work to Jules via GitHub Actions
labels. The pattern is executor-agnostic — Codex, a local harness like
Pi, or a custom executor can plug in behind the same dispatch contract.

The system has:

- **Graph-driven dispatch**: A heartbeat loop reads the project graph
  from YAML, identifies ready nodes, classifies events, builds job
  payloads from node specs, and dispatches via executor adapters.
- **Receipt-based return flow**: When a PR merges, the system converts
  it into a structured receipt with artifact references and moves the
  job into `awaiting_review`. No silent writeback to graph truth.
- **SQLite state persistence**: Every event, job, queue record, and
  result is a row. State is auditable and replayable;
  `python3 -m runtime.replay` lets you reprocess return events or
  re-dispatch jobs from persisted state.
- **Executor adapters**: `adapters/jules_action_adapter.py` is the
  working adapter. Adding a new executor means writing a new adapter
  against the same dispatch contract — not rewriting the orchestration
  layer.
- **Manual review workflow**: When a job lands in `awaiting_review`,
  the operator takes exactly one manual action: accept (update graph
  truth), retry (re-dispatch from persisted state), block (record the
  blocker), defer (leave for later), or reopen/supersede.

No automatic node advancement. No automatic review. No automatic graph
writeback in this phase.
