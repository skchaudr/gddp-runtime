# GDDP internals map for a Factory mission-mode adapter

Verified against the read-only checkouts at `/Users/sab-mini/repos/gddp-runtime`
and `/Users/sab-mini/repos/gddp-config` on 2026-08-07. “INFERRED” marks the few
places where the code does not yet implement the proposed behavior.

## A. Graph layer

### Layout and real records

I walked `/Users/sab-mini/repos/gddp-config` recursively with `.git` excluded.
The durable graph corpus is:

| project | project.yaml | node YAML count |
|---|---:|---:|
| `_template` | yes | 1 |
| `aa-cli` | yes | 12 |
| `aa-cli-verify` | yes | 11 |
| `album-production` | yes | 10 |
| `gddp-runtime` | yes | 22 |
| `myapi` | yes | 6 |
| `needle-gemma` | no | 0 |
| `pi-harness-hygiene` | yes | 2 |
| `pi-hub-projection` | yes | 4 |
| `sab-orchestrate` | yes | 1 |
| `sell-valuables` | yes | 10 |
| `skc-portfolio-migration` | yes | 10 |
| `test-project` | yes | 3 |
| `vault-doctor` | yes | 7 |
| `vm-harness-audit` | yes | 5 |

The remaining top-level surfaces are `bin/gddp`, `scripts/`, `schemas/v1/`,
`verification/`, `verification-runtime/`, `exports/`, `templates/`, `docs/`,
`droid-wiki/`, and local/generated tool directories. `GraphReader` resolves
config root as explicit argument, then `GDDP_CONFIG_PATH`, then sibling
`../gddp-config`; it reads `graphs/<project>/project.yaml` and
`graphs/<project>/nodes/<node>.yaml` (`graph_reader.py:43-61,81-100,122-149`).

Complete real `graphs/pi-harness-hygiene/project.yaml`:

```yaml
schema_version: '1.0'
schema_type: project_graph
project_id: pi-harness-hygiene
project_name: Pi Harness Hygiene (sab-mini)
description: Two concurrent, disjoint corrective nodes on the sab-mini pi home (the Pi-Coding-Agent repo-as-checkout at ~/.pi), executed by droid through the GDDP loop. First mutation graph; the audit graphs stay behind us — this is real work through the daily-driver machinery, then a full pause for assessment.
repo: /Users/sab-mini/.pi
blueprint:
  vision: Prove the GDDP loop as a daily driver on real, bounded improvement work against the primary host's pi harness. Two nodes with disjoint file scopes dispatch concurrently (the first honest concurrency exercise), land on result refs, and pause for human review before any sync decision.
  architecture_notes: Both nodes depend on nothing and run concurrently. node-01 owns agent/extensions/ hygiene (archive three entrypoint-less dirs); node-02 owns agent/chains/ model-pin correctness against enabledModels. Disjoint subtrees of one repo, so concurrent worktrees cannot conflict. Mutation is recoverable — the repo is git, and node-01 archives rather than deletes.
  major_capabilities:
  - Extension auto-load hygiene (remove noise without losing history)
  - Chain model-pin correctness against the live enabledModels set
  - Concurrent non-overlapping dispatch through one repo
graph_version: '1.0'
created_at: 2026-08-05
last_updated: 2026-08-05
nodes_dir: nodes/
nodes:
  - id: node-01-extension-noise-cleanup
    title: Archive entrypoint-less extension dirs out of auto-load
    status: provisional
    type: task
  - id: node-02-chain-pin-repair
    title: Repair chain model pins that reference unavailable models
    status: provisional
    type: task
execution_policy:
  default_executor: droid
  max_concurrent_jobs: 2
  frontier_auto_advance: true
  retry_budget: 3
  require_human_review_before_overnight: false
  artifact_gate_enforced: true
  allowed_repos:
    - /Users/sab-mini/.pi
```

Complete real `graphs/pi-harness-hygiene/nodes/node-01-extension-noise-cleanup.yaml`:

```yaml
schema_version: "1.0"
schema_type: node

node_id: node-01-extension-noise-cleanup
title: Archive entrypoint-less extension dirs out of auto-load
type: capability

why: The agent/extensions/ auto-load surface carries three directories that resolve no loadable entrypoint (herdr/, subagent/, pi-tool-display/ — identified in the 2026-08-05 extension audit on the VM and confirmed present in this repo). They are noise in every loader scan and every audit. Archive them inside the repo (agent/archive/) so auto-load skips them while history and content stay recoverable. Do not touch anything else in the tree.

depends_on: []

acceptance_criteria:
  - id: dirs-moved
    criterion: herdr, subagent, and pi-tool-display directories no longer exist directly under agent/extensions/
  - id: archive-exists
    criterion: all three directories exist with their contents intact under agent/archive/extensions/
  - id: local-file-preserved
    criterion: agent/extensions/herdr-agent-state.ts (a real local file, not a symlink) is still present and unmodified
  - id: pi-loads
    criterion: report includes the output of `pi list` (or `pi --version`) run after the move, exiting 0
  - id: report-exists
    criterion: reports/node-01-extension-cleanup.md exists, listing what moved where and the verification output

constraints:
  - Only move agent/extensions/herdr, agent/extensions/subagent, and agent/extensions/pi-tool-display to agent/archive/extensions/ (create the archive dir as needed)
  - Do not modify, rename, or delete any other file or directory
  - Do not edit settings.json or any npm/package configuration
  - Commit all work on this node's result ref per the executor contract

allowed_execution_modes:
  - droid

required_artifacts:
  - reports/node-01-extension-cleanup.md

status: provisional
priority: high

unlocks: []
```

### Status vocabulary and writers

The controlled **graph/node** statuses are exactly `pending`, `ready`,
`provisional`, `complete`, and `deferred`
(`gddp-config/scripts/node_cli.py:32`,
`gddp-config/scripts/validate.py:38-41`). All five occur in current config.
Recursive YAML text also contains `needs_review` and `received`, but those are
not legal node graph statuses; they belong to other records/examples.

Production Python/YAML additionally uses these non-graph lifecycle tokens:
`received`, `claimed`, `classified`, `mapped`, `ignored`, `scope_blocked`,
`ready`, `running`, `awaiting_result`, `awaiting_review`, `accepted`, `failed`,
`cancelled`, `dispatching`, `dispatched`, `needs_operator`, `collected`, and
`evaluated`. These are event/job/queue/session states, not graph truth
(`init_db.py:54-205`, `state_recorder.py:18-124,323-470`).

Verified graph-status writers:

