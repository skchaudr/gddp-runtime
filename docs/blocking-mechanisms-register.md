# GDDP Blocking Mechanisms Register

Long-running inventory of places where GDDP stops, parks, defers, ignores, or
suppresses work. Add an entry whenever a new mechanism is found. Do not use
"safety" as a justification without naming the concrete harmful consequence.

Last audited: 2026-08-09.

## Operating premise

A planned graph or mission names a target commit/ref. That target defines the
starting snapshot. Execution should occur in an isolated checkout at that
snapshot. Returned work should get a durable ref and reach evaluation whenever
it is retrievable.

Git relationships answer separate questions:

1. **Can the requested starting snapshot be constructed?**
2. **What did the executor actually return?**
3. **Can that result be integrated automatically?**

A negative answer to question 3 must not erase the answer to question 2.
Ancestry, branch, receipt, and commit-shape discrepancies are evidence about
integration or provenance. They are not, by themselves, reasons to suppress an
evaluator verdict.

## Required disposition language

- **HARD STOP** — continuing would cause a named harmful consequence below.
- **PARK** — this node/attempt needs operator input; unrelated work continues.
- **DEFER** — retryable condition; retain reason and next retry condition.
- **REVIEW** — preserve and evaluate the result, but do not auto-integrate it.
- **WARN** — record evidence; execution and evaluation continue.
- **BUG** — accidental blockage with no defensible policy purpose.

No condition may become a project-wide or graph-wide stop merely because its
implementation site is project-wide.

## Concrete harmful consequences that can justify a hard stop

| ID | Condition | Concrete harmful consequence if execution continues | Narrow response |
|---|---|---|---|
| HC-01 | Target commit/ref cannot resolve to a commit | The executor would run from an arbitrary checkout while GDDP falsely attributes the result to the planned snapshot. | Stop only this attempt; request/fetch the target. |
| HC-02 | Target repository identity is ambiguous or wrong | Work can modify and report evidence from the wrong repository. | Stop only this attempt; resolve repository identity. |
| HC-03 | Node/project target is ambiguous | Work can satisfy a different node's intent and attach evidence to the wrong graph record. | Refuse guessed routing; require an exact target. |
| HC-04 | A job for the same node is already active and no explicit supersession exists | Concurrent attempts can race pushes/results, spend twice, and attach the losing result as current evidence. | Block that node only; offer cancel or explicit parallel/superseding attempt. |
| HC-05 | Required dependency output is absent from the execution snapshot | The dependent can implement against an interface/state that does not contain its prerequisite and produce a misleading result. | Compose an integration base, choose the dependency ref, or request graph amendment; do not block unrelated nodes. |
| HC-06 | The same completion ID arrives with different content digests | Two incompatible outputs claim one identity; automatic selection can bind the wrong code and evidence to the attempt. | Quarantine the conflicting completions; continue unrelated work. |
| HC-07 | Result ref resolves to a different object than the claimed result SHA, or the object is not a commit | GDDP cannot know which returned code is being evaluated or retained. | Preserve the envelope, stop auto-integration, and request identity repair. |
| HC-08 | Dispatch reservation cannot be made atomically because runtime state is unreadable | Two schedulers can reserve duplicate work or overwrite/race job state. | Stop new reservations only; reconciliation/read-only inspection should remain available. |
| HC-09 | An operation is about to mutate a protected/shared branch without explicit authority | It can alter the shared baseline, bypass review, and affect every later attempt. | Prevent that push/mutation. If already done, preserve/evaluate evidence and raise an incident; blocking evaluation cannot undo it. |
| HC-10 | Required packet fields are missing or structurally ambiguous | The executor cannot know the intended node, goal, constraints, or target snapshot and may perform unrelated work. | Reject only that packet with an exact repair message. |

Resource cost, inconvenience, unusual Git history, missing ceremony, and an
implementation path that has not yet been written are not concrete harmful
consequences.

## Mechanism register

### Admission and routing

