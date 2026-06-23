# GDDP — Implementation Plan

Sequel to [`PROJECT-BRIEF.md`](PROJECT-BRIEF.md). Direction + ground state live
there; this plan sequences the work into phases a lesser model can decompose
into native units — **graph node** in [`gddp-config`](../gddp-config) + **Jules
task** in this repo. **Link, don't restate:** the build plan, the decision-loop
contract, and the README handoff already exist. This overlay adds phase shape,
DoD, and risk; it does not re-architect.

## Canonical direction

Build graph nodes and graphs. Get operator (Sab) first-hand exposure to the full
range of domain problems. Iterate and test — finalize the remaining pieces of the
decision and verification loop. **Goal: overnight run is a success.**

## How the pieces fit

GDDP is two repos that work together. **This repo** (`gddp-runtime`) is the
pipeline — webhook intake → classify → scope → queue → execute. **`gddp-config`**
(next directory over) is the graph — YAML node definitions, dependency edges, and
state tracking. The runtime reads the graph to know what to build next; it writes
results back to the graph so nodes progress toward `complete`. A **graph node**
is a YAML file in gddp-config that defines one unit of work (a feature, a fix, a
doc). A **Jules task** is a bounded coding job dispatched from this repo that
produces a PR against the codebase the graph node points at. The verification
harness (Phases 1–4) watches both: it reads the PR diff, the tests, and the
graph edges, and returns pass/fail without editing code.

## Source docs (read before decomposing any phase)
- Direction + gaps: [`PROJECT-BRIEF.md`](PROJECT-BRIEF.md)
- **The build plan** — verification module, 5 tasks / 3 waves / worktree parallelism: [`verification-parallel-build-revised.md`](verification-parallel-build-revised.md) — load-bearing; Phases 0–3 below sequence it, not replace it
- Decision-loop v0 contract (4 powers, event-driven, hard limits): [`docs/decision-loop-spec.md`](docs/decision-loop-spec.md) — **draft/future; label as such**
- Portfolio README handoff (voice, shape, scrub list): [`docs/HANDOFF-PI-README.md`](docs/HANDOFF-PI-README.md)
- Trials ops runbook: [`deploy/BIGPI_RUNBOOK.md`](deploy/BIGPI_RUNBOOK.md)
- Vision framing for README "why": [`docs/gdd-next.md`](docs/gdd-next.md)

## Phase summary
| # | Phase | Build | Audit | Understand | Native unit |
|---|---|---|---|---|---|
| 0 | Pre-work / dependency gate | skeleton, stub, schema | pytest green | ADR (graph_updater decision + WHY) | 1 commit + 1 ADR |
| 1 | Structural validator + decision engine | Wave 1 (validator + engine) | merge-time pytest, matrix review | invariant checks as learning artifacts | 2 Jules tasks |
| 2 | Conductor / return-path wiring | Wave 2 (full return path) | dry_run.py E2E, zero-config-write assert | "runtime cannot mutate config truth" as architecture | 1 Jules + 1 graph node |
| 3 | Semantic evaluator + shape profiles | Wave 3 (LLM evaluator + profiles) | schema-rejection tests, YAML validation | shape profiles as domain understanding | 2 Jules tasks |
| 4 | Trials-readiness / overnight reliability | failure-mode handling, cron, escalate | overnight runs, failure-mode injection | operator learns the failure surface firsthand | 1 graph node + runbook |
| 5 | Finish-for-public | scrub verification script | grep sweep, link checker, tests still pass | README (portfolio confidence), ADR notes, labels | docs + test commits |

## Phases
Each phase carries all 3 dimensions: **build** (expansion/actualization), **audit**
(build + run testing infrastructure), **understand** (docs, learning artifacts,
competence demonstration).