1. **Human/operator path:** `gddp node browse` invokes
   `node_cli.cmd_set_status`; it requires a reason, appends the graph-status
   history first, surgically and atomically rewrites both node YAML and the
   `project.yaml` summary, validates, and rolls both files back on failure
   (`gddp-config/scripts/gddp.py:924-964`;
   `gddp-config/scripts/node_cli.py:1669-1846`). `complete` is offered only
   through this interactive human surface, not as a shell `set-status`
   subcommand.
2. **`provisional_gate`:** after evaluation finalization, a combined `pass`
   with both integrity booleans true and no required human review rewrites
   both files to `provisional`; it skips `human_gate: true` and never writes
   `complete` (`provisional_gate.py:38-56,88-172`).
3. **`frontier`:** for opted-in projects, rewrites both files from `pending`
   to `ready` when every dependency is `complete|provisional`, excluding
   human-gated nodes, then injects a normal dispatch event
   (`frontier.py:52-120`).
4. **`graph_updater`:** legacy decision-loop proposal code creates a branch
   and evidence PR which changes only the `project.yaml` summary to
   `complete`; a human merge would publish it (`graph_updater.py:21-129,
   159-188`). It does **not** update the node YAML and therefore would create
   the drift that current dispatch rejects. It also uses `push --force`
   (`graph_updater.py:87-91`). This is a real, load-bearing inconsistency, but
   I found no call from the heartbeat attempt path; the caller is the separate
   decision-loop `accept_node` power (`decision_loop/powers/accept_node.py:19-88`).
5. Node/project creation and import tools author initial statuses, but are not
   attempt-lifecycle transitions. A human can also edit YAML directly; the
   heartbeat review drain treats graph files as authoritative
   (`state_recorder.py:130-170`).

`GraphReader.invalidate` is indeed defined twice (`graph_reader.py:64-78` and
`:102-109`). The second definition shadows the first and removes the
`project_id=None` “clear all caches” behavior. This is a **latent API bug**, not
a currently exercised live failure: the only production callers found pass a
concrete project id (`frontier.py:119`, `runner.py:246`).

### Execution-mode enforcement

`classifier.classify` uses the first node mode by default, and rejects an
operator-selected executor not present in that node’s modes
(`classifier.py:48-83,86-89`). Positional `gddp <graph|node> [executor]` also
hard-rejects status drift, non-ready targets, and disallowed executors
(`gddp-config/scripts/gddp.py:149-228`). The special mode `agent` accepts any
member of `_CONCRETE_AGENT_EXECUTORS`, currently `jules`, `jules_api`,
`jules_cli`, `local_subprocess`—not `droid`
(`gddp-config/scripts/gddp.py:76-104`).

The config validator’s full allowlist is:
`agent`, `droid`, `jules`, `jules_api`, `jules_cli`, `local_subprocess`,
`vertex`, `pi_worker`, `vm_worker`, `human`
(`gddp-config/scripts/validate.py:41-52`). Parallel copies exist in
`import_node.py:43-54`, `batch_fill.py:48-59`, and `new_node.py:48-59`.
Runtime dispatchability is a second, narrower set: `ADAPTERS` contains
`jules_api`, `jules_cli`, `local_subprocess`, `droid`, and mediated
`MEDIATED_ADAPTERS` contains `jules` (`dispatcher.py:27-43`).

**Exact minimum for a new runnable mode such as `factory_mission`:**

* add `"factory_mission"` to all four config allowlists
  (`validate.py`, `import_node.py`, `batch_fill.py`, `new_node.py`);
* document it in `schemas/v1/node.yaml` (that file is an example schema, not
  the enforcing validator);
* add `"factory_mission": FactoryMissionAdapter` to
  `heartbeat/dispatcher.py:27-39`;
* add it to `_LOCAL_TRANSPORT_EXECUTORS` only if its adapter constructor must
  receive the local checkout path (`dispatcher.py:35-39`);
* add it to `_CONCRETE_AGENT_EXECUTORS` only if generic `agent` nodes may select
  it (`gddp-config/scripts/gddp.py:77-79`).

No change to `NodeData`, classifier membership logic, job schema, or
`NodePacket` is required.

`gddp-config` is a git repository on `main`, clean and tracking
`origin/main`: `## main...origin/main`.

## B. Attempt lifecycle, exhaustive ordered trace

1. **Graph becomes scheduler-visible.** A human writes `ready`, or
   `advance_frontier` changes an eligible `pending` node to `ready` in both
   graph files and inserts an `events` row with source `frontier_auto`, status
   `received`, URL `frontier-dispatch://node: <id>`
   (`frontier.py:52-120,177-213`). This is the only graph write before dispatch.
2. **Heartbeat loads graph.** `run_heartbeat` constructs `GraphReader`, resolves
   repo checkout, loads `project.yaml`, capacity policy, and
   `get_ready_nodes`; the latter filters only summary `status == "ready"` and
   loads detail YAML, without dependency checks
   (`runner.py:136-177`; `graph_reader.py:151-170`).
3. **Reconciliation runs first.** `reconcile_sessions` recovers stale
   `dispatching` reservations, polls all active sessions for this repo, and
   queues any evaluation work before planning new dispatch
   (`runner.py:183-193`; `reconciler.py:146-225`). This ordering makes existing
   attempt returns visible before capacity is reserved.
4. **Frontier and review drain.** `advance_frontier` may add newly ready nodes.
   `reconcile_reviewed_jobs` maps jobs in `awaiting_review` to `accepted` or
   `deferred` only after the human-owned graph reaches `complete` or `deferred`;
   it updates `jobs` and `queue_records`, never graph YAML
   (`runner.py:195-219`; `state_recorder.py:130-170`).
5. **Pending event selection and claim.** `_plan_dispatches` selects this
   project’s (or unowned matching-repo) events in `received`, plus stale
   `claimed`, ordered by receipt. It atomically changes the chosen event to
   `claimed`, stamps `claimed_at` and `project_id`, and commits
   (`runner.py:324-391`).
6. **Classification.** `classifier.classify` requires `issue.opened` and an
   explicit `node: <id>` tag naming a currently ready node. It chooses the
   first allowed mode or validates `routing.selected_executor`. No match writes
   event `ignored`; a match later writes `classified`, JSON classification, and
   `scope_status='in_scope'` (`classifier.py:31-89`;
   `state_recorder.py:18-38`).
