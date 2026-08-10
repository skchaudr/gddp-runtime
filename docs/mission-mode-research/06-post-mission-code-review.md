# Factory mission adapter: post-mission code review

## Overall assessment

The adapter landed as a substantial, coherent implementation rather than a thin demo. Its strongest property is that it treats Factory artifacts as evidence instead of graph truth: mission output is joined back to demanded node IDs, checked against receipts and handoffs, verified against Git, and routed to human review on disagreement. The responsibilities are mostly well separated, persistence is durable, failure paths generally fail closed, README coverage is extensive, and the focused suite passes (`123 passed`).

It is close to production quality at the GDDP boundary, but it is not yet production-ready for unattended use with a changing Factory CLI. Two correctness gaps matter. First, `MissionAdapter._packet_node` drops `NodePacket.previous_findings`, so a `factory_mission` retry does not receive the evaluator's fix-list even though other adapters preserve it. Second, incremental collection verifies ancestry and a trailer but not the required “exactly one commit” base→result range. A feature that makes two commits can be evaluated while the mission is running; because that session is then excluded from terminal remainder collection, whole-engagement history verification may never catch it. More broadly, the only end-to-end test uses a fake Droid that serially implements the hoped-for Factory behavior. The mission planner's preservation of feature IDs and ordering, the runtime event vocabulary, and real completion/failure behavior remain assumptions or only partially probed.

## File-by-file review

### 1. `scripts/adapters/mission_adapter.py` — **acceptable**

- **Correctness:** Engagement dispatch validates non-empty input, unique feature IDs, a common expected base, and checkout/base agreement. It records command, model profile, PID identity, logs, mission directory, receipt ledger, push audit, branch, and demanded IDs durably. Status avoids trusting a reused PID and combines process liveness with Factory artifacts. Collection fans out exact feature IDs and fails closed on planned-feature drift. Cancellation targets the captured process group and preserves evidence.
- **Design quality:** The engagement lifecycle is cohesive and its durable `session.json` makes it usable across heartbeat processes. Atomic JSON replacement and the cross-process mission-creation lock are appropriate.
- **Integration:** It implements both the legacy one-node facade and the engagement extension cleanly. It leaves graph truth untouched and returns `PatchResult`s to the existing reconciler.
- **Needs attention:** `_packet_node` reconstructs a `NodeData` but silently discards `packet.previous_findings`, `attempt_index`, job identity, and execution-attempt identity. The first item is a real retry-contract bug: evaluator findings are persisted and decoded by `dispatcher.py`, but never rendered into `mission.md`. This conflicts with the canonical rule that retries inject the failure fix-list without changing node intent. `session_prompt.py` demonstrates the established behavior for other direct adapters.
- **Fragility:** Mission-directory discovery depends on Factory creating exactly one new directory under `~/.factory/missions` soon after spawn. The lock prevents GDDP/GDDP races but cannot disambiguate a mission started outside GDDP. Terminal detection also depends on `mission_completed` or `state.json.state == "completed"`, both Factory-owned formats.

### 2. `scripts/adapters/mission_projection.py` — **acceptable**

- **Correctness:** It emits exactly one feature per supplied node, keeps exact IDs, performs stable topological sorting, rejects duplicates/cycles, includes intent/criteria/constraints/artifacts, and states a clear commit/receipt/push contract. Planned-feature verification correctly parks every add/remove/rename/reorder drift.
- **Design quality:** Rendering, ordering, readiness selection, and post-planning verification are separated and easy to test.
- **Integration:** Structured packet values are thawed correctly at the JSON rendering boundary. Read-only audit readiness avoids inventing a service stack.
- **Needs attention:** Projection preserves topological order in prose but does not encode dependency edges in a Factory-native feature representation. Correct execution therefore assumes Factory honors the supplied order and does not parallelize dependent features against one shared branch. The eight-feature “topological execution” test cannot verify this because its fake Droid explicitly loops through features serially.
- **Known issue:** Previous-attempt findings are absent from the generated mission because the adapter does not pass them into this renderer. A retry projection test currently proves only that frozen `previous_findings` do not cause serialization trouble; it does not assert that findings reach the worker.

### 3. `scripts/adapters/mission_evidence.py` — **needs work**