| ID | Current mechanism | Current effect / blast radius | Judgment | Required alternative | Source |
|---|---|---|---|---|---|
| BM-001 | Graph-wide dispatch finds one project/node status disagreement | Aborts dispatch of every otherwise valid ready node in the graph. | **SOFTEN**: drift is real evidence; graph-wide refusal is not justified. | Exclude and explain only the drifting node; dispatch the valid remainder. | `gddp-config/scripts/gddp.py::build_dispatch_plan` |
| BM-002 | Explicit executor conflicts with one node in graph dispatch | Aborts the entire graph request. | **SOFTEN**. | Exclude incompatible nodes, show them in preview, dispatch compatible nodes. | `gddp-config/scripts/gddp.py::build_dispatch_plan` |
| BM-003 | Node name exists in multiple graphs | Refuses guessed dispatch. | **HARD STOP**, HC-03. | Require graph qualification; no guessed target. | `gddp-config/scripts/gddp.py::build_dispatch_plan` |
| BM-004 | Node is not graph-ready | Refuses dispatch. | **PARK**, not generic safety. Graph truth says this proposal is not at the dispatch frontier. | Show exact status and offer the human-owned graph action; never mutate status automatically. | `gddp-config/scripts/gddp.py::build_dispatch_plan` |
| BM-005 | Runtime DB/events table cannot be read | Refuses all new CLI dispatch events. | **HARD STOP for reservation**, HC-08. | Keep reads/diagnostics available and name the DB repair; do not pretend the frontier is empty. | `gddp-config/scripts/gddp.py::_connect_events_db`, `_classify_dispatch_items` |
| BM-006 | Any historical job has an active value in either duplicated state column | Node is omitted from dispatch, even when the newest job is settled. | **CONTAIN**: duplicate prevention is valid, but duplicated/drifting state can create a false permanent lock. | Derive one authoritative attempt state; expose explicit stale-lock repair/supersession. | `gddp-config/scripts/frontier.py::dispatch_blockers` |
| BM-007 | `agent` means executor-neutral in config but literal executor in runtime | Explicit concrete routing is ignored, or runtime selects nonexistent adapter `agent`; event loops or is ignored. | **BUG**. | One shared resolver maps neutral mode to a registered project/default executor before event insertion. | `gddp-config/scripts/gddp.py::_executor_allowed`; `classifier.py::classify`, `_pick_executor`; `dispatcher.py::ADAPTERS` |
| BM-008 | Explicit runtime routing is not literally in `allowed_execution_modes` | Classifier returns `None`; event becomes terminal `ignored (no node mapping)`. | **BUG** for neutral modes; poor diagnosis otherwise. | Use shared compatibility rules and store an exact routing error instead of “no node mapping.” | `classifier.py::classify`; `runner.py::_plan_dispatches` |
| BM-009 | Intake event is untagged or not `issue.opened` | Event is ignored and spends no executor budget. | **KEEP** for unsolicited public webhook intake; it is not a valid gate for an already planned mission. | Manual/frontier dispatch should carry typed exact node identity and bypass heuristic classification. | `classifier.py::classify` |
| BM-010 | Ready summary has no node YAML | Runtime silently skips the node. | **BUG**. | Loud per-node configuration error; continue other nodes/projects. | `graph_reader.py::get_ready_nodes` |
| BM-011 | One node declaring an unregistered execution mode aborted graph loading | The project/all-active scan could fail before other valid work ran. | **RESOLVED** in `56ebcd3`. | Current `main` loads the node with a loud warning; only its dispatch fails at adapter lookup. | `graph_reader.py::validate_node_execution_modes` |
| BM-012 | One project has malformed execution-policy sizing | Can abort the whole `--all-active` scan before other projects run. | **CONTAIN**. | Park that project with its validation error and tick remaining projects. | `graph_reader.py::parse_execution_policy`; `runner.py::_configured_job_capacity`, `run_active_projects` |
| BM-013 | Ready node has unsatisfied graph dependencies | CLI excludes it; runtime marks its event terminal `scope_blocked`. | **CHANGE**. HC-05 justifies not executing from an incomplete snapshot, not terminal disposal. | `DEFER` with dependency/ref details, compose the base when possible, or ask for graph amendment. | `scope_checker.py::check_scope`; `runner.py::_plan_dispatches` |
| BM-014 | Config validator rejected `ready` with unsatisfied dependencies | Any graph validation/status workflow could fail globally over a scheduling preference. | **RESOLVED** in config commit `953406a`. | The validator was removed; frontier reports the condition and dispatch handles dependency admission. | `gddp-config/scripts/validate.py` history |
| BM-015 | `human_gate: true` prevents automatic frontier advance | Node waits for the operator. | **KEEP**: explicit human ownership, not accidental blocking. | Make the waiting reason visible; manual graph action remains human-only. | `frontier.py::advance_frontier` |

