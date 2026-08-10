# 089 — OR — Mission demolition work order

**Status:** drafted for operator review, awaiting sign-off before Stage 0 begins.
**Author:** Claude Code (drafting only). **Executor:** Kimi.
**Operator:** Sab. Audit points are marked **[OR]** and happen *during*, not only after.
**Date:** 2026-08-10.

---

## 0. Why this document exists at all

The factory_mission adapter merged at `63bdabe` with **+19,639 / −55 across 123 files**
against an approved budget of under 1,000 lines. It was not a bad implementation —
the post-mission review (`docs/mission-mode-research/06-post-mission-code-review.md`)
calls it coherent and mostly well separated. That is exactly the problem. It was
good work at roughly 4× the authorized scope, and the scope it took was *governance*:
twelve new places where GDDP stops.

The consequence is measurable. `db/queue.db` holds 26 `results` rows. Every one
of them predates mission mode. Across four `factory_mission` sessions the evaluator
has produced **zero** verdicts. The subsystem built to police evidence has instead
prevented any evidence from being judged.

So this work order inverts the failure. Where the mission was open-ended and
additive, this is bounded and subtractive.

**The single governing rule: this work order may not increase production line
count. Every stage lands net-negative or flat. A stage that needs to add
production lines is a stop-and-ask, not a judgment call.**

---

## 1. Established facts (verified 2026-08-10, do not re-derive)

### 1.1 The real diff shape

| Component | Lines |
|---|---|
| `docs/mission-mode-research/` | +9,976 |
| tests | +5,146 |
| **production code** | **+3,669** |
| **— of which, in 7 new mission-only files** | **~3,055** |
| **— of which, modifying pre-existing GDDP** | **~614** |

The 614: `reconciler.py` +384/−22, `dispatcher.py` +104/−2,
`graph_reader.py` +97/−3, `init_db.py` +29.

### 1.2 Local execution is already clean — verified, no change required

This is the load-bearing fact for the return to known-good, and it holds without
touching a line:

- `ADAPTERS` in `dispatcher.py:34` still registers `jules_api`,
  `local_subprocess`, `droid`, `factory_mission`, `pi_rpc`.
- `supports_engagement()` returns `False` in `EngagementAdapterDefaults`
  (`executor_protocol.py:195`). **`MissionAdapter` is the only override**
  (`mission_adapter.py:98`).
- `_reconcile_engagement_group` — all ~270 lines of quarantine, feature-id
  join, and review routing — is entered only behind that `supports_engagement()`
  check at `reconciler.py:281`. For every other executor it is dead code.
- `submit_completion` has exactly **one** call site in the entire runtime:
  `reconciler.py:659`, inside the engagement path.
- The runtime imports exactly **one** mission symbol: `MissionAdapter` in the
  dispatcher registry. `mission_evidence`, `mission_git_verify`,
  `mission_push_guard`, and `mission_projection` are imported only by
  `mission_adapter.py`.
- Non-engagement executors reconcile through `_handle_completed`
  (`reconciler.py:835`), the pre-mission path.

**Conclusion: pausing droid missions requires no code change.** Stop declaring
`factory_mission` in graph nodes and GDDP is back to its known-good local path.
The demolition below is about paying down the surface, not about unblocking
local runs — those are already unblocked.

### 1.3 Work already done, do not redo

- `e4d4bbc` — feature-id drift gate removed (`verify_planned_feature_ids` +
  `_feature_drift_reason`). Operator verdict: unapproved evaluator-scope
  seizure. This is the template for every strip below: remove both
  implementation sites, keep the reasoning in the commit message.
- `40a6905` — MappingProxyType thaw before mission.md serialization.
- `a44d2af` — `gddp receipt` replaces the bespoke `gddp-node-receipt` call.
- `e362be8` — early process-exit detection with stderr surfaced.

### 1.4 Ledger state at time of writing

`node-07-instructions-audit` is stuck `running` with no terminal status.
`node-05` failed on the receipt CLI (since fixed). `node-01` and `node-03`
`dispatch_failed` on the mappingproxy bug (since fixed). `node-09` was never
enqueued. Zero results rows for any of them. **These five jobs are not this
work order's problem** — do not attempt to reconcile or re-dispatch them as
part of demolition. They are noted so their state is not mistaken for a
regression introduced here.

---

## 2. Scope

### 2.1 In scope

The nine mission-introduced blocking mechanisms in
`docs/blocking-mechanisms-register.md` whose disposition is already written,
plus the transport-side correctness bug they obscure.