- **Correctness:** Evidence is joined by exact feature ID rather than file order. Missing/malformed channels are represented explicitly. Receipt/handoff/progress/Git disagreements, receipt context mismatches, conflicting receipts, push timing, and protected-branch contamination route to review. Per-node manifests preserve claims even when quarantined, which is excellent evidence discipline.
- **Design quality:** The module is necessarily dense, but helpers isolate parsing, cross-checking, quarantine, completion identity, push verification, and Git-context checks.
- **Integration:** Manifests carry the completion and provenance fields needed by the reconciler and evaluator. Post-hoc protected-branch detection usefully closes most of the documented push-guard bypass.
- **Correctness gap:** Incremental subset collection deliberately skips `verify_engagement_history`, but no replacement check requires `base..result` to contain exactly one commit. `verify_git_result` only checks that base is an ancestor of result. A worker can create an untrailed intermediate commit plus a correctly trailed result commit, push it, emit matching receipt/handoff/progress, and pass incremental collection. Once that node is evaluated, terminal reconciliation requests only remaining feature IDs, so the full history bijection may never run for the completed node. The evidence layer should verify one commit in each receipt's own `base..result` range even during subset collection.
- **Fragility:** Completion identity depends on Factory's `missionId`, feature ID, and `workerSessionId` semantics remaining stable. Handoff and progress selection assumes current key names and event shapes.

### 4. `scripts/adapters/mission_git_verify.py` — **needs work**

- **Correctness:** It robustly distinguishes commits from blobs/trees, checks ancestry, local branch reachability, cached origin reachability, and exact `GDDP-Node-Id` trailers. Whole-engagement verification enforces one topologically ordered commit per demanded node.
- **Design quality:** Git observations are returned as explicit facts plus a quarantine reason rather than raised as opaque exceptions. Command failures fail closed.
- **Integration:** The manifest shape is straightforward and consumed cleanly by evidence collection.
- **Correctness gap:** `verify_git_result` does not enforce that `base_sha..result_sha` contains exactly one commit, despite that being the per-feature execution contract. Whole-engagement verification covers this only when all demanded features are collected together. A node-scoped range-cardinality check belongs here and would close the incremental-collection hole.
- **Fragility:** Origin reachability uses local remote-tracking refs. The separate push audit provides additional evidence, but a changed Git/Factory fetch behavior could make this conservative check route valid results to review.

### 5. `scripts/adapters/mission_push_guard.py` — **acceptable**

- **Correctness:** The PATH shim permits only the exact non-force push to `origin` and the engagement ref. The inherited `core.hooksPath` layer catches ordinary absolute-path Git use. Audit appends are locked and record command, result SHA, outcome, containing refs, and timestamp.
- **Design quality:** Policy enforcement and audit are centralized at the executable boundary rather than scattered through worker instructions.
- **Integration:** Installation returns a child environment without mutating the caller's mapping and preserves existing command-scoped Git config entries.
- **Known limitation:** Absolute Git plus `-c core.hooksPath=/dev/null` bypasses both prevention layers. This is explicitly tested and documented, and evidence collection checks protected branches post hoc. It still cannot prevent the consequential remote write; it can only quarantine afterward.
- **Fragility:** The pre-push hook reconstructs the parent command through `ps` and `shlex.split`. Changes in process ancestry, command rendering, platform behavior, or Factory's Git invocation could make the hook fail closed. The PATH wrapper remains the more dependable layer.

### 6. `scripts/gddp_node_receipt.py` — **solid**

- **Correctness:** It requires all claims, independently records current HEAD/branch/toplevel, appends one locked JSONL record, and leaves mismatch adjudication to collection. It fails without writing when Git context is unavailable.
- **Design quality:** This is a small, single-purpose worker boundary. Separating claimed `--result` from observed `git_head` is the right evidence model.
- **Integration:** The `GDDP_RECEIPTS_PATH` contract is simple and the adapter injects it. Tests exercise the CLI through a real subprocess and Git repository.
- **Minor operational constraint:** The destination parent must already exist. That is true for adapter-created engagement directories, but standalone invocation gives only a write error.

### 7. `scripts/adapters/executor_protocol.py` — **solid**