7. **Preflight and base.** `executor_preflight_error` applies
   `GDDP_EXECUTOR_OVERRIDE`, verifies the adapter exists, and constructs it to
   validate configuration (`runner.py:422-435`; `dispatcher.py:45-63`).
   `_get_head_sha` runs `git rev-parse HEAD`; `_chained_base` replaces HEAD
   with the latest recorded result SHA when exactly one dependency is
   provisional, or defers if multiple provisional bases need merging
   (`runner.py:437-474,665-738`).
8. **Capacity lock and scope gate.** Under `BEGIN IMMEDIATE`, the runner counts
   jobs whose job/queue state is `ready|running`, enforces
   `max_concurrent_jobs`, then `check_scope` rejects an existing
   `ready|running|awaiting_review` job or any dependency not
   `complete|provisional` (`runner.py:476-516`;
   `scope_checker.py:22-75`). A scope failure updates the event to
   `scope_blocked`.
9. **Job reservation.** `build_job` creates
   `<runtime>/jobs/<job_id>/` and a job dict at attempt 0, max attempts 3,
   status/queue `ready` (`job_factory.py:26-68`). `insert_job` writes `jobs`;
   `insert_queue_record` writes queue `ready`; `insert_executor_session` writes
   one `executor_sessions` row in `dispatching` with
   `execution_attempt_id=<job_id>:attempt:0`, attempt index and expected base.
   All are committed before worker dispatch (`runner.py:518-532`;
   `state_recorder.py:55-80,173-218`).
10. **Packet construction.** `_execute_dispatches` calls `dispatcher.dispatch`
    concurrently. It decodes persisted JSON fields and creates the immutable
    12-field `NodePacket`; attempt identity is rebuilt as
    `f"{job_id}:attempt:{attempt_index}"` (`runner.py:537-571`;
    `dispatcher.py:66-91,116-155`).
11. **Adapter dispatch.** Registry lookup selects the adapter. For local/droid,
    `LocalSubprocessAdapter.dispatch` creates a unique spool directory and
    writes `packet.json`, `command.json`, and `supervisor.pid`, then starts a
    detached supervisor after a publication handshake
    (`dispatcher.py:27-39,93-97`;
    `local_subprocess_adapter.py:50-114`).
12. **Dispatch outcome persistence.** `_record_outcomes` atomically finalizes
    only a still-`dispatching` session to `dispatched` (or `mediated`), storing
    executor/session id and expected base; then maps the event and changes both
    `jobs` and `queue_records` to `running`. Failure finalizes
    `dispatch_failed` and changes job/queue to `failed`
    (`runner.py:574-662`; `state_recorder.py:82-112,323-355`).
13. **Executor terminal evidence.** On a later tick `_reconcile_one` instantiates
    the recorded adapter and calls idempotent `status`. Transient poll errors
    preserve state. `running` updates the session; `completed` enters
    `_handle_completed`; failed/missing routes through retry policy; auth
    failure parks `needs_operator` (`reconciler.py:311-426,588-740`).
14. **Collection.** `_handle_completed` requires recorded expected base, creates
    a temporary destination, and calls `adapter.collect`
    (`reconciler.py:428-464`). For local/droid, collect reads the terminal
    handoff from spool `stdout`, copies it to the temp destination, and returns
    `result_commit_sha` plus `result_ref`
    (`local_subprocess_adapter.py:120-174`).
15. **Result/ref and ancestry verification.** Commit-ref handoff must include a
    ref. `_resolve_ref` runs
    `git rev-parse --verify refs/heads/<result_ref>^{commit}` and requires exact
    SHA equality; `_is_ancestor` runs
    `git merge-base --is-ancestor <expected-base> <result-sha>`
    (`reconciler.py:465-484,934-962`). Any mismatch raises into the common
    failure handler: session and job/queue become `failed`; no evaluator runs
    (`reconciler.py:559-569`).
16. **Durable collected state.** A valid result updates `executor_sessions` to
    `collected`, stores `result_commit_sha` and `patch_path/result_ref`, commits,
    best-effort creates `gddp/result-<job>-<session>` with `git update-ref`, and
    adds evaluation to the batch (`reconciler.py:485-503,966-993`;
    `state_recorder.py:407-432`). A crash after this point resumes directly
    from `collected`, without recollection (`reconciler.py:342-368`).
17. **Patch-only alternative.** Remote adapters provide patch/base instead.
    Runtime creates a detached worktree at reported base (or expected base),
    `git apply`, `git add -A`, commits
    `result(job=<job>, session=<session>)`, records collected state/ref, queues
    evaluation, and removes the worktree
    (`reconciler.py:505-557,996-1116`).
18. **Evaluator bridge.** `EvaluationBatch.start` runs
    `_run_evaluation` in bounded threads. It calls `verify_job_return` with
    project/node, result SHA as `merge_commit_sha`, expected base, job id and
    attempt (`reconciler.py:63-113,816-831`).
19. **Pinned evaluation worktree.** Bridge validates node/project YAML and repo
    resolution, requires a merge/result SHA, fetches origin best-effort, and
    creates a detached `gddp-eval-wt-*` at that exact commit. Failure to
    materialize is `subject_mismatch`, not mutable-HEAD evaluation
    (`bridge.py:48-147,149-182`).
20. **Two-lane evaluator.** CLI loads the YAML, invokes `orchestrator.verify`;
    deterministic assembly checks criteria, constraints, artifacts, dependency
    statuses and optional `base..HEAD` subject diff. Semantic criteria runs only
    where deterministic evidence is indeterminate and otherwise unblocked.
    Integrity always runs when wired. The pure combiner takes the worse result
    (`verification/cli.py:322-346`; `orchestrator.py:16-110`;
    `integrity_combiner.py:20-61`).
21. **Verdict receipt write.** The evaluator CLI writes the complete Pydantic
    receipt under
    `<receipt-dir>/<project>/<node>/<job>-attempt<N>.json`; an occupied path
    creates `-rerun<N>` rather than overwriting. It then emits a JSON summary
    containing `receipt_path`, verdict/provenance/lane results
    (`verification/cli.py:347-434`; `receipt_sink.py:7-61`). Bridge retries one
    transient verifier failure and parses the last JSON object
    (`bridge.py:48-76,216-319,330-340`).
22. **Review routing.** Coordinator `_finalize_evaluation` writes/upserts
    `results` with ID `res_<session_db_id>`, full verification summary in
    `acceptance_check`, and status `awaiting_review`; changes session to
    `evaluated`; changes `jobs.status`, `jobs.queue_state`, and
    `queue_records.queue` to `awaiting_review`; commits
    (`reconciler.py:833-902`; `results_store.py:69-151`). Even evaluator error
    routes to human review.
