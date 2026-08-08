# GDDP Simplification Proposal

**Status:** DRAFT — proposal only. No code changes authorized by this document.
**Date:** 2026-08-08
**Authors:** Claude (§1, §2, §3, §5) + Pi (§4, §6)
**Rule of engagement:** strictly proposal-first. Nothing here is executed until Sab
accepts it. Per `AGENTS.md`, agents do not author graph nodes; this is a
candidate list for human ruling, not a work plan.

---

## §0 Why this document exists

`AGENTS.md` opens with the failure pattern this repo is trying to escape:

> 1. An agent assumes a behavior exists. 2. It designs around that assumption
> without verifying. 3. The system fails because the assumption was false.
> 4. More machinery is proposed to fix the failure and that invented workaround
> becomes architecture.

Every candidate below is a suspected layer-4 artifact: machinery that exists
because of a past workaround, not because the operating loop needs it. Each is
stated with evidence (paths, reference counts, LOC) so the ruling can be made
against facts rather than vibes.

---

## §1 Inventory & metrics — Claude

Measured on `main` @ `8ef0464`, tracked files only (`git ls-files`).

| Surface | Files | LOC |
|---|---:|---:|
| All tracked Python | 122 | 29,779 |
| — production Python (non-`test_`) | — | 15,534 |
| — test Python (`test_*.py`) | — | 14,245 |
| `scripts/runtime/verification/` | 48 | 10,131 |
| `scripts/runtime/heartbeat/` | 20 | 7,685 |
| `scripts/adapters/` | 8 | 2,469 |
| `scripts/runtime/decision_loop/` | 12 | 1,446 |
| Tracked Markdown | 133 | — |

Two numbers frame the whole conversation:

1. **`verification/` is 34% of the codebase** (10,131 of 29,779 LOC) — larger
   than the heartbeat that drives it. For a subsystem whose stated output is
   "a two-lane worst-of verdict receipt", this is the highest-value place to
   look for collapse.
2. **Test LOC is 48% of the tree** and is concentrated oddly:
   `heartbeat/test_executor_sessions.py` alone is 2,577 lines — 9% of all
   Python in the repo, and larger than any three production modules combined.
   That file is a simplification target in its own right, not just coverage.

---

## §2 Orphan surfaces — Claude

Method: for each module, list every non-test file referencing it, excluding the
module's own file. "Orphan" = zero external non-test references anywhere in
`scripts/` or `deploy/`.

### 2.1 `scripts/runtime/decision_loop/` — 12 files, 1,446 LOC — ORPHAN

The single largest deletion candidate. Nothing in `scripts/` or `deploy/`
imports it. Its only referents are documentation:

- `docs/decision-loop-spec.md:280` describes the intended callers
  (`webhook router`, `cron handler`) — **neither caller exists**. This is the
  layer-4 pattern verbatim: a spec described an integration, the module was
  built against it, the integration never landed, and the module stayed.
- `docs/building-blocks-reckoning.md:238` already independently flags
  `decision_loop/powers/dispatch_next.py` as a "dead parallel dispatcher …
  not the heartbeat import graph."
- `docs/handoff-2026-07-30-recovery.md:208` accounts for its 1,504 lines.

Note the naming collision that likely helped it survive review: there is also a
live `scripts/runtime/verification/decision_engine.py` (referenced from
`orchestrator.py` and `semantic/pi_runner.py`). The dead package and the live
module read as the same thing at a glance. **Proposed: delete the package,
retain `docs/decision-loop-spec.md` under `docs/archive/`.**

### 2.2 `scripts/node_status_history.py` — ORPHAN

No external non-test reference. Note the adjacent breakage in §5.1.

### 2.3 Canary family — ORPHAN

- `scripts/canary_local_executor.py`
- `scripts/canary_local_executor_slow.py`
- `scripts/canary_stabilization_reset.py`

Post-incident scaffolding from `docs/postmortem-canary-scope-2026-07-12.md`.
Zero external non-test references. **Proposed: move to `scripts/_archive/` or
delete — but see §4, Pi should rule on whether canary re-arming is a standing
operational capability Sab expects to reach for.**

### 2.4 `scripts/runtime/replay.py` — effectively orphan

Only referent is `docs/dispatch-checklist.md`. If the checklist step is live
operator practice, this is documented-but-unwired, not dead. Needs a ruling.

---

## §3 Duplication & overlap — Claude

These are *not* proposed deletions. They are places where three things exist and
the shape suggests one or two would do. Each needs Pi's doctrine ruling in §4
before anything is proposed concretely.

### 3.1 The gate layer — *not* duplication; a naming collision (revised)