### 2.2 Explicitly out of scope — the list the original mission needed

Touching any of these is a **stop-and-ask**, not a judgment call:

- Any adapter other than `factory_mission` (`local_subprocess`, `droid`,
  `pi_rpc`, `jules_*`) — including "while I was in there" cleanups.
- The evaluator, `scripts/runtime/verification/**`, or the semantic lane.
- The single-session reconciliation path (`_handle_completed` and below).
- Graph truth, node status, frontier, gate tokens, `gddp.py`, `node_cli.py`.
- Database schema. The columns added by `init_db.py` are additive, idempotent,
  and harmless when null. **Leave them.** Removing schema is how a demolition
  becomes an outage.
- `docs/mission-mode-research/` (9,976 lines). It is inert text and costs
  nothing at runtime. Do not touch it, do not count it, do not "tidy" it.
- The register itself. Kimi records outcomes against existing rows; new rows
  and changed dispositions are the operator's.
- Renaming anything. The `reconciler` → collection-loop proposal
  (`.handoffs/082-OR-...` on `feat/khoj-idle-shutdown`) is a separate,
  unapproved discussion. Not here.

### 2.3 The keep line

**Transport core — keep.** Project graph nodes into a mission, launch
`droid exec --mission`, poll status, map the returned branch's commits back to
node IDs, hand `PatchResult`s to the reconciler.

**Governance — strip.** Anything that decides whether a retrievable result
*deserves* to reach the evaluator. That decision belongs to the evaluator and
to Sab, and it already exists upstream of this subsystem.

The test for any given function is one question: *if this returned "no", would
a retrievable commit fail to be judged?* If yes, it is governance. Strip it.

---

## 3. Register dispositions — the spec

No new judgment is required. These verdicts are already written in
`docs/blocking-mechanisms-register.md`. Kimi executes them; Kimi does not
re-litigate them.

| BM | Mechanism | Written disposition | Source |
|---|---|---|---|
| BM-019 | Engagement packets have different expected bases → whole engagement fails | **SOFTEN** | `mission_adapter.py::dispatch_engagement` |
| BM-020 | Checkout HEAD not exactly the expected base → engagement fails | **REMOVE** | `mission_adapter.py::dispatch_engagement` |
| BM-030 | Result unreachable from local engagement branch | **REVIEW/PARK** | `mission_git_verify.py::verify_git_result` |
| BM-031 | Result unreachable from expected origin branch | **WARN/REPAIR** | `mission_git_verify.py::verify_git_result` |
| BM-032 | Commit lacks exactly one `GDDP-Node-Id` trailer | **WARN** | `mission_git_verify.py::verify_git_result` |
| BM-033 | History is not exactly one commit per node in topological order | **SOFTEN** | `mission_git_verify.py::verify_engagement_history` |
| BM-034 | Collected feature IDs ≠ reserved node IDs → all jobs to review | **SOFTEN** | `reconciler.py::_reconcile_engagement_group` |
| BM-035 | Receipt / handoff / progress / push audit missing or inconsistent | **WARN/REVIEW** | `mission_evidence.py`, `mission_adapter.py` |
| BM-036 | Protected-branch reachability detected post-execution | **INCIDENT + EVALUATE** | `mission_evidence.py::_protected_branch_push_reasons` |
| BM-037 | Same completion ID, different digest | **HARD STOP — KEEP** (HC-06) | `completion_discipline.py::submit_completion` |
| BM-038 | Same completion ID and digest replays | **KEEP** | `completion_discipline.py::submit_completion` |

Two operating notes on this table:

**BM-036 is not a strip.** "INCIDENT + EVALUATE" means the detection survives and
gets louder, while the *suppression* dies. A protected-branch push must raise an
incident and still let the evaluator speak. Post-hoc quarantine cannot un-push
anything; it can only hide the result.

**BM-037/038 are the genuine keeps**, but `completion_discipline.py` spends 245
lines on them. Kimi measures what a minimal HC-06 digest-conflict guard actually
costs and reports the number in the Stage 0 map. If it is 40 lines, that is a
200-line finding for the operator — not a licence to rewrite it unasked.

---

## 4. The transport bug that must be fixed, not stripped

From the post-mission review, §1 and "Open risks":

> `MissionAdapter._packet_node` reconstructs a `NodeData` but silently discards
> `packet.previous_findings` … evaluator findings are persisted and decoded by
> `dispatcher.py`, but never rendered into `mission.md`.