### Base selection, checkout, and scheduling

| ID | Current mechanism | Current effect / blast radius | Judgment | Required alternative | Source |
|---|---|---|---|---|---|
| BM-016 | Executor preflight fails | Event returns to `received` every heartbeat with no durable disposition. | **BUG/DEFER LOOP**. | Park once as `config_error` with repair text; do not consume capacity; retry only after configuration changes or operator action. | `runner.py::_plan_dispatches`; `dispatcher.py::executor_preflight_error` |
| BM-017 | One provisional dependency has no recorded result SHA | Event returns to `received` indefinitely. | **PARK**, HC-05. | Record `waiting_for_dependency_ref`; awaken when a durable ref appears. | `runner.py::_chained_base` |
| BM-018 | More than one dependency is provisional | Dispatch is repeatedly refused because “there is no merge machinery.” | **BUG/MISSING CAPABILITY**, not a safety policy. | Build an isolated integration base from the required refs, dispatch separately where valid, or park once for an operator-selected composition. | `runner.py::_chained_base` |
| BM-019 | Engagement packets have different expected bases | Entire engagement fails. | **SOFTEN**. | Split by base, normalize to a proven common descendant, or create an integration worktree. | `mission_adapter.py::dispatch_engagement`; `runner.py::_execute_dispatches` |
| BM-020 | Shared checkout HEAD is not exactly the expected base SHA | Entire engagement fails and suggests moving the shared checkout. | **REMOVE**. Exact equality is unnecessary and shared-checkout mutation increases risk. | Create an isolated worktree at the planned target; allow descendant HEAD only when its relationship is deliberately selected. | `mission_adapter.py::dispatch_engagement` |
| BM-021 | Repository capacity is full | Current event returns to `received`, then `break` stops scanning every later event. | **SOFTEN**. Capacity is scheduling, not safety. | Defer the affected executor/repo lane and continue scanning work that can use another lane or free capacity. | `runner.py::_plan_dispatches` |
| BM-022 | Auth-blocked session becomes `needs_operator`, but job remains running | It retains a node lock and consumes shared capacity indefinitely. | **BUG**. | Preserve the node lock, release scheduler/executor capacity, and continue unrelated work. | `reconciler.py::_handle_failed`; `runner.py::_active_job_count` |
| BM-023 | Reconciliation or schema failure leaves a job active | Capacity and duplicate guards can remain occupied although no executor is progressing. | **BUG**. | Transactionally park the attempt as `reconcile_error`, release capacity, retain node lock/evidence, continue unrelated work. | `reconciler.py`; DB migration path |
| BM-024 | Engagement order places a selected dependency after its dependent | Engagement fails before launch. | **REPAIR LOCALLY**: HC-05 applies, but rejection is avoidable. | Topologically sort selected packets; fail only if the selected graph is cyclic or ambiguous. | `dispatcher.py::_validate_engagement_order` |
| BM-025 | Local checkout cannot be resolved | Reconciliation is skipped; local executor preflight later defers. | **PARK local work only**. | State `checkout_unavailable`, continue remote transports/projects, and name every path tried. | `runner.py::run_heartbeat`; repository resolver |

### Collection, Git evidence, and evaluation