I initially flagged `runtime/gates.py`, `heartbeat/provisional_gate.py`, and
`heartbeat/frontier.py` as three overlapping gate surfaces. Reading their
public functions, that is wrong and I am withdrawing it — they are three
distinct concerns, 532 LOC total, and none is redundant:

| Module | LOC | Actual concern |
|---|---:|---|
| `gates.py` | 134 | Gate-token file I/O: `write_gate` / `revoke_gate` / `read_gate` / `gate_satisfied` |
| `provisional_gate.py` | 171 | Provisional-status marking: `provisional_eligible`, `maybe_mark_provisional` |
| `frontier.py` | 227 | Dispatch advancement: `advance_frontier`, `_ensure_dependency_gates`, `_inject_dispatch_event` |

The real finding here is smaller and cheaper: **the word "gate" names two
unrelated things** — a dependency admission token (`gates.py`) and a
provisional node status (`provisional_gate.py`). That collision is a live
comprehension hazard in a repo whose stated failure mode is agents assuming
behavior that isn't there. **Proposed: rename, not restructure.** e.g.
`gates.py` → `gate_tokens.py` and `provisional_gate.py` → `provisional_status.py`.

Separately worth Pi's eye but *not* a simplification claim: `3dd05e9`,
`3ff4a79`, and `efa449a` (self-heal for missing dependency tokens at frontier
dispatch) all land on this seam inside two weeks. Three rapid patches may just
be a young subsystem stabilizing. Flagging the churn, not diagnosing it.

### 3.2 Three Jules adapters

`jules_action_adapter`, `jules_api_adapter`, `jules_cli_adapter` — 2,469 LOC
across `scripts/adapters/`, all three reachable from
`heartbeat/dispatcher.py`.

`AGENTS.md` says: *"Prefer a direct executor transport for the short node round
trip. Preserve any mediated pathway as inherited infrastructure rather than the
required command bus"* and *"Treat GitHub, Jules, Codex, and other executors as
replaceable transports and workers."*

A three-way fan-out for a single replaceable transport looks like the opposite
of that doctrine. **Question for Pi:** does `neutral-executor-contract` require
the mediated dispatcher path to survive, or can the Jules fan-out demote to one
adapter + archive, with `local_subprocess_adapter` as the direct transport?

### 3.3 `verification/` internal seams

48 files, 10,131 LOC, comprising: a deterministic lane (`deterministic/`,
incl. a 1,021-line `probes.py`), a semantic lane (`semantic/`, incl. a
TypeScript `pi_harness/` of three `.ts` files), plus `bridge.py`, `cli.py`,
`decision_engine.py`, `integrity_combiner.py`, `retry_budget.py`,
`receipt_sink.py`, `schemas.py`, `orchestrator.py`, and `shape_profiles/`.

I asked Pi to rule on which of these are contract vs. implementation detail.
Pi's first answer was to push `decision_engine`, `integrity_combiner`,
`retry_budget`, and `shape_profiles/` down into `semantic/`. Checking the actual
import graph showed that was backwards on three of the four; Pi revised, and
§4.2 item 6 now reflects the corrected ruling. The evidence that settled it:

| Module | Real importers | Why push-down is wrong |
|---|---|---|
| `retry_budget.py` | `scripts/runtime/return_router.py:194` | Its consumer is **outside `verification/` entirely**. Pushing it into `semantic/` makes an external caller reach into a lane's internals — worse coupling, not better. If it moves, it moves *out* toward `return_router`, not *in*. |
| `decision_engine.py` | `orchestrator.py:7`, `:62`, `:164` | Called as `decision_engine.decide(det, semantic)` — it takes **both** lanes' output. A lane-combining module cannot live inside one lane by definition. |
| `integrity_combiner.py` | `orchestrator.py:7`, `:78` | Called as `integrity_combiner.combine(criteria_verdict, integrity, action)` — same argument: cross-lane by construction. |
| `shape_profiles/` | **none** (zero non-test importers in `scripts/`) | Not an implementation detail — an **orphan**. Belongs in §2 with the other dead surfaces, not in a reorganization list. |

Agreed landing point (§4.2.6): the top-level contract is `orchestrator` +
`schemas` + `cli` + `bridge` + `decision_engine` + `integrity_combiner`;
`retry_budget` is misplaced but the fix points outward, toward `return_router`;
`shape_profiles/` is dead.

**Sizing honesty:** that is a genuine but **modest** cleanup. It does not
recover anything like the 34% headline in §1, and this proposal should not be
read as implying it does.