23. **Optional provisional flow.** After DB routing,
    `maybe_mark_provisional` may rewrite graph status to `provisional` and
    write a gate token, but never completes the node
    (`reconciler.py:904-912`; `provisional_gate.py:88-172`). Human review later
    changes graph truth; a future heartbeat drains the runtime review row as
    described in step 4.

Retries preserve the same job but increment `jobs.attempt`, create a new
executor-session row and therefore a new execution-attempt id; plumbing retries
keep the work attempt index and increment `jobs.plumbing_attempt`
(`state_recorder.py:223-320`). This distinction already exists and is reusable.

## C. Existing droid one-shot path

### Exact command and packet transport

The code default is the following exact tuple
(`local_subprocess_adapter.py:312-331`):

```text
"/usr/bin/python3",
"/Users/sab-mini/repos/gddp-runtime/scripts/local_agent_executor.py",
"--",
"droid",
"exec",
"--auto",
"high",
"--append-system-prompt",
"Treat piped JSON as the authoritative GDDP NodePacket. Work only in the current worktree. Implement its goal within its constraints, create its required artifacts, run relevant checks, then stop. Never modify graph truth or runtime databases."
```

The armed host overrides it through `GDDP_DROID_SUBPROCESS_ARGV`. The exact
current `gddp.env` argv is:

```text
["/usr/bin/python3","/Users/sab-mini/repos/gddp-runtime/scripts/local_agent_executor.py","--","/Users/sab-mini/.local/bin/droid","exec","--auto","high","-m","custom:Grok-4.5-sub-(Hermes)-0","--append-system-prompt","Treat piped JSON as the authoritative GDDP NodePacket. Work only in the current worktree. Implement its goal within its constraints, create its required artifacts, run relevant checks, then stop. Never modify graph truth or runtime databases."]
```

The packet is serialized exactly to spool `packet.json`, not embedded in the
system prompt. Supervisor opens that file as subprocess stdin
(`local_subprocess_adapter.py:66-72,425-451`). The wrapper reads all stdin,
parses only enough to require `expected_base_commit_sha`, creates the worktree,
then pipes the **unchanged JSON text** to `droid exec` stdin
(`local_agent_executor.py:54-64,275-286,289-329`). The contract preamble rides
`--append-system-prompt`; no packet file path is passed to Droid.

### Worktree, commit and refs

`local_agent_executor.create_worktree` executes:

```text
git worktree add --detach <tempdir> <packet.expected_base_commit_sha>
```

in the target repo (`local_agent_executor.py:67-83`). The target repo is the
wrapper’s cwd supplied by the local adapter, not the runtime repository
(`local_agent_executor.py:296-302`; `dispatcher.py:35-39,93-97`).

After Droid exits, the **GDDP wrapper**, not Droid, guarantees persistence:

```text
git add -A
git -c user.name=gddp-local-agent -c user.email=gddp-local-agent@localhost \
    commit -m "result(job=<job_id>, attempt=<execution_attempt_id>)"
```

It appends `--allow-empty` when the index is clean, resolves HEAD, and verifies
expected base ancestry (`local_agent_executor.py:162-215`). The stable ref is:

```text
gddp/attempt-<execution_attempt_id with characters outside A-Za-z0-9._/- changed to ->
```

For today’s id it is normally
`gddp/attempt-<job_id>-attempt-<index>`
(`local_agent_executor.py:107-115`). If the ref exists, the wrapper permits an
update only when the old ref is equal to or an ancestor of the new result.
An unrelated existing target refuses to overwrite prior evidence. Creation and
advance use `git update-ref refs/heads/<ref> <result> [<empty-old>]`
(`local_agent_executor.py:217-248`). Success emits one
`gddp.local_result.v1` JSON object on wrapper stdout, then removes the
worktree; persistence failure emits the same schema with `worktree_path` and
keeps the worktree (`local_agent_executor.py:250-272,303-322`).

### Durable terminal state

The spool directory name includes safe job id, node id, attempt index and a
UUID (`local_subprocess_adapter.py:50-56`). Files are:

* `packet.json`, `command.json`, `supervisor.pid` at dispatch;
* `pid`, `stdout`, `stderr` after executor spawn;
* atomically written `exit.json` with integer `returncode` and `cancelled`
  after wait;
* optional `cancel.requested`.

Supervisor and executor each start a new process session; cancellation writes
the marker and signals the process group (`local_subprocess_adapter.py:75-110,
176-194,425-486`). Status is derived only from durable spool plus PID liveness:
valid exit 0 → `completed`; nonzero → `failed` with stderr/handoff recovery
detail; live executor PID → `running`; live supervisor PID → `dispatched`;
neither PID nor exit → failed “exited without durable exit state”
(`local_subprocess_adapter.py:209-271`). Agent stdout/stderr are redirected to
the wrapper’s stderr so they land in spool `stderr`; wrapper stdout contains
only the machine handoff and lands in spool `stdout`
(`local_agent_executor.py:275-286`).

## D. Reconciliation, ancestry, idempotency

Ancestry and identity checks are exact:

1. collect returns asserted `result_commit_sha` and `result_ref`;
2. `git rev-parse --verify refs/heads/<result_ref>^{commit}` must equal the
   asserted SHA;
3. `git merge-base --is-ancestor <expected_base_commit_sha>
   <result_commit_sha>` must exit 0
   (`reconciler.py:465-484,934-962`);
4. local wrapper independently performed the same ancestry check before
   creating its attempt ref (`local_agent_executor.py:199-215`).

Mismatch behavior is not quarantine today: the common exception handler sets
the executor session `failed`, sets job and queue `failed`, retains error text,
and does not evaluate (`reconciler.py:559-569`). Remote patch mode notably does
not compare reported patch base to expected base; it materializes and evaluates
the returned work at the reported base because suppressing returned evidence
was judged worse (`reconciler.py:505-518`).

Existing replay/duplicate controls are partial:

* event claiming is compare-and-update and scope rejects another active job;
* late dispatch finalization succeeds only from `dispatching`;
* `collected` resumes evaluation from the stored SHA without recollecting;
* a local attempt ref refuses unrelated reuse;
* receipt files preserve repeated evaluator runs as `-rerunN`;
* result row ID `res_<session_db_id>` is upserted, so repeated finalization
  overwrites that result row.

There is no `completion_id`, no completion digest, no uniqueness constraint on
`execution_attempt_id`, and no conflicting-completion quarantine. Receipt
rerun suffixing preserves duplicates but does not identify or quarantine them.

