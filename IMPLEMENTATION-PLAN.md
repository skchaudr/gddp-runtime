# GDDP — Implementation Plan

Sequel to [`PROJECT-BRIEF.md`](PROJECT-BRIEF.md). Direction + ground state live
there; this plan sequences the work into phases a lesser model can decompose
into native units — **graph node** in [`gddp-config`](../gddp-config) + **Jules
task** in this repo. **Link, don't restate:** the build plan, the decision-loop
contract, and the README handoff already exist. This overlay adds phase shape,
DoD, and risk; it does not re-architect.

## Source docs (read before decomposing any phase)
- Direction + gaps: [`PROJECT-BRIEF.md`](PROJECT-BRIEF.md)
- **The build plan** — verification module, 5 tasks / 3 waves / worktree parallelism: [`verification-parallel-build-revised.md`](verification-parallel-build-revised.md) — load-bearing; Phases 0–3 below sequence it, not replace it
- Decision-loop v0 contract (4 powers, event-driven, hard limits): [`docs/decision-loop-spec.md`](docs/decision-loop-spec.md) — **draft/future; label as such**
- Portfolio README handoff (voice, shape, scrub list): [`docs/HANDOFF-PI-README.md`](docs/HANDOFF-PI-README.md)
- Trials ops runbook: [`deploy/BIGPI_RUNBOOK.md`](deploy/BIGPI_RUNBOOK.md)
- Vision framing for README "why": [`docs/gdd-next.md`](docs/gdd-next.md)

## Direction (from brief)
Trials-ready: overnight runs stable and boringly reliable. The work that gets
there is **building a custom agent verification harness** — the actual
deliverable of Phases 0–4, and the heart of this plan. Its deterministic spine
is the structural validator + decision engine (Phase 1); its LLM core is the
semantic evaluator (Phase 3), which judges whether a node satisfies its semantic
role in the larger system, not just local test correctness; the conductor
(Phase 2) + trials (Phase 4) keep it observing graph state and invariants
continuously, catching drift and escalating node-by-node to the operator. In
other words, Phases 0–4 construct a custom agent harness where an LLM verifier
reads the diff, the tests, the node spec, and the graph edges, and returns
pass/fail/uncertain without editing code — `gdd-next.md`'s "builder agents
build, verifier agents verify, the graph decides what done means," made
operational. The "runtime cannot mutate config truth" rule stays visible as
architecture, not accident.

## Phases
Each phase carries: scope · DoD · dependency · verification · risk · native unit.

### Phase 0 — Pre-work / dependency gate
- **Scope:** the 4 pre-work items in [`verification-parallel-build-revised.md`](verification-parallel-build-revised.md) §Pre-work on main — module skeleton, `SemanticOutput` stub, `shape_profile.yaml` schema, and the **`graph_updater` decision** (PR-proposal vs direct Contents-API write) recorded as an ADR near `return_router.py`.
- **DoD:** all 4 on `main`; ADR names the chosen model (recommended: PR-proposal) and WHY.
- **Dependency:** none (first).
- **Verification:** `python3 -m pytest -q` green; ADR file present.
- **Risk:** graph_updater decision blocks Phase 2 — do not skip.
- **Native unit:** 1 commit on main + 1 ADR.

### Phase 1 — Structural validator + decision engine (build Wave 1)
- **Scope:** Tasks 1 + 2 — structural validator (5 invariant checks) + decision rules engine (6-row matrix as a lookup table, not nested ifs). File-level scope locks are the per-agent packets in the build plan.
- **DoD:** both branches merged `--no-ff`; `pytest scripts/runtime/verification` green; per-agent stop-condition contract met.
- **Dependency:** Phase 0 (`SemanticOutput` stub).
- **Verification:** merge-time pytest after each `--no-ff`; review matrix-as-table.
- **Risk:** scope creep into Task 3/4 — the stop condition is the guard.
- **Native unit:** 2 Jules tasks (`feature/t1-structural`, `feature/t2-decision`).

### Phase 2 — Conductor / return-path wiring (build Wave 2, standalone)
- **Scope:** Task 3 — `return_router → review_queue → review-node packet → structural → optional semantic → decision engine → verdict → graph_updater PR-proposal`. Touches live files + Pi harness packet; **no parallelism**.
- **DoD:** conductor path wired; runtime *proposes* graph mutations (PR-proposal), never silently mutates config truth; `decision-loop-runtime` node → `complete` in gddp-config.
- **Dependency:** Phase 1 + Phase 0 graph_updater ADR.
- **Verification:** `scripts/dry_run.py` end-to-end (SQLite only); assert receipt written, zero config writes.
- **Risk:** load-bearing invariant — "runtime cannot mutate config truth" (brief Narrative). Any silent write fails the phase.
- **Native unit:** 1 Jules task (`feature/t3-conductor`) + 1 graph node (`decision-loop-runtime`).