What remains true and unexamined: `orchestrator.py` (377 LOC) carries a
781-LOC test file, and `deterministic/probes.py` (1,021 LOC) carries a 731-LOC
test file. If there is real bulk to recover in `verification/`, the evidence
points at the **deterministic lane and its tests**, which neither of us
examined, rather than at the top-level module layout that §4.2.6 targets.

### 3.4 Python/TypeScript boundary

`semantic/pi_harness/` is three `.ts` files inside an otherwise pure-Python
repo with no `package.json`, no lint config, and no JS toolchain declared in
`AGENTS.md`'s project snapshot. This is an undeclared second language in the
build. Flagging as an architecture question, not proposing removal.

---

## §4 What must NOT be simplified away — Pi

### 4.1 The Doctrine Floor
Based on `docs/GDDP-becomes-small-and-real.md` and `AGENTS.md`, the following are non-negotiable and cannot be simplified away:
1. **GDDP's Identity:** It is *not* the executor and *not* the agent harness. It is the intent-preservation and graph-integrity layer constraining the loop.
2. **The Evaluator's Job:** It must perform semantic verification against canonical docs (e.g., `README.md`, `PROJECT-BRIEF.md`, DAG neighborhood), **not** just local tests. Tests are evidence; the verdict is intent/integrity preservation.
3. **The Human Authority Invariant:** Only Sab moves a node to complete. The system cannot be self-certifying. 
4. **The Neutral Executor Contract:** Executors (Pi, Claude, Jules) are replaceable transports. The system dispatches bounded packets and receives receipts.

### 4.2 Rulings on Claude's Candidates
1. **`decision_loop/` (§2.1): DELETE.** This is the exact failure pattern `AGENTS.md` warns against: building machinery around unverified assumptions (callers that never existed). It was superseded by the heartbeat dispatch loop. Delete the package, move spec to `docs/archive/`.
2. **`node_status_history.py` & `replay.py` (§2.2, 2.4): DELETE/ARCHIVE.** If they aren't wired into the live `mini-heartbeat` or `scripts/jobs_status.py` pathways, they are dead weight.
3. **Canary family (§2.3): ARCHIVE.** These appear to be incident scaffolding. Unless Sab confirms they are active operational capabilities, move them to `scripts/_archive/`.
4. **The gate layer (§3.1): APPROVE RENAME.** Acknowledging the withdrawal of the collapse proposal. The naming collision between dependency admission tokens (`gates.py`) and provisional status (`provisional_gate.py`) is exactly the kind of semantic trap that causes self-heal churn and agent drift. Rename `gates.py` → `gate_tokens.py` and `provisional_gate.py` → `provisional_status.py`.
5. **Three Jules adapters (§3.2): DEMOTE TO ONE.** Doctrine states: *"Prefer a direct executor transport... Preserve any mediated pathway as inherited infrastructure."* A three-way fan-out for Jules violates the neutral-executor-contract. Keep one adapter for Jules as legacy/infrastructure, archive the rest, and rely on the direct transport (like `local_subprocess`).
6. **`verification/` internal seams (§3.3): CORRECTED PUSH-DOWN.** The initial push-down proposal was backwards on facts. The true state:
   - `decision_engine.py` and `integrity_combiner.py` are lane-combiners called by `orchestrator.py`. They cannot live inside a single lane; they belong at the top level as part of the core contract.
   - `retry_budget.py` is imported by `scripts/runtime/return_router.py` (outside verification entirely). It should be moved OUT of `verification/` and towards its consumer.
   - `shape_profiles/` is a pure orphan (zero non-test importers). It belongs in the delete/archive list, not the push-down list.
   - The honest, pared-down top-level contract for verification is therefore: `orchestrator`, `schemas`, `cli`, `bridge`, `decision_engine`, and `integrity_combiner`.

---

## §5 Hygiene defects — Claude

Concrete, low-controversy, verifiable defects. These are not architecture
questions.

### 5.1 The package definition is gone; the build artifact survived it

- There is **no `pyproject.toml`, no `setup.py`, no `setup.cfg`** anywhere in
  the repo.
- `gddp_runtime.egg-info/` still exists on disk (untracked) and its
  `entry_points.txt` declares `gddp = scripts.node_status:main`.
- **`scripts/node_status.py` does not exist.** The nearest file is
  `scripts/node_status_history.py` (itself an orphan, §2.2).

So the repo carries a stale build artifact pointing at a console script whose
target module is missing, generated from a package definition that no longer
exists. The `gddp` command that actually works is
`~/.local/bin/gddp`, an unrelated bash launcher that resolves via
`GDDP_CONFIG_PATH` → repo root → known layouts.