`awaiting_review` is unconditional after evaluator completion **or evaluator
error**: write the result, set session `evaluated`, set all job/queue views to
`awaiting_review`, then optionally mark the graph provisional
(`reconciler.py:833-912`). Human graph status later drains it
(`state_recorder.py:130-170`).

### Minimal field-only completion discipline

No new table or service is needed. The smallest durable additions are to the
existing per-attempt `executor_sessions` row (`init_db.py:188-205`):

* nullable `completion_id TEXT`;
* nullable `completion_digest_sha256 TEXT` (digest the normalized completion
  envelope, including attempt/base/result and evidence tuple);
* nullable `completion_quarantine_reason TEXT`.

Add a partial unique index on non-null `completion_id` and compare under the
same SQLite write transaction. Exact same id+digest returns the already stored
result (no-op). Same attempt with a different id/digest, or same id with a
different digest, sets existing `state` to a new terminal
`completion_quarantined`, records the reason, retains both incoming identities
in the error/quarantine text or referenced evidence JSON, and routes the job to
`awaiting_review`. This is small reconciliation logic, not a subsystem.

To carry those fields through the neutral adapter seam, add nullable
`completion_id` and `completion_digest_sha256` to `PatchResult`
(`executor_protocol.py:136-153`) or return them in a normalized collect
envelope. `NodePacket` remains unchanged. For receipts, add optional
`execution_attempt_id`, `completion_id`, and `evidence_manifest_sha256` to
`VerdictReceipt`; these are provenance links only.

## E. Evaluator inputs and external commits

### Required inputs

For the live heartbeat evaluator to run:

* `project_id` and `node_id`;
* readable config node YAML and project YAML;
* resolvable local project repo checkout;
* a non-null result/merge commit SHA that `git worktree add --detach` can
  materialize;
* the repository tree at that commit, containing any required artifacts;
* Pi binary, verifier/integrity extensions, provider configuration and model
  credential for live semantic/integrity lanes.

Expected base is not required by bridge, but when present it enables the
neutral `base..HEAD` name-status evidence and is already ancestry-verified
before evaluation. `pr_ref` is optional. Job id/attempt are optional to the
schema but required for immutable per-attempt receipt naming. Node
`acceptance_criteria`, `constraints`, `depends_on`, `required_artifacts`, and
project status index come from YAML, not executor output
(`bridge.py:78-147,216-319`; `deterministic/__init__.py:22-112`).

Executor transcripts are **not required**. The evaluator’s own Pi tool traces
are generated during evaluation. Required artifacts must be files at repo root,
`.gddp/`, or `docs/`, or exact H2 sections of `executor-receipt.md`;
`merged_pr` is always deterministically absent
(`deterministic/artifacts.py:27-65`). External validator/UAT/transcript files
are useful only if placed/referenced where the evaluator can read them and the
node criteria make them relevant.

### Full VerdictReceipt schema

Top level (`schemas.py:161-225`):

```text
project_id: str
node_id: str
verdict: pass | fail | blocked | needs-human-review |
         needs-more-evidence | out-of-scope-change-detected
criteria_verdict: same enum | null
integrity: IntegrityOutput | null
confidence: float 0..1
criteria_confidence: float 0..1
completeness: float 0..1
graph_readiness: float 0..1
completeness_status: complete | partial | not-run
deterministic: DeterministicResult
semantic: SemanticOutput | null
decision_reasoning: str
required_next_action: str
generated_at: str
evaluated_tree_sha: str | null
evaluated_commit_sha: str | null
merge_commit_sha: str | null
expected_base_commit_sha: str | null
pr_ref: str | null
job_id: str | null
canonical_context: dict[str,str] | null
context_coverage: ContextCoverage | null
```

Nested structures (`schemas.py:28-159`):

```text
DeterministicResult:
  criteria: [{
    id, criterion, status, confidence, method, evidence[], reasoning,
    mismatch_kind, mismatch_detail, needs_evidence, human_question
  }]
  constraints: [{
    constraint, status, confidence, method, evidence[], reasoning
  }]
  artifacts_present: dict[str,bool]
  deps_status: dict[str,str]
  criteria_mismatches: [{criterion_id, kind, detail}]
  missing_evidence: [{criterion_id, what_is_missing, what_exists}]
  human_review_questions: [{criterion_id, question}]
  subject_diff: dict | null

SemanticOutput:
  judgments: [{
    criterion_id,
    judgment: judged_pass | judged_fail | indeterminate,
    confidence: 0..1, evidence[], reasoning
  }]
  overall_reasoning: str
  risks: str | null
  followup_candidates: str | null
  budget_exhausted: bool
  budget_trace: dict | null
  lane_status: completed | no-verdict | crashed | timed-out | null
  harness_error: str | null

IntegrityOutput:
  verdict: pass | block | drift | insufficient | contradicted | unknown
  intent_preserved: bool
  graph_integrity_preserved: bool
  required_human_review: bool
  confidence: 0..1
  findings: [{severity: low|medium|high, summary, affected_node_ids[]}]
  reasoning: str
  tool_trace: list[dict] | null
  graph_observations:
    [{severity: low|medium|high, summary, affected_node_ids[]}] | null
  lane_status: completed | no-verdict | crashed | timed-out | null
  harness_error: str | null

ContextCoverage:
  criteria: LaneCoverage | "not_run"
  integrity: LaneCoverage
  overall: none | low | medium | high
LaneCoverage:
  rating: none | low | medium | high
  offered, content_accessed, not_observed: int
  accessed_paths[], not_observed_paths[]
```

### Lanes and combination

Lane 1 first builds deterministic criteria/constraint/artifact/dependency
evidence. Semantic criteria investigation runs only for indeterminate criteria
when dependencies and hard constraints are not already blocking and no
criterion has hard-failed (`orchestrator.py:35-55,161-170`). Its output enters
the fixed 12-row decision matrix (`decision_engine.py:273-444`).

Lane 2 always runs when wired and asks fresh-eyes intent/graph-integrity
questions, not acceptance re-adjudication (`orchestrator.py:60-78`;
`semantic/integrity_runner.py:1-79`). The deterministic combiner applies the
worse verdict: integrity pass cannot upgrade criteria; `insufficient` floors at
needs-more-evidence; unknown/drift/contradicted/block or false preservation
flags floor at needs-human-review
(`integrity_combiner.py:20-61`). Note that criteria `fail`/`blocked` remains
worse than the integrity human-review floor.

### Can it evaluate an externally produced mission commit?