- **Correctness:** The engagement extension is additive, one-node adapters default to unsupported behavior, and `PatchResult` carries node join keys, manifest links, completion identity, digest, and quarantine state. `NodePacket` deeply freezes decoded JSON while retaining deterministic serialization.
- **Design quality:** Engagement support is an optional capability without forcing one-node transports to fake batching. The common packet remains executor-neutral.
- **Integration:** Existing direct adapters can inherit defaults, while runtime capability probing remains duck-typed.
- **Caveat:** The protocol correctly transports `previous_findings`; the mission adapter's loss of that field is an implementation defect, not a protocol defect.

### 8. `scripts/runtime/heartbeat/dispatcher.py` — **solid**

- **Correctness:** It enforces one configured executor per engagement, checks adapter capability, validates unique IDs and topological order, decodes persisted packet fields once, and preserves expected-base and previous-findings data.
- **Design quality:** Adapter construction remains centralized and local transports receive `repo_path` as `cwd`.
- **Integration:** `factory_mission` is registered like other direct adapters rather than special-cased throughout dispatch.
- **Caveat:** Actual grouping and chunking live in `runner.py`, not this file. The dispatcher validates a provided group but does not establish dependency semantics inside Factory.

### 9. `scripts/runtime/heartbeat/reconciler.py` — **acceptable**

- **Correctness:** Shared sessions are grouped, collected once, joined by feature ID, and fanned out to existing per-job session rows. Completed nodes can move to evaluation while the mission continues; incomplete live evidence is deferred rather than prematurely quarantined. Terminal failures still preserve completed feature evidence. Duplicate completion discipline preserves the first result and, after the recorded repair, does not launder quarantine disposition.
- **Design quality:** The engagement-specific path is contained and hands valid results back to the existing evaluation batch. Database writes remain coordinator-owned.
- **Integration:** Results still stop at `awaiting_review`; the evaluator never marks a node complete. Per-feature evaluation uses the feature commit's parent as the node-scoped base, while the session retains the common dispatch base.
- **Needs attention:** Incremental evaluation is irrevocably ahead of whole-engagement history checking. Already evaluated sessions are omitted from terminal remainder collection, so the multi-commit gap described above is not merely delayed—it may never be detected. Either per-feature verification must prove exactly one commit before incremental evaluation, or terminal reconciliation needs a durable whole-engagement integrity pass that can quarantine prior results.
- **Fragility:** Engagement status handling understands only the current adapter state/event model; unfamiliar Factory terminal output becomes crash/review, which is safe but operationally noisy.

### 10. `scripts/init_db.py` — **acceptable**

- **Correctness:** New session columns capture execution-attempt identity, completion identity/digest/quarantine, and evidence-manifest path. Idempotent column additions support existing databases; historical rows receive deterministic attempt backfills. The partial unique index prevents one completion identity from being silently accepted by multiple rows.
- **Design quality:** Records-discipline fields live on the existing executor-session table rather than introducing a parallel mission database.
- **Integration:** The schema matches fields used by completion discipline, reconciler, and evaluator provenance.
- **Known risk:** Index creation assumes existing non-null completion IDs are already unique. A legacy/operator-modified database containing duplicates would fail initialization and need manual repair; normal pre-feature databases have null/missing values and are unaffected.

### 11. `scripts/runtime/verification/schemas.py` — **solid**

- **Correctness:** `VerdictReceipt` adds optional `execution_attempt_id`, `evidence_manifest_sha256`, and `mission_receipt_id` without breaking legacy receipts. Existing compatibility filling remains intact.
- **Design quality:** Provenance links are explicit and transport-neutral. They identify the attempt, bind the manifest bytes, and reference the executor completion.
- **Integration:** `EvaluationBatch` computes/populates these values and the end-to-end test validates receipt round-tripping.
- **Caveat:** The schema records links but does not itself validate that the digest resolves to a retained manifest or that the mission receipt ID is unique; those responsibilities correctly remain in persistence/reconciliation.

## Test quality

The tests are meaningful overall, not coverage padding. They use real temporary Git repositories for object typing, ancestry, branches, remotes, pushes, worktrees, trailers, protected-branch contamination, CLI receipts, and the adapter's commit/ref behavior. They exercise malformed/missing evidence, conflicting receipts, feature-ID drift, crash salvage, PID reuse, cancellation isolation, incremental collection, duplicate completion, quarantine preservation, and database fan-out. The focused command completed with **123 passing tests in 51.93 seconds** using `python3 -m pytest`.