This matters beyond tidiness: `AGENTS.md` names `gddp` as "the single
operator-facing control plane." Anyone who reads `entry_points.txt` to find it
lands on a dead module. **Proposed: delete `gddp_runtime.egg-info/`, add it to
`.gitignore`, and either restore a real `pyproject.toml` or document in
`AGENTS.md` that `gddp` is a shell launcher and the repo is intentionally
not pip-installable.**

### 5.2 `AGENTS.md` project snapshot contradicts the repo

`AGENTS.md:39` states *"No requirements.txt — scripts use stdlib + Flask."*
A `requirements.txt` exists at repo root. `AGENTS.md:109-110` repeats
"stdlib + Flask / `pip install flask`". Small, but this is the file every agent
session reads first, and it is wrong on line 39.

### 5.3 Root-level Markdown drift

Seven tracked `.md` files at root: `AGENTS.md`, `README.md`, `PROJECT-BRIEF.md`,
`TOPOLOGY.md` (all four legitimately canonical) plus `decision.md`,
`result-summary.md`, and `readiness-report-2026-07-18.md` — the last three are
session artifacts, not canon. Also untracked at root: `patch.diff` (tracked,
3.1KB, a loose diff), `.DS_Store` (10KB). **Proposed: move the three session
artifacts to `docs/archive/`, delete `patch.diff`, gitignore `.DS_Store`.**

### 5.4 Documentation outweighs and outdates the code

133 tracked Markdown files against 122 Python files. Oldest-touched docs still
sitting in the live `docs/` tree (not `docs/archive/`):

| Last touched | File |
|---|---|
| 2026-05-06 | `docs/operator-practice/task-ideas.md` |
| 2026-05-12 | `docs/CHANGELOG.md` |
| 2026-05-26 | `docs/decision-loop-spec.md` |

`decision-loop-spec.md` is the spec for the dead package in §2.1 — three months
stale, describing callers that never existed, and still sitting in the live docs
tree where an agent will read it as current. This is exactly how step 1 of the
`AGENTS.md` failure pattern gets seeded. **Proposed: `docs/` gets a hard
live/archive split, and anything describing an unwired integration moves to
archive with a dated header.**

### 5.5 Test mass concentration

`heartbeat/test_executor_sessions.py` at 2,577 lines is 9% of all Python in the
repo. Not proposing deletion — proposing it be read for whether it is testing
one subsystem or has accreted into a catch-all. Same question for
`verification/test_orchestrator.py` (781 LOC against a 377-LOC module).

---

## §6 Sequencing — Pi

If Sab approves this proposal, the execution should follow this order to preserve a working loop:

1. **Phase 1: Hygiene & Deletes (Immediate, lowest risk)**
   - Delete `decision_loop/`, `gddp_runtime.egg-info/`, `node_status_history.py`, and `patch.diff`.
   - Archive the canary family, `replay.py`, and stale docs/session artifacts.
   - Fix `AGENTS.md` line 39 to acknowledge `requirements.txt`.
2. **Phase 2: Adapters & Gate Renames (Low-Medium risk)**
   - Rename `gates.py` → `gate_tokens.py` and `provisional_gate.py` → `provisional_status.py`.
   - Demote the Jules adapters to a single mediated adapter; rely on direct transports.
3. **Phase 3: Verification Subsystem Realignment (High value)**
   - Delete/archive the orphaned `shape_profiles/`.
   - Move `retry_budget.py` out of `verification/` and towards its external consumer (`return_router.py`).
   - Retain `orchestrator.py`, `schemas.py`, `cli.py`, `bridge.py`, `decision_engine.py`, and `integrity_combiner.py` as the clean top-level API for verification.
4. **Phase 4: Test Pruning**
   - After deleting dead code and collapsing boundaries, aggressively prune `test_executor_sessions.py` (2,577 LOC) and `test_orchestrator.py` to only cover the surviving loop and contracts.

---

## §7 Open questions for Sab

0. **Resolved, but flagging the process.** Two rulings in this document were
   initially made on premises that turned out to be false — the "three
   overlapping gate surfaces" collapse (withdrawn by Claude after reading the
   modules' public functions) and the `verification/` push-down (revised by Pi
   after checking the real import graph). Both were caught by verifying against
   the code rather than the description. That is the §0 failure pattern being
   caught in flight, and it is the reason §3.3 and §4.2.6 now carry explicit
   file:line evidence. Treat any claim in this document *without* such evidence
   as unverified.
1. Is the canary family (§2.3) a standing operational capability you expect to
   reach for, or spent scaffolding?
2. Should the repo be pip-installable again (`pyproject.toml` restored), or is
   the bash launcher the intended permanent shape? (§5.1)
3. `docs/` live/archive split — do you want that as one sweep or incrementally
   as each doc is touched? (§5.4)