| ID | Current mechanism | Current effect / blast radius | Judgment | Required alternative | Source |
|---|---|---|---|---|---|
| BM-026 | Commit-ref handoff lacks `result_ref` | Single-session path marks job/session failed before evaluation. | **REVIEW/PARK**. If the commit object is retrievable, evaluate it and repair durability separately; if not, HC-07 applies. | Create GDDP-owned durable ref when possible; otherwise preserve envelope and request identity repair. | `reconciler.py::_handle_completed` |
| BM-027 | `result_ref` does not resolve exactly to claimed result SHA | Single-session path fails before evaluation. | **HARD STOP for auto-integration**, HC-07; not necessarily an evaluation stop. | Resolve/preserve every observable object, evaluate an unambiguous commit, quarantine identity conflict. | `reconciler.py::_handle_completed` |
| BM-028 | Result does not descend from expected base | Single-session path fails; engagement path routes to review without semantic evaluation. | **REVIEW**, not evidence suppression. | Evaluate retrievable work against its actual parent/base; block only automatic integration into the planned line. | `reconciler.py::_handle_completed`, `_reconcile_engagement_group` |
| BM-029 | Returned patch reports a different base than dispatch expected | Historical behavior discarded valid work; current patch path evaluates it on its reported base. | **CURRENT BEHAVIOR GOOD**. | Keep: reconstruct in isolated worktree, evaluate, record base difference as integration evidence. | `reconciler.py::_handle_completed`; commit `56db172d` |
| BM-030 | Result is not reachable from local engagement branch | Marks mission result review-required. | **REVIEW/PARK durability**. | Preserve/evaluate an existing commit; create a GDDP-owned ref; do not confuse branch ceremony with code correctness. | `mission_git_verify.py::verify_git_result` |
| BM-031 | Result is not reachable from expected origin branch | Marks mission result review-required and suppresses normal evaluation. | **WARN/REPAIR**. Remote durability matters, but is not semantic correctness. | Evaluate local durable object; retry/prompt push separately. | `mission_git_verify.py::verify_git_result` |
| BM-032 | Commit lacks exactly one matching `GDDP-Node-Id` trailer | Marks result review-required and suppresses normal evaluation. | **WARN**, unless identity is actually ambiguous. | Use reserved feature/session mapping as primary identity; trailer is corroborating evidence. | `mission_git_verify.py::verify_git_result` |
| BM-033 | Engagement history is not exactly one commit per node in demanded topological order | Quarantines results from normal evaluation. | **SOFTEN**. Commit shape is workflow ceremony, not intent correctness. | Evaluate node-scoped diffs/results; warn about attribution ambiguity; review only genuinely inseparable outputs. | `mission_git_verify.py::verify_engagement_history` |
| BM-034 | Collected feature IDs do not exactly equal every reserved node ID | Routes every job in the engagement to review, including exact matches. | **SOFTEN**. | Reconcile exact matches independently; quarantine only missing, duplicate, or unknown mappings. | `reconciler.py::_reconcile_engagement_group` |
| BM-035 | Receipt, handoff, progress, or push audit is missing/inconsistent | Mission result becomes review-required and normally bypasses evaluation. | **WARN/REVIEW**. Provenance weakness is useful evidence, not a reason to silence the evaluator when code is retrievable. | Run evaluator; show provenance lane separately; block only automatic integration if identity is ambiguous. | `mission_evidence.py`; `mission_adapter.py` collection |
| BM-036 | Protected-branch reachability is detected after execution | Result is quarantined from normal evaluation. | **INCIDENT + EVALUATE**. HC-09 justified prevention before mutation; post-hoc suppression cannot undo the push. | Preserve/evaluate result, alert operator, freeze further mutation, and provide exact affected refs. | `mission_evidence.py::_protected_branch_push_reasons` |
| BM-037 | Same completion ID arrives with a different digest | All involved completions/jobs are quarantined for review. | **HARD STOP for auto-selection**, HC-06. | Keep quarantine; show both envelopes and never silently choose. Unrelated work continues. | `completion_discipline.py::submit_completion` |
| BM-038 | Same completion ID/digest replays | First stored result is reused; duplicate is recorded. | **KEEP**. | Preserve any prior quarantine; do not strand a replay in running. | `completion_discipline.py::submit_completion` |
| BM-039 | Evaluator raises or cannot write its display row | Evaluator error still routes job to human review; graph truth does not advance. | **KEEP NON-FATAL**. | Preserve explicit error and all collected evidence; unrelated evaluation continues. | `reconciler.py::_run_evaluation`, `_finalize_evaluation` |
| BM-040 | Missing provisional gate token | Frontier tries to recreate it; failure is logged but non-fatal. | **KEEP NON-BLOCKING**. | Gate tokens remain a repairable projection, never graph authority. | `frontier.py::_ensure_dependency_gates`; `gate_tokens.py` |