### Phase 0 — Pre-work / dependency gate
- **Scope:** the 4 pre-work items in [`verification-parallel-build-revised.md`](verification-parallel-build-revised.md) §Pre-work on main — module skeleton, `SemanticOutput` stub, `shape_profile.yaml` schema, and the **`graph_updater` decision** (PR-proposal vs direct Contents-API write) recorded as an ADR near `return_router.py`.
- **Build:** module skeleton, stub, schema on `main`.
- **Audit:** `python3 -m pytest -q` green after each pre-work commit.
- **Understand:** ADR names the graph_updater choice (recommended: PR-proposal) and WHY — this is a decision the operator made deliberately, not an accident.
- **DoD:** all 4 on `main`; ADR present; tests green.
- **Dependency:** none (first).
- **Risk:** graph_updater decision blocks Phase 2 — do not skip.
- **Native unit:** 1 commit on main + 1 ADR.

### Phase 1 — Structural validator + decision engine (build Wave 1)
- **Scope:** Tasks 1 + 2 — structural validator (5 invariant checks) + decision rules engine (6-row matrix as a lookup table, not nested ifs). File-level scope locks are the per-agent packets in the build plan.
- **Build:** the validator and the engine. Two Jules tasks on separate branches, mergeable via worktree.
- **Audit:** merge-time `pytest scripts/runtime/verification` green after each `--no-ff`; review the decision matrix as a table (not a code structure) to catch logic errors.
- **Understand:** the 5 invariant checks and the 6-row decision matrix are learning artifacts — they encode what "done means" for a graph node. Reading them teaches the operator (and any future reader) the domain.
- **DoD:** both branches merged `--no-ff`; tests green; per-agent stop-condition contract met.
- **Dependency:** Phase 0 (`SemanticOutput` stub).
- **Risk:** scope creep into Task 3/4 — the stop condition is the guard.
- **Native unit:** 2 Jules tasks (`feature/t1-structural`, `feature/t2-decision`).

### Phase 2 — Conductor / return-path wiring (build Wave 2, standalone)
- **Scope:** Task 3 — `return_router → review_queue → review-node packet → structural → optional semantic → decision engine → verdict → graph_updater PR-proposal`. Touches live files + Pi harness packet; **no parallelism**.
- **Build:** wire the full return path. This is the conductor that makes the verification loop operational — without it, Phases 1 and 3 are isolated components.
- **Audit:** `scripts/dry_run.py` end-to-end (SQLite only); assert receipt written, zero config writes. The zero-config-write assert is the load-bearing test — it proves "runtime cannot mutate config truth" at the integration level, not just in a unit test.
- **Understand:** the "runtime cannot mutate config truth" rule becomes visible as architecture, not accident. The README (Phase 5) explains WHY; the dry_run proves it.
- **DoD:** conductor path wired; runtime *proposes* graph mutations (PR-proposal), never silently mutates config truth; `decision-loop-runtime` node → `complete` in gddp-config.
- **Dependency:** Phase 1 + Phase 0 graph_updater ADR.
- **Risk:** any silent config write fails the phase.
- **Native unit:** 1 Jules task (`feature/t3-conductor`) + 1 graph node (`decision-loop-runtime`).

### Phase 3 — Semantic evaluator + shape profiles (build Wave 3)
- **Scope:** Tasks 4 + 5 — the LLM **semantic evaluator** (`evaluator_prompt` → LLM runner abstraction → JSON → `SemanticOutput`), which is the LLM core of the verification harness, + 4 shape profiles (`cli-tool`, `runtime-orchestrator`, `web-app`, `automation`).
- **Build:** the evaluator abstraction + 4 shape profiles. The evaluator is the piece that lets an LLM judge "does this node satisfy its semantic role?" without editing code.
- **Audit:** happy-path extraction + schema-rejection tests; YAML validation across profiles. The evaluator prompt is tested against known-good and known-bad examples.
- **Understand:** shape profiles encode domain knowledge — what "done" looks like for a CLI tool vs a web app vs an automation script. Building them teaches the operator the full range of node types the system handles.
- **DoD:** schemas validate; prompt renders from `node_spec × pr_diff × shape_profile`; 4 profiles validate; new LLM dependency recorded.
- **Dependency:** Phase 0 (shape_profile schema) + Phase 1 (decision engine consumes semantic).
- **Risk:** semantic verdict puts an LLM control-flow-adjacent — keep it advisory; the decision engine stays deterministic.
- **Native unit:** 2 Jules tasks (`feature/t4-semantic`, `feature/t5-shape-profiles`).