**Yes, verified by interface behavior.** The evaluator does not require that
GDDP created or supervised the producer worktree. It discards producer
worktree identity and creates its own detached evaluation worktree at the
provided commit (`bridge.py:149-182`). The external commit must be present in
the resolved repo’s object database or fetchable from `origin`; a commit only
inside an unshared/unpushed worktree/object store is fatal
`subject_mismatch`. The mission adapter can fill this by ensuring the commit is
reachable via its permitted mission work branch/ref before collection.

What an external mission completion must supply/fill:

* execution-attempt join: existing GDDP `execution_attempt_id`;
* result commit SHA and reachable ref;
* recorded expected base SHA for ancestry and diff;
* project/node ids already in the GDDP session/job;
* required artifact files in the result tree;
* optional Factory validator/UAT/handoff/transcript references. Their absence
  is not evaluator-plumbing-fatal, but may make criteria indeterminate or
  required artifacts absent;
* completion id/digest and evidence tuple are currently missing from GDDP and
  need the field-only additions above.

The producer’s original worktree path, PID, mission transcript, and supervision
history are not required by the current evaluator. Per the fixed direction,
mission git work must still occur under `droid exec -w`; GDDP only needs the
reachable commit/ref and honest per-node evidence.

## F. Tests and setup

Required command was run exactly from the runtime checkout:

```text
cd /Users/sab-mini/repos/gddp-runtime
time python3 -m pytest -q
```

Result: **517 passed, 0 failed, 0 skipped in 9.91s**; wall clock
`real 0m10.210s`, user `0m4.240s`, sys `0m3.327s`. There were no failures to
quote. Before and after status was unchanged:

```text
## main...origin/main
?? docs/operator-practice/droid-mission-mode-prompt.md
```

Thus pytest left no newly visible artifacts. The inherited untracked file was
present before the run and was not touched.

`.venv/bin` exists and includes Python 3.14 and pytest. The explicit venv
command also passed: **517 passed in 9.77s**, wall 10.023s:

```text
cd /Users/sab-mini/repos/gddp-runtime
.venv/bin/python -m pytest -q
```

Activation is **not required on this host**: system `python3` and venv are both
3.14.6 and both have Flask 3.1.3, PyYAML 6.0.3, Pydantic 2.13.4 and pytest
9.1.1. `anthropic` is absent from both but the full suite still passes; `rich`
is present only in the venv.

The true dependency declaration is `requirements.txt`: `flask>=3.0`,
`pyyaml>=6.0`, `pydantic>=2.0`, `anthropic>=0.40`. Root `setup.sh` is stale/
incomplete: it checks Python and runs only `pip install flask`; it does not
create a venv or install the full requirements (`setup.sh:1-24`).

Verified fresh-host procedure is the one in
`deploy/mini-heartbeat/FRESH-HOST-STANDUP.md`: clone runtime and config side by
side (the proven Linux host used `~/gddp-runtime` and `~/gddp-config`), create
`gddp-config/.venv`, install `flask pyyaml rich` for `bin/gddp`, install/verify
the intended executor CLI, configure
`deploy/mini-heartbeat/env/gddp.env` including executor argv and evaluator
credential, install the user systemd service/timer, use
`KillMode=process`, smoke, then inject the first node. For a development host,
also install runtime `requirements.txt` and pytest; the fresh-host record is an
operations record, not a complete developer dependency installer.

## G. Operator surface and heartbeat kit

### `gddp`

`which gddp` is `/Users/sab-mini/bin/gddp`, a symlink-compatible shell launcher
whose source is `gddp-config/bin/gddp`. It resolves config root from
`GDDP_CONFIG_PATH`, its own checkout, then known locations; chooses
`gddp-config/.venv/bin/python` if executable, otherwise `python3`; and execs
`scripts/gddp.py` (`gddp-config/bin/gddp:1-54`). There is no `setup.py`,
`pyproject.toml`, or `console_scripts` entry.

Full surface verified through `--help` and parser code
(`gddp-config/scripts/gddp.py:2410-2594`):

```text
gddp <graph-or-node> [executor]              # exact positional dispatch
gddp node browse [--project PROJECT]
gddp node new
gddp node rapid --project P [--repo R] [--project-name N] [--llm-draft] [--dry-run]
gddp node batch --project P
gddp node import (--file F|--stdin) --project P [--auto-approve] [--dry-run]
gddp node validate [--project P] [--json] [--strict] [--quiet] [--root ROOT]
gddp node list [--project P] [--status S] [--active]
gddp node show --project P NODE [--trace] [--view all|summary|evaluation|contract]
gddp node status [--project P]
gddp jobs list [--state S]
gddp jobs show REF [--full]
gddp jobs results [--all]
gddp jobs set REF STATE --reason REASON [--yes]
gddp verify node --project P --node N [--repo-path PATH] [--live] [--base SHA]
gddp review --project P --node N [--repo-path PATH] [--full]
gddp obsidian export --project P [--vault PATH] [--dry-run]
gddp project new --project-id P [--project-name N] [--repo R]
                 [--from-outline F|--from-graphify F] [--dry-run] [--force]
gddp project validate [--project P]
```

There is intentionally no `gddp node set-status`; graph changes are made in
the interactive `node browse` human-review menu. `jobs set` changes runtime
state only.

### Mini-heartbeat

`common.sh` resolves kit/runtime/config/repo roots, sources
`env/gddp.env`, chooses runtime venv Python or `/usr/bin/python3`, defines
launchd paths, XML/sed-escapes values, and renders environment placeholders
into plist templates (`bin/common.sh:1-102`). The current local env fixes
runtime/config/repo roots, secret resolver commands, Pi one-shot argv, Droid
argv, and spool root. Resolver commands are passed, not resolved secret values.

`install-dormant.sh` creates runtime state directories, optionally copies the
example env, renders both plists, registers them, then disables/stops them
(`bin/install-dormant.sh:1-53`). `arm.sh` is macOS-only and refuses unless
`MINI_HEARTBEAT_ARM=1`; it re-renders, bootouts old jobs, changes installed
intake to RunAtLoad+KeepAlive and heartbeat to RunAtLoad, bootstraps/enables
both, starts intake, and kicks one heartbeat (`bin/arm.sh:1-69`). `disarm.sh`
bootouts/disables and re-renders dormant templates.