This is **transport, not governance**. A `factory_mission` retry currently
receives no fix-list, so it can repeat the exact failure the evaluator just
caught. That breaks the retry contract every other adapter honours —
`session_prompt.py` shows the established behaviour.

It is also the one defect that directly attacks what Sab is trying to protect:
the evaluate → find → retry → improve loop. Fix it. Expect it to cost single-digit
to low-double-digit lines. It is the one place this work order is permitted to
add production code, and the Stage 3 gate below accounts for it.

The review's *second* open risk — incremental multi-commit acceptance — needs no
fix. It is a hole in `verify_git_result`'s governance, and Stage 2 removes the
governance. Record it as moot; do not build a range-cardinality check.

---

## 5. Stages

Suite green after every stage. Each stage is one commit. No stage begins before
the previous one is signed off.

### Stage 0 — the map **[OR: hard gate, nothing moves until Sab signs]**

Kimi produces a one-page keep/strip map: every function in `mission_adapter.py`,
`mission_projection.py`, `mission_evidence.py`, `mission_git_verify.py`,
`mission_push_guard.py`, and `completion_discipline.py`, plus the engagement
block of `reconciler.py`, marked **KEEP (transport)** or **STRIP (governance)**.

Each row carries:
- line count
- the BM it implements, if any
- which tests die with it, by name
- one sentence of justification, referencing the §2.3 test

The map ends with a projected net line delta. Sab reviews one page instead of
9,000 lines. **No code moves in Stage 0.**

### Stage 1 — the free removals

**AMENDED 2026-08-10, see §9. This stage originally included
`mission_push_guard.py`. It does not.**

BM-020 (exact checkout HEAD, written **REMOVE**) and BM-019 (differing expected
bases, written **SOFTEN**), both in `mission_adapter.py::dispatch_engagement`.

Expected delta: ≈ −25 production, plus tests.

### Stage 2 — git verification demoted to evidence **[OR: audit checkpoint]**

BM-030, BM-031, BM-032, BM-033. `mission_git_verify.py` stops returning quarantine
reasons and starts returning observations. Ancestry, branch reachability, origin
reachability, and trailer presence all survive **as recorded facts**. What dies is
their power to stop evaluation.

What remains of `verify_git_result`: resolve the ref, confirm it is a commit,
report what was observed. HC-07 still applies — if the object cannot be resolved
or is not a commit, that is a genuine hard stop, because GDDP then does not know
what it is evaluating.

Expected delta: −200 to −280 production.

### Stage 3 — evidence and the reconciler fan-out **[OR: audit checkpoint]**

BM-034, BM-035, BM-036, plus the §4 `previous_findings` fix.

`mission_evidence.py` is the largest single file at 889 lines and the densest
governance. The per-node manifests are **keep** — the review is right that
preserving claims even when disagreeing is good evidence discipline. The
cross-check *verdicts* are strip. BM-034's fan-out in
`_reconcile_engagement_group` stops routing exact matches to review alongside
the mismatches.

This is the stage most likely to surface something the map missed. It gets the
closest audit.

### Stage 4 — measure, record, stop

- Re-run the register against the code; mark each BM row with its resolving commit.
- Report final production line delta against §1.1.
- Report `completion_discipline.py`'s minimal-guard cost (§3).
- **Stop.** Do not proceed to re-dispatch, do not re-enable `factory_mission`
  anywhere, do not touch the five stranded audit jobs.

---

## 6. Acceptance criteria

1. Full suite green at every stage boundary — not just the focused mission suite.
2. Net production line count is **negative** across Stages 1–3 combined.
3. No file outside §2.1's named set is modified, tests included.
4. Every removal commit names its BM ID and quotes the register's disposition,
   following `e4d4bbc`.
5. `previous_findings` reaches rendered `mission.md`, with a test that asserts
   the finding text is present — not merely that serialization survives.
6. A local-executor smoke run still dispatches, collects, and evaluates. This is
   the return-to-sanity proof and it must be demonstrated, not assumed.
7. Every commit carries `Co-authored-by:` for the tool that wrote it.

---

## 7. What would make this work order fail the same way the mission did

Named in advance so it is recognisable while it is happening:

- **Replacing rather than removing.** "I stripped the push guard and added a
  lighter one" is the original failure wearing a smaller coat. Strip means strip.
- **Fixing adjacent bugs found in passing.** Record them in the map; leave them.
- **Improving tests while deleting them.** Tests for stripped code get deleted.
  Tests for kept code stay as they are.