### Phase 3 — Semantic evaluator + shape profiles (build Wave 3)
- **Scope:** Tasks 4 + 5 — the LLM **semantic evaluator** (`evaluator_prompt` → LLM runner abstraction → JSON → `SemanticOutput`), which is the LLM core of the verification harness, + 4 shape profiles (`cli-tool`, `runtime-orchestrator`, `web-app`, `automation`).
- **DoD:** schemas validate; prompt renders from `node_spec × pr_diff × shape_profile`; 4 profiles validate against `shape_profile.yaml`; new LLM dependency recorded in the repo dependency file.
- **Dependency:** Phase 0 (shape_profile schema) + Phase 1 (decision engine consumes semantic).
- **Verification:** happy-path extraction + schema-rejection tests; YAML validation across profiles.
- **Risk:** semantic verdict puts an LLM control-flow-adjacent (see `gdd-next.md`: "remove the LLM from control-flow positions where rationalization can occur") — keep it advisory; the decision engine stays deterministic.
- **Native unit:** 2 Jules tasks (`feature/t4-semantic`, `feature/t5-shape-profiles`).

### Phase 4 — Trials-readiness / overnight reliability
- **Scope:** stale-state handling + cron-fallback idempotency + escalate paths for each failure mode in [`decision-loop-spec.md`](docs/decision-loop-spec.md) §Failure Modes; operator-facing drift flagging node-by-node.
- **DoD:** N consecutive overnight runs stable (define N with operator); escalate fires correctly on every spec'd failure mode; `decision-loop-review-gate` node → `complete`.
- **Dependency:** Phases 1–3.
- **Verification:** runbook-driven trials on Big Pi; failure-mode injection; `escalate` writes a result row + log line every time.
- **Risk:** review/accept powers are **draft/future, not the stable contract** — label them before trials or they read as shipped (brief gap).
- **Native unit:** 1 graph node (`decision-loop-review-gate`) + runbook updates.

### Phase 5 — Finish-for-public (portfolio polish)
- **Scope:** the plan-character layer —
  - (a) Portfolio `README.md` per [`HANDOFF-PI-README.md`](docs/HANDOFF-PI-README.md) — voice: confident, not boastful; mixed audience. **Drafts only, no push.**
  - (b) **Scrub host-roles topology leak** — `ssd-big`, `ssd-small`, `mac`, SSH paths, Big Pi `~/opclaw` surface across `docs/host-roles.md`, `docs/handoffs/`, `deploy/BIGPI_RUNBOOK.md`.
  - (c) `scripts/runtime/graph_updater.py` stub disposition — README explains WHY it's disabled (runtime cannot mutate config truth) or it reads as broken code (brief gap).
  - (d) `.agents/hooks/ag_natural_guard.py` — attribution/clarifying note for `.pi` cross-project reuse.
  - (e) Label `decision-loop-spec.md` review/accept powers as draft/future.
  - (f) Note `gddp-config` branch `feat/openclaw-nodes` is historical (objects use decision-loop naming).
- **DoD:** README draft (Sab sign-off before push); scrub grep clean in public-facing docs; stub explained; attributions + labels in place.
- **Dependency:** docs can draft in parallel, but the README reflects final architecture → gate after Phase 4.
- **Verification:** `grep -riE "ssd-big|ssd-small|opclaw|~/opclaw" README.md docs/ deploy/` returns nothing public-facing; README links resolve; tests still pass.
- **Risk:** scrub is load-bearing for public — any operator-topology leak is a real op-sec issue, not cosmetics.
- **Native unit:** docs commits (README, ADR notes, scrub pass).

## Execution + commit policy
- Order: Phase 0 → 1 → 2 → 3 → 4 → 5. Waves 1 and 3 parallelize (worktree); Wave 2 standalone.
- Branch: this plan and all phase work land on the current branch `fix/decision-loop-io-seams`; **no push** until Sab signs off (drafts-only per brief).
- Re-derive nothing: when decomposing a phase into Jules tasks, copy the packet text from [`verification-parallel-build-revised.md`](verification-parallel-build-revised.md) verbatim — it already carries file-level scope locks and acceptance criteria.

## Open (Sab decides)
- **Trials N:** how many consecutive stable overnight runs close Phase 4?
- **README push gate:** Phase 5 README stays draft until explicit sign-off (assumed yes).
- **gddp-config branch:** rename `feat/openclaw-nodes` → decision-loop naming now, or leave + document? (Phase 5f assumes document.)
