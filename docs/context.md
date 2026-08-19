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

## 2. Canonical Root Documents

The following documents in `docs/` have foundational authority cited by `AGENTS.md`:

- [`docs/Tests-can-fail-nodes-can-pass.md`](Tests-can-fail-nodes-can-pass.md) — Node status reflects human-accepted intent, not temporary test pass/fail state.
- [`docs/GDDP-becomes-small-and-real.md`](GDDP-becomes-small-and-real.md) — GDDP's boundary: intent preservation & graph integrity layer, not the agent harness.
- [`docs/dispatch-checklist.md`](dispatch-checklist.md) — Operational checklist for dispatch readiness.

---

## 3. Epistemic Conflict Rules

1. If a proposal in `proposals/` contradicts `invariants/` or `current/`, the invariant/current truth overrides the proposal.
2. If a historical doc in `archive/` describes an architecture differently from `current/`, the archive is obsolete.
3. If an empirical observation in `learning/` discovers a gap in `current/`, submit a proposal before treating the finding as accepted architecture.