- **Treating Stage 0's map as a plan to improve rather than a plan to execute.**
- **Silence between stages.** Each stage boundary is an audit point. A stage
  that lands without the operator seeing it did not happen correctly, even if
  the code is right.

---

## 8. Open for the operator

1. ~~Sign-off on the §2.3 keep line~~ — **SIGNED 2026-08-10.**
2. ~~BM-037/038 scope~~ — **CLOSED: out of scope.** Kimi's Stage 0 measurement:
   a minimal HC-06 digest-conflict guard costs ~45–55 lines against the current
   245. That ~190-line finding is recorded, not acted on.
3. ~~Where the demolition lands~~ — **CLOSED: branch off `main`**, created at
   Stage 1, one commit per stage, merged after Stage 4. Stage 0's map is a review
   document and sits on `main` (`3772243`), not on the branch.
4. ~~`mission_push_guard.py`~~ — **RULED 2026-08-10: ARCHIVE.** Not kept in
   production, not deleted. *"Until a real use case is identified, this CANNOT
   live in production… if this becomes a pain point down the road, we bring it
   out of archive."* Operator doctrine accompanying the ruling: **prevent
   dangerous pushes where practical, detect bypasses independently, never let
   post-hoc detection silence evaluation.** The archived layer failed the first
   clause — a PATH shim plus a pre-push hook that rebuilds its parent command
   through `ps` is not prevention "where practical," and it shipped with its own
   bypass documented in `AGENTS.md`. Archiving removes it from the production
   surface, so Stage 1 returns to ≈ −375 and combined Stages 1–3 to ≈ −790.
   Archive ≠ strip: the live integration points still come out
   (`mission_adapter.py:29/166/188/254`), and `mission_evidence.py:118` must
   tolerate a missing `push-audit.jsonl` once the producer is gone.

---

## 9. Amendment — 2026-08-10, after Stage 0 verification

**§5 Stage 1 was wrong and this section corrects it.**

The original text called `mission_push_guard.py` "the cleanest case in the
register." **It is not in the register.** It has no BM row and no written
disposition — all 46 rows checked. The work order asserted register backing
that does not exist, and Kimi executed it faithfully in `090` because §3 says
the register is the spec.

The register in fact argues the other way. HC-09: *"An operation is about to
mutate a protected/shared branch without explicit authority → **Prevent that
push/mutation.**"* And BM-036's own disposition text: *"HC-09 justified
prevention before mutation; post-hoc suppression cannot undo the push."*

The register's position is that **prevention is correct** and *post-hoc
suppression* is the defect. `mission_push_guard.py` is the prevention layer.
Stripping it runs against HC-09, not with it.

The case *for* stripping is still real and belongs in the operator's decision:
the review documents a working bypass (absolute git + `-c
core.hooksPath=/dev/null`); the pre-push hook reconstructs its parent command
through `ps` and `shlex.split`, which the review calls fragile; and the review
judges the PATH wrapper "the more dependable layer" of the two. A defensible
third option is to strip the hook layer and keep the PATH wrapper.

But that is a judgment about how much prevention is worth, not the execution
of a verdict already written. It is §2.2 out-of-scope until the operator rules.

**Consequences of the amendment:**

| | Original | Amended |
|---|---|---|
| Stage 1 | ≈ −375 | ≈ −25 |
| Combined Stages 1–3 | ≈ −790 | ≈ −440 |

The governing no-net-increase rule still holds comfortably.

**Two Stage 0 findings that survive verification unchanged:**

- Every line count in `090` matches the files exactly (851 / 215 / 900 / 340 /
  352 / 245 / 204). Measured, not estimated.
- `_protected_branch_push_reasons` does **not** consume `push_audit` — it
  queries git directly via `ls-remote`, `_is_ancestor`, `_remote_branch_tip`.
  BM-036 detection therefore survives a push-guard strip regardless of the
  ruling. Kimi's Stage 1 reasoning on that point was sound.

**Residual to handle whenever `push_guard` is ruled on:** `mission_evidence.py:118`
reads `push_audit_path`, produced at `mission_adapter.py:166/188/254` through the
guard install. Strip the guard and the producer goes with it. `090` already marks
`_push_verification` STRIP, which is consistent, but the manifest read at `:118`
must tolerate a missing file rather than assume one.

**`090` is not amended.** It is an accurate record of what the spec said when it
was written. The error was in `089`.