The principal weakness is at the Factory boundary. `test_mission_pipeline_e2e.py` launches a fake Droid that creates the exact files and events the adapter expects and explicitly executes features serially. It is a strong GDDP integration test but not evidence that a real Droid mission preserves feature IDs/order, emits `mission_completed`, uses the assumed handoff/progress fields, executes dependency order, or behaves the same on genuine worker failure. The eight-feature test especially risks overstating what is known: it tests the fake's `for` loop, not Factory scheduling. There is also no test proving previous findings appear in a retry mission, and no incremental test with two commits in one feature's base→result range.

README was updated substantially: it names `factory_mission`, documents architecture, configuration, command shape, evidence, push policy, tests, and operational entrypoints. AGENTS.md explicitly lists the observed limitations: hook-file incompatibility in Droid 0.189.0, untested real `mission_completed`, partially observed crash/resume, untested genuine worker failure, and the residual absolute-Git/hooksPath bypass. One README sentence overstates current verification by saying per-node collection independently verifies “changed paths”; the manifest observes dirty worktree paths and Git boundaries, while scope/changed-file judgment is primarily downstream evaluator work.

## Integration fit

This feels native to the codebase. It extends the executor protocol rather than replacing it, uses the established `NodePacket`, stores lifecycle state in `executor_sessions`, returns through the existing reconciler and two-lane evaluator, and stops at human review. Mission state is not allowed to mutate graph truth. The implementation also follows the repository's evidence-first doctrine: malformed or disagreeing artifacts are retained and quarantined, not normalized into success.

The largest “bolted-on” area is not a new subsystem but the amount of Factory-format knowledge embedded in the adapter/evidence layer: mission-directory discovery, `features.json`, `state.json`, progress event names/fields, handoff shape, worker session IDs, CLI flags, and worktree behavior. The code generally treats those as fallible evidence, which limits damage, but dispatch/status/collection still cannot function without them. The projection also substitutes emphatic prose for a verified Factory-native dependency contract. That is precisely where the project's assumption warning should remain active.

## Open risks

- **Retry intent loss:** `previous_findings` reaches `NodePacket` but is dropped before mission projection. Factory-mission retries can repeat the same failure without the required fix-list.
- **Incremental multi-commit acceptance:** A completed feature can pass incremental collection with more than one commit in `base..result`; terminal remainder collection may never recheck it.
- **Unverified real scheduling:** The implementation assumes exact feature IDs/order survive Factory planning and that dependent features are not run concurrently against one engagement branch.
- **Unverified terminal vocabulary:** Real `mission_completed` behavior has not been observed; `state.json` is a fallback but is also Factory-owned.
- **Unverified genuine failures:** Worker-level failure, retry, handoff multiplicity, and cleanup behavior have not been exercised with a real mission.
- **Factory internal formats:** Renamed/moved mission directories, progress fields, handoff files, state values, or CLI flags can turn sessions into crash/review outcomes or prevent dispatch.
- **Mission-directory race:** The creation lock covers only GDDP processes sharing the same lock root, not unrelated Droid missions using the same Factory mission directory.
- **Push prevention is bypassable:** Absolute Git plus a hooksPath override can write to a protected remote before post-hoc quarantine detects it.
- **Remote/network dependence:** Collection invokes live `ls-remote` checks for protected branches. Offline fallback is conservative but can miss a direct push if both live access and local refs are unavailable/stale.
- **Documentation drift:** README's fixed test count (`633`) and claim of changed-path verification can become misleading as the suite and evidence boundary evolve.

## Bottom line

The code is **close, but not production-ready for fully unattended mission mode**. The GDDP-side architecture, records discipline, fail-closed evidence handling, and Git-backed tests are strong enough for controlled canaries with mandatory human review. Before treating it as a dependable overnight executor, preserve `previous_findings` in mission projection, enforce exactly one commit in every per-feature base→result range (including incremental collection), and run real Factory probes for planning fidelity, terminal events, dependency scheduling, crash/resume, and genuine worker failure. Those are bounded fixes and validations; a redesign is not warranted.