### Lifecycle and failure containment

| ID | Current mechanism | Current effect / blast radius | Judgment | Required alternative | Source |
|---|---|---|---|---|---|
| BM-041 | Job is awaiting human review | Duplicate dispatch is blocked indefinitely. | **KEEP node-local**, HC-04, but require an explicit operator escape. | Offer cancel, retry, parallel comparison, or supersede without changing graph truth. | `scope_checker.py::check_scope`; config `frontier.py::dispatch_blockers` |
| BM-042 | Return-router exception | Event is marked terminal `ignored`. | **BUG**. | Dead-letter with exact exception and retry/operator action; never relabel processing failure as irrelevant input. | `runner.py::_plan_dispatches` |
| BM-043 | Dispatch finishes after reservation was cancelled/superseded | Late result/failure is ignored after best-effort remote cancellation. | **SOFTEN**. | Do not attach it as current, but retain it as orphan/superseded evidence with its commit/ref and cancellation outcome. | `runner.py::_record_outcomes`; `dispatcher.py::cancel_remote_session` |
| BM-044 | Claimed event's heartbeat crashes | Event is unavailable for 30 minutes, then claimable again. | **KEEP retry**, but make lease visible. | Store claim owner/lease expiry; allow deliberate early release. | `runner.py::_plan_dispatches` |
| BM-045 | Poll error is classified transient | Session waits for next heartbeat without consuming attempt. | **KEEP DEFER**, bounded by observability. | Count duration/errors and park if the same condition exceeds an operator-visible threshold. | `reconciler.py::_reconcile_one` |
| BM-046 | Executor reports `needs_operator` or repeatedly asks a question | Session parks; job remains active. | **PARK node-local**; capacity retention is covered by BM-022. | Record exact requested decision; release capacity; unrelated work continues. | `reconciler.py::_handle_awaiting_reply`, `_handle_needs_operator` |

## Historical proof that over-blocking loses work

- `56db172d` removed exact expected-base versus returned-patch-base rejection
  after three valid Jules outputs were discarded before evaluation.
- `a5e0eb9` introduced provisional base chaining and explicitly refused multiple
  provisional parents because merge machinery did not exist. This records an
  implementation gap, not a timeless safety rule.
- `f53baae` normalized a provisional dependency base to checkout HEAD when the
  result is already its ancestor. Exact parent equality had prevented valid
  sibling work from sharing an engagement.
- Current doctrine already states: base mismatch is integration evidence and
  must never silence evaluation (`docs/building-blocks-reckoning.md`,
  `docs/GDDP-rebuild.md`).

## Adding an entry

For every new block, record:

1. Stable ID and date observed.
2. Trigger and exact code path.
3. What state changes: event, job, session, result, node, capacity.
4. Blast radius: attempt, node, engagement, executor, repo, project, all-active.
5. Concrete harmful consequence claimed.
6. Whether that consequence is observed, proven by a test, or merely asserted.
7. Narrowest non-blocking alternative.
8. Desired disposition: hard stop, park, defer, review, warn, or bug.
9. Commit that changes or retires the mechanism.

If the consequence cannot be named precisely, default to preserving evidence,
continuing unrelated work, and asking the operator rather than blocking.
