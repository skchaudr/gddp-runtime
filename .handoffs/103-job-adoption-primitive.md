# 103 — Job adoption: a birth path for work completed outside the runtime

------------------------------------------------ Agent Section START

Date: 2026-08-21
Worktree: none (design session)
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Four myapi-part2 nodes were completed by hand and committed to MyAPI; the runtime has no record of them, so they stay `ready` forever and their dependents stay blocked. Evaluation is not a graph-driven phase — it only ever runs over rows in `executor_sessions` (`reconciler.py:248`), so no session row means no evaluation regardless of node status. `gddp eval` runs the evaluator but writes nothing back, so it cannot repair graph legibility.

### Scope touched (One file per line, +/- for only what was changed)

No files changed. Design only — read reconciler.py, frontier.py, provisional_status.py, state_recorder.py, job_factory.py, dispatcher.py, graph_reader.py, gddp.py.

### Constrained areas touched (none / list + justification)

none

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

Clean on main. Untracked `.factory/` and `.local/` only.

### Artifacts (Filepath - Description, 1 line max per artifact)

This handoff file — the only artifact.

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Implement `gddp jobs adopt` per the contract below, then run it for the four nodes in §5 and let one heartbeat tick do the rest. The adoption writer is also the primitive the Air sweep evaluator needs — the sweep is this command plus candidate discovery.

------------------------------------------------ Agent Section END

## 1. The gap

Every job row in the runtime has been born from an event: an intake webhook, or
a `frontier_auto` injection (`frontier.py:199`). There is no path for "this work
already exists, record it." That is the whole gap. It is a missing birth path,
not a hard problem.

Consequences when work lands outside the runtime:

- The node keeps its pre-work status (`ready`) permanently.
- Dependents never unblock — `scope_checker` computes satisfaction live from
  graph status, and nothing moved it.
- `gddp jobs` shows nothing; there is no results row, so no evaluator evidence
  is reachable from the runtime at all.
- The graph stops being the record of the work at exactly the point you would
  want to point at it.

`frontier_auto_advance` is not the lever. It injects *dispatch* events, so
enabling it would re-run the work rather than evaluate it.

## 2. The seam that already exists

`reconciler.py:449` — a session in state `collected` carrying a
`result_commit_sha` skips polling and collection entirely and goes straight to
evaluation. It exists for crash resume, but it is shape-identical to adoption:

```
jobs row + executor_sessions row (state='collected', result_commit_sha=<sha>)
  → next tick: _reconcile_one → evaluation_batch.add
  → _run_evaluation (verify_job_return — the same call every dispatched node makes)
  → _finalize_evaluation → results row + job awaiting_review
  → maybe_mark_provisional → frontier advances dependents
```

Nothing downstream is special-cased. The only handrolled part is the two rows
standing in for a dispatch that never happened.

Verified reachability for a purely-adopted session:

- `get_active_executor_sessions` includes `collected` (`state_recorder.py:467`).
- Grouping excludes `collected` from engagement handling and routes it straight
  to `_reconcile_one` (`reconciler.py:262-295`).
- `_reconcile_one` returns at the `collected` branch before any adapter is
  instantiated, so no executor process is contacted.

## 3. Command contract

```
gddp jobs adopt --project <id> --node <id> --commit <sha> [--base <sha>]
                [--executor local_subprocess] [--dry-run]
```

Writes three rows in one transaction, then exits. It never runs the evaluator
itself — the heartbeat does, on its own schedule.

**events** — modeled on `_inject_dispatch_event` (`frontier.py:199`):

- `source`: `adopt_manual`
- `status`: `mapped` (already bound to a job; the classifier must never pick it up)
- `url`: `adopt://node: <node_id>` (keeps the node tag convention)
- `project_id`, `repo`, `project_node_candidates` from the graph

**jobs** — reuse `build_job` (`job_factory.py:28`) unchanged. Title, goal, why,
constraints, acceptance_criteria, dependencies, priority, required_artifacts all
derive from the node YAML. Override after construction:

- `status` / `queue_state`: `awaiting_result`
- `executor`: the adopt executor (see constraint below)

Do **not** insert a `queue_records` row — the job is not dispatchable.

**executor_sessions** — reuse `insert_executor_session`
(`state_recorder.py:205`) with `state="collected"`, then set:

- `result_commit_sha`: `--commit`
- `expected_base_commit_sha`: `--base`
- `session_id`: `adopt_<node_id>_<shorthash>` (no live session exists)

## 4. Constraints the implementation must respect

**Executor must be an ADAPTERS key.** `_reconcile_one` skips unknown executors
at `reconciler.py:437`, *before* the collected branch. A name like `manual`
would strand the session silently. Default to `local_subprocess` — it is the
honest label for work done in the local checkout, and it is in the map
(`dispatcher.py:36`).

**`jobs.repo` must match the heartbeat's `--repo`.**
`get_active_executor_sessions` filters by repo for cross-repo safety. Note
`myapi-part2/project.yaml` carries `repo: /Users/sab-mini/repos/MyAPI` — a
filesystem path, not `owner/name`. Verify what the myapi-part2 heartbeat passes
as `--repo` and match it exactly, or reconcile will silently skip every adopted
session. **Check this before writing any rows.**

**`--base` should be required in practice.** Without it the verifier loses its
diff boundary and evaluates the whole tree instead of the node's change. The
flag can stay optional in the parser, but warn loudly when omitted.

**Guards, all pre-write:**

- `--commit` resolves in the repo; `--base` is an ancestor of `--commit`.
- Node exists in the graph and its status is not in `TERMINAL_STATUSES`
  (`complete`, `deferred`) — `maybe_mark_provisional` would refuse anyway
  (`provisional_status.py:119`), so refuse earlier and louder.
- No existing non-terminal job for `(project_id, node_id)`.
- No existing session with this `result_commit_sha` — makes re-running the
  command safe.

**`--dry-run` prints the three rows and exits.** Adoption asserts that work
happened; it should be readable before it is written.

## 5. Application: the four myapi-part2 nodes

Identified from MyAPI `git log` — each commit names its node explicitly. They
are sequential, so each node's base is its predecessor's commit:

| node | commit | base |
|---|---|---|
| `node-05-inventory-handoffs` | `131a143` | `4267673` |
| `node-06-git-evidence` | `0fbcb09` | `131a143` |
| `node-07-graphify-evidence` | `d890c59` | `0fbcb09` |
| `node-03-validate-anchor` | `ae5ce82` | `d890c59` |

All four are `ready` in `project.yaml` — consistent with work that completed
with the runtime never watching.

Adopt in commit order (03 last, matching its position in history). Then one
heartbeat tick evaluates all four; `node-08-build-source-layers` and its
siblings unblock on the following tick if the verdicts qualify for provisional.

Operator note: the graph statuses and any acceptance remain Sab's call —
adoption routes the nodes to `awaiting_review`, it does not accept them.

## 6. Relationship to the Air sweep

The sweep evaluator is this command plus candidate discovery: find nodes whose
status predates a commit that references them, propose the adopt rows, and let
the operator confirm. Building the writer first means the sweep has something
to call rather than reimplementing row-writing inside a cron job.

## 7. What is deliberately not in scope

- No receipt reuse. `verify_job_return` always evaluates fresh, so a node
  studied with `gddp eval` beforehand is evaluated twice. Acceptable —
  `gddp eval` receipts write to the node-only path and overwrite in place,
  while adopted runs write to the immutable `job_id`+`attempt` path
  (`receipt_sink.py:43`), so the two never collide.
- No auto-discovery of candidates (that is the sweep).
- No graph-truth writes. `complete` stays human-only.
