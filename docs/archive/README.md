## What This Is

GDDP is a system for turning software projects into explicit maps of work, then using agents to move through those maps without losing human control.

## Agentic Developer Tools Landscape

Most agentic developer tools today fall into two camps. Inline assistants like Cursor, Windsurf, and Copilot's agent mode operate synchronously inside a single editor session, useful for line‑by‑line work bounded by whatever the developer happens to be looking at. Agents like Jules, Devin, and Codex go further: they take a task description, open PRs, and can even ship code while you sleep. Defining scope becomes a balancing act between giving the agent enough freedom to be effective while ensuring that the agent doesn't overreach. Essentially, if you are not highly specific, they either under‑ or over‑reach; they decide their own scope. You give them a goal and trust the model to figure out what counts as done.

## GDDP Premise

GDDP sits between those camps with a different premise: **scope is not the agent’s job**. Work is decomposed up front into a dependency graph with explicit acceptance criteria, constraints, and bounded scopes. Agents read nodes from that graph, execute the work, and produce structured receipts. The system does not automatically declare work complete.

## Evaluator Agent

Upon "completion" of implementation, each node triggers an "evaluator agent," an agent with a custom harness operating on an OpenClaw‑style heartbeat schedule. The heartbeat is crucial; it ensures the agent has the freshest context and is solely focused on evaluating the work against the acceptance criteria. After the evaluator determines the work against the node's defined criteria, it transitions to evaluating the graph to ensure the project remains in integrity with the latest local changes. Deterministic checks, like noting test results, are cheap and fast. Too often with agentic development, tests are shaped by the code, making them the lowest level of verification, but graph invariants and the convergence of the entire project must be evaluated, neighboring sub-systems and the entire project are where the true evaluations need to happen.  

Importantly, the evaluator does not actually give a graph‑mutating verdict. It stops at review: a human decides whether to accept, retry, or block each piece of work before graph truth advances. The evaluator can notice drift, scope creep, or outright failure, and give the executor instructions to handle those issues, for up to N retries (configurable per node).

## Runtime Repository

This is the runtime repository: the execution and orchestration machinery. It reads human‑owned project truth from a separate configuration repository (`gddp‑config`), dispatches bounded work to executor adapters, persists runtime state and structured receipts in SQLite, and stops at review. It does not define project truth, and it does not automatically mutate graph state on the return path.
---

## Why This Matters

This is a working control plane for **bounded agent autonomy**. I use "Graph-Driven Development Pipeline" as shorthand, but more accurately, this project is a semi-autonomous graph-driven agentic development pipeline with human-in-the-loop style review.   

If you’ve used Jules or Devin, you know the async model: write a prompt, get a PR, review the diff, and hope the agent picked the right scope. If you’ve used Cursor or Claude Code, you know the synchronous model: the agent runs in your editor while you steer turn by turn. Both work. Neither answers a different question: how does a long-running software project decide what work is ready to execute next?

GDDP’s answer is a human-owned project graph in gddp-config. Each node defines its own scope, acceptance criteria, dependencies, and execution constraints. The graph defines what work is possible. The runtime continuously evaluates graph state, identifies runnable nodes, applies scheduling policy, builds a job packet from the node specification, and dispatches it through an executor adapter.

Today that adapter routes work to Jules through GitHub Actions labels. The dispatch contract is executor-agnostic: Codex, Pi, Droid, or any custom execution harness can implement the same interface while the graph remains the canonical source of project intent.The system has:

- **Graph-driven dispatch**: A heartbeat loop reads the project graph
  from YAML, identifies ready nodes, classifies events, builds job
  payloads from node specs, and dispatches via executor adapters.
- **Receipt-based return flow**: When a PR merges, the system converts
  it into a structured receipt with artifact references and moves the
  job into `awaiting_review`. No silent writeback to graph truth, no claiming work is valid, complete, or accepted.
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
writeback. The graph is isolated to preserve human intent; nothing is accepted until *you* say so.
