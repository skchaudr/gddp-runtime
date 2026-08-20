# docs/context.md — Documentation Epistemic Authority Map

This document defines the authority, permanence, and classification of all documentation within `docs/`.

---

## 1. Documentation Tiers & Precedence

Documentation in this directory is partitioned into distinct epistemic tiers:

| Directory | Epistemic Tier | Authority Status | Primary Purpose |
|---|---|---|---|
| [`invariants/`](invariants/) | **Tier 1: Invariants** | Inviolable System Law | Rules that must remain true across all implementations and agents |
| [`current/`](current/) | **Tier 2: Current Truth** | Active Specification | Current production topology, active contracts, live loop |
| [`decisions/`](decisions/) | **Tier 3: Decisions** | Accepted Rationale | Why specific architectural choices were accepted |
| [`proposals/`](proposals/) | **Tier 4: Proposals** | Non-Canonical | Proposed designs, plans, or refactors (never assume accepted) |
| [`learning/`](learning/) | **Tier 5: Learning** | Empirical Observations | Postmortems, run reflections, field notes, failure analyses |
| [`artifacts/`](artifacts/) | **Tier 6: Artifacts** | Evidence & Output | Test logs, evaluation outputs, benchmark runs |
| [`archive/`](archive/) | **Tier 7: Archive** | Historical / Superseded | Decommissioned designs; do not resurrect without explicit node |

---

## 2. Canonical Decision & Current Truth Documents

The following documents define core architecture and operational checklists:

- [`docs/decisions/Tests-can-fail-nodes-can-pass.md`](decisions/Tests-can-fail-nodes-can-pass.md) — Node status reflects human-accepted intent, not temporary test pass/fail state.
- [`docs/decisions/GDDP-becomes-small-and-real.md`](decisions/GDDP-becomes-small-and-real.md) — GDDP's boundary: intent preservation & graph integrity layer, not the agent harness.
- [`docs/decisions/A-more-complete-evaluator-7-14-26.md`](decisions/A-more-complete-evaluator-7-14-26.md) — Evaluator as integrity-preserving project observer.
- [`docs/decisions/GDDP-rebuild.md`](decisions/GDDP-rebuild.md) — Provisional continuation and non-blocking evaluation.
- [`docs/current/dispatch-checklist.md`](current/dispatch-checklist.md) — Operational checklist for dispatch readiness.
- [`docs/current/decision-loop-spec.md`](current/decision-loop-spec.md) — Decision and reconciliation loop specification.

---

## 3. Epistemic Conflict Rules

1. If a proposal in `proposals/` contradicts `invariants/` or `current/`, the invariant/current truth overrides the proposal.
2. If a historical doc in `archive/` describes an architecture differently from `current/`, the archive is obsolete.
3. If an empirical observation in `learning/` discovers a gap in `current/`, submit a proposal before treating the finding as accepted architecture.