`smoke.sh` checks runtime/config, resolves DeepSeek and webhook credentials by
length only, checks gh/pi, probes intake health and invalid-HMAC rejection,
checks launchd registration and rendered-env drift, then runs one heartbeat
tick after sourcing the kit environment (`bin/smoke.sh:1-183`). `baseline.sh`
is the deeper production check: git sync, local credential commands, launchd,
local/funnel health, signed HMAC, DB integrity/writability, heartbeat, gh, and
Pi extensions, with OK/degraded/broken exit codes. `watch-dispatch.sh` builds a
six-pane Zellij view over intake log, heartbeat log, events, jobs, issues and
PRs; `shell-aliases.sh` exposes `gddp-watch*`.

Launchd:

* `com.gddp.intake`: runtime venv Python runs `scripts/intake_server.py`,
  dormant template `RunAtLoad=false`, `KeepAlive=false`, logs under
  `~/Library/Logs`.
* `com.gddp.heartbeat`: every 300 seconds runs
  `<python> -m scripts.runtime.heartbeat.runner --all-active --config-path
  <config>`, with executor/evaluator env and local spool configured.

Linux systemd mirrors the 300-second cadence. The oneshot service sources
`gddp.env` and requires `KillMode=process`; default cgroup killing was observed
to reap detached executors when a tick ended
(`systemd/gddp-heartbeat.service:1-14`,
`FRESH-HOST-STANDUP.md:24-51`).

`GDDP_LOCAL_SUBPROCESS_ARGV` is a JSON argv array consumed by
`LocalSubprocessAdapter._configured_argv`; it is not a shell command
(`local_subprocess_adapter.py:274-299`). `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR`
points to durable per-session attempt folders used by dispatch, polling,
collection, cancellation and crash recovery.

Concretely, calling the runner directly from an ordinary shell skips the env
file frozen into launchd/common.sh. For `local_subprocess`, missing argv or
spool causes adapter construction/preflight failure
(`local_subprocess_adapter.py:274-299,359-363`). More dangerously, a different
shell env can select stale executor/model credentials or the wrong spool,
making an existing session appear missing and creating failed jobs/retries.
The mini-heartbeat entrypoints source the canonical env before invoking the
runner; this is why AGENTS.md requires them. `smoke.sh` does invoke the module,
but only inside the kit after sourcing `common.sh`.

## H. Repository state (read-only)

Main checkout:

```text
## main...origin/main
?? docs/operator-practice/droid-mission-mode-prompt.md
```

Last 15 commits:

```text
efa449a fix(gates): self-heal missing dependency tokens at frontier dispatch
3ff4a79 fix(gates): atomic tempfile, revocation, self-heal, schema validation, receipt path
3dd05e9 feat(gates): per-node gate-token writer for mission-mode admission
31fbe2c docs: mission-hooks investigation — no per-node admission API; mission-level lease it is
5c22eac docs: mission-hooks investigation briefing (for interactive droid mission)
07144df docs: mission may hold the authored graph; GDDP retains graph authority
84d5b24 Draft: two mode executor architecture
06606e0 journal: node-01 pass; stall root cause (ready-vs-pending authoring) + validator hardening
4426c8b fix(observability): move otelcol to 4319 so the Datadog agent can own 4318
22a0a13 feat(observability): make droid telemetry reach the collector under launchd
f67a5dd docs: run journal for pi-hub-projection — split-brain argv fix + liveness gap
8329c62 handoff(066): pi-harness-hygiene staged; run nodes A LOT
afebfda feat(heartbeat): split plumbing retries from work-attempt budget (3+3)
536a2d8 chore(deploy): archive dead-topology artifacts — setup.sh, gddp-intake.service, BIGPI_RUNBOOK
985165f docs: fresh-host stand-up record — the real one, from the khoj-38 port
```

Worktrees:

| path | branch/upstream | HEAD vs `origin/main` | uncommitted |
|---|---|---|---|
| `.worktrees/capability-spine` | `feat/capability-spine`, behind its upstream by 8 | 0 ahead / 133 behind | none |
| `.worktrees/restore-forward-gates` | `fix/restore-forward-gates`, equal to its upstream | 0 ahead / 64 behind | none |

There are no stashes. `git worktree list` also reports six old detached
temporary exec/eval registrations as prunable because their directories no
longer exist; I did not prune or alter them.

## Attempt lifecycle trace

1. `frontier.advance_frontier` (`frontier.py:52`) reads graph+DB, writes node/project `pending→ready` and a `received` event.
2. `runner.run_heartbeat` (`runner.py:136`) reads project/ready nodes/policy and opens WAL SQLite.
3. `reconciler.reconcile_sessions` (`reconciler.py:146`) polls/collects old attempts before new capacity is planned.
4. `runner._plan_dispatches` (`runner.py:324`) claims `events.received→claimed`.
5. `classifier.classify` (`classifier.py:31`) maps an explicit node tag and allowed executor.
6. `dispatcher.executor_preflight_error` (`dispatcher.py:45`) verifies adapter configuration.
7. `runner._chained_base` (`runner.py:665`) selects HEAD or one provisional dependency result SHA.
8. `scope_checker.check_scope` (`scope_checker.py:31`) rejects duplicate active work or unsatisfied dependencies.
9. `job_factory.build_job` + recorder (`job_factory.py:26`; `state_recorder.py:55`) create jobs dir, job `ready`, queue `ready`, session `dispatching`, attempt id.
10. `dispatcher._build_node_packet` (`dispatcher.py:116`) produces immutable executor-neutral packet.
11. adapter `dispatch` creates executor session/spool; runner records session `dispatched`, job/queue `running` (`runner.py:574`).
12. later `_reconcile_one` (`reconciler.py:311`) polls `dispatched→running→completed`.
13. `_handle_completed` (`reconciler.py:428`) collects handoff and verifies ref equality plus base→result ancestry.
14. recorder writes session `collected`, result SHA/ref; batch queues pinned evaluator (`reconciler.py:485`).
15. bridge creates detached evaluation worktree at exact result commit (`bridge.py:78,149`).
16. orchestrator runs deterministic criteria lane, conditional semantic lane, and always-wired integrity lane (`orchestrator.py:16`).
17. `integrity_combiner.combine` (`integrity_combiner.py:42`) chooses the worse-of verdict.
18. evaluator CLI calls `receipt_sink.write_receipt` (`cli.py:347`; `receipt_sink.py:29`) for immutable per-attempt receipt.
19. `_finalize_evaluation` (`reconciler.py:833`) writes results, session `evaluated`, job/queue `awaiting_review`.
20. `maybe_mark_provisional` (`provisional_gate.py:88`) may write `provisional`; only later human graph action can write `complete`.

## Seams for a mission-mode adapter