### Phase 4 — Trials-readiness / overnight reliability
- **Scope:** stale-state handling + cron-fallback idempotency + escalate paths for each failure mode in [`decision-loop-spec.md`](docs/decision-loop-spec.md) §Failure Modes; operator-facing drift flagging node-by-node.
- **Build:** failure-mode handling, cron fallback, escalate wiring. These make the system resilient enough to run unattended.
- **Audit:** N consecutive overnight runs stable (define N with operator); failure-mode injection — inject each spec'd failure mode, assert escalate fires and writes a result row + log line. The operator (Sab) gets first-hand exposure to the full range of domain problems during these runs.
- **Understand:** the runbook + failure-mode log teach the operator what breaks, how it breaks, and how the system recovers. This is hands-on domain learning — the overnight runs are the operator's classroom.
- **DoD:** N overnight runs stable; escalate fires on every spec'd failure mode; `decision-loop-review-gate` node → `complete`.
- **Dependency:** Phases 1–3.
- **Risk:** review/accept powers are **draft/future, not the stable contract** — label them before trials.
- **Native unit:** 1 graph node (`decision-loop-review-gate`) + runbook updates.

### Phase 5 — Finish-for-public (portfolio polish)
- **Scope:** (a) Build a scrub verification script that automates the grep sweep + link resolution + test pass — this becomes part of the repo's CI/test infrastructure and runs on every future commit. (b) Portfolio `README.md` per [`HANDOFF-PI-README.md`](docs/HANDOFF-PI-README.md) — voice: confident, not boastful; mixed audience. (c) Scrub host-roles topology leak (`ssd-big`, `ssd-small`, `mac`, SSH paths, Big Pi `~/opclaw`). (d) `graph_updater.py` stub disposition — README explains WHY it's disabled. (e) `.agents/hooks/ag_natural_guard.py` attribution. (f) Label `decision-loop-spec.md` review/accept powers as draft/future. (g) Note `gddp-config` branch `feat/openclaw-nodes` is historical.
- **Build:** scrub verification script (reusable test infrastructure). README draft.
- **Audit:** run the scrub script — `grep` sweep clean, all links resolve, `pytest` still passes. The script is the audit infrastructure; running it is the audit.
- **Understand:** README demonstrates portfolio confidence — what the system is, why it exists, how it was verified. ADR notes and labels preserve decisions as learning artifacts. Scrub proves the repo is safe for public eyes.
- **DoD:** README draft (Sab sign-off); scrub script built and passing; stub explained; attributions + labels in place.
- **Dependency:** Phase 4 (README reflects final architecture).
- **Risk:** scrub is load-bearing for public — any operator-topology leak is a real op-sec issue.
- **Native unit:** docs commits + scrub verification script. **Drafts only, no push.**

## Execution + commit policy
- Order: Phase 0 → 1 → 2 → 3 → 4 → 5. Waves 1 and 3 parallelize (worktree); Wave 2 standalone.
- Branch: this plan and all phase work land on the current branch `fix/decision-loop-io-seams`; **no push** until Sab signs off.
- Re-derive nothing: when decomposing a phase into Jules tasks, copy the packet text from [`verification-parallel-build-revised.md`](verification-parallel-build-revised.md) verbatim.

## Open (Sab decides)
- **Trials N:** how many consecutive stable overnight runs close Phase 4?
- **README push gate:** Phase 5 README stays draft until explicit sign-off (assumed yes).
- **gddp-config branch:** rename `feat/openclaw-nodes` → decision-loop naming now, or leave + document?