| Seam | Existing contract | Minimal change |
|---|---|---|
| Adapter registration | `dispatcher.ADAPTERS` (`dispatcher.py:27-39`) | Add one name/class entry; add to local-cwd set only if needed. |
| Neutral attempt input | `NodePacket` (`executor_protocol.py:43-116`) | Reuse unchanged; mission adapter transports exact `to_json()` record. |
| Lifecycle methods | `ExecutorAdapter.dispatch/status/collect/cancel` (`executor_protocol.py:168-191`) | Implement the four methods and keep GDDP’s per-node records post-hoc. **INFERRED candidate:** `dispatch` launches one headless `droid exec --mission -w`; verify the real CLI/process contract before choosing this mapping. Do not add scheduling or lease machinery. |
| Allowed graph mode | config validators and operator dispatch (`validate.py:41-52`; `gddp.py:100-118`) | Add the new string to four config allowlists, adapter registry, and optionally generic-agent concrete set. |
| Attempt reservation | `executor_sessions.execution_attempt_id` (`init_db.py:188-205`; `state_recorder.py:177-218`) | Reuse as per-node join key; do not create an attempt table. |
| Collection result | `PatchResult.result_commit_sha/result_ref` (`executor_protocol.py:136-153`) | Populate from mission worker commit; add nullable completion id/digest fields. |
| Commit verification | `_resolve_ref` + `_is_ancestor` (`reconciler.py:465-484,934-962`) | No architectural change; ensure mission work branch/ref is reachable locally and feed base/result/ref through this path. |
| Durable attempt metadata | existing `executor_sessions` row | Add nullable completion/evidence fields and partial unique completion-id index. |
| Evaluator | `verify_job_return` (`bridge.py:48-147`) | No change to supervision assumption; it accepts any reachable commit. |
| Receipt provenance | `VerdictReceipt` (`schemas.py:161-225`) | Add optional attempt/completion/evidence-manifest links; no lane changes. |
| Receipt sink | per-job-attempt paths (`receipt_sink.py:7-61`) | Reuse. Optionally place normalized mission evidence path/hash in receipt provenance. |
| Review routing | `_finalize_evaluation` (`reconciler.py:833-912`) | Reuse unchanged, including error/mismatch routing to human review. |
| Per-node artifact slicing | arbitrary JSON in `results.acceptance_check`, plus session `patch_path` | Store one evidence-manifest JSON path and keys `{featureId, workerSessionId, commitId}`; no artifact service. |
| Operator entry | positional `gddp <node|graph> [executor]` (`gddp.py:149-228,384-402`) | New mode becomes selectable after allowlist/registry additions. |

The proposed architecture document mentions persistent missions and leases, but
the operator’s fixed v1 direction supersedes that machinery: per-node fidelity
must come from records and post-hoc evidence slicing. The seams above can host
that adapter without a mission registry, scheduler, lease service, new table,
or second evaluator.

## Records-discipline gap analysis

| Record discipline | What exists today | Missing | Smallest field-only closure | New subsystem? |
|---|---|---|---|---|
| attempt id | `execution_attempt_id=<job>:attempt:<index>` in packet and `executor_sessions`; per-attempt receipt path | No DB uniqueness; plumbing retries may share work attempt id by design | No required field. Optionally unique `(execution_attempt_id, plumbing_attempt identity)` policy; keep packet id as join key | **No** |
| completion id | none | Stable executor-produced completion identity | `executor_sessions.completion_id TEXT NULL`; optional `VerdictReceipt.completion_id` | **No** |
| base/result ancestry | expected and result SHA stored; result ref exact-resolved; `merge-base --is-ancestor` | External adapter must supply reachable ref/SHA; mismatch currently “failed,” not explicit integrity quarantine | No new field for ancestry. Optional `completion_digest_sha256` binds base/result/ref into completion | **No** |
| duplicate quarantine | event claim, active-job guard, collected resume, unrelated attempt-ref refusal, receipt rerun preservation | No exact completion replay no-op; no conflicting completion state/digest | `completion_digest_sha256 TEXT NULL`, `completion_quarantine_reason TEXT NULL`, partial unique index on non-null completion id; use session state `completion_quarantined` and existing job review route | **No** |
| per-node evidence slicing | result commit, session id, attempt id, arbitrary result JSON; Factory identifiers absent | No durable `(featureId, workerSessionId, commitId)` tuple or manifest path/hash | `executor_sessions.evidence_manifest_path TEXT NULL`; manifest JSON keys `featureId`, `workerSessionId`, `commitId`; optional `VerdictReceipt.evidence_manifest_sha256` | **No** |

**Records-discipline verdict: no row requires a new subsystem.** All five needs
fit the existing adapter → executor-session row → reconciler → evaluator →
receipt/review path. If live Factory evidence shows that the tuple cannot be
recovered reliably from mission artifacts, that is the declared
**STOP-AND-REDESIGN** condition; do not build a watcher, lease manager,
mission database, or second scheduler to compensate.

## Unverified / needs live evidence

1. Exact `droid exec --mission` command-line flags, machine-readable terminal
   output, and whether `-w` plus mission mode can be used in the required
   headless invocation. I did not run a live mission; verify with
   `droid exec --help` and one disposable mission worktree.
2. Which Factory mission artifacts stably expose `featureId`,
   `workerSessionId`, and `commitId`, at what terminal event they stop changing,
   and whether retries rewrite them. Verify with one captured completed mission
   and a deliberate replay/retry.
3. Whether every worker commit is pushed/reachable from the main checkout
   without violating the branch policy. Verify by producing one mission work
   branch, then from the main checkout run `git rev-parse <ref>^{commit}` and
   `git merge-base --is-ancestor <base> <result>`.
4. Whether one mission completion can emit two terminal records and what stable
   value can serve as `completion_id`. Verify with crash/restart and duplicate
   delivery probes.
5. Exact artifact immutability guarantees for Factory validator, UAT,
   transcript, handoff and progress files. Verify by hashing at terminal
   completion and again after mission exit/resume.
6. How per-node evidence should be selected when a worker session or commit
   spans more than one feature. The fixed tuple implies a join, but no current
   GDDP or inspected Factory artifact proves cardinality.
7. Whether `graph_updater.open_evidence_pr` is deployed/invoked anywhere
   outside this repository’s heartbeat. Static call search found only the
   decision-loop power; process/scheduler inspection would verify liveness.
8. The current config tree contains local/generated directories omitted from
   the compact tree listing above; they are not read by `GraphReader`. No claim
   is made about their runtime significance outside GDDP.
