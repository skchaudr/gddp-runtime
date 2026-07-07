# Spec: Integrity Lane — always-on evaluator mandate (evaluator-intent-integrity-verdict)

Status: DRAFT — needs Sab sign-off before any implementation.
Implements Sab's decision (2026-07-07): the evaluator has two distinct responsibilities, not two modes of one decision.

## Doctrine (verbatim intent)

  1. **Criteria adjudication** — deterministic-first. Semantic reasoning fires only when deterministic evidence is insufficient or ambiguous (current `_should_run_semantic` behavior, post-b1727f1). Deterministic evidence CAN be sufficient to establish the node's verdict.
  2. **Integrity evaluation** — ALWAYS executes, regardless of deterministic outcome. Answers a different question: does the change preserve the health, intent, and structure of the project? A green deterministic run must not bypass this.

## v1 design (lean)

- New orchestrator phase after criteria adjudication: `integrity_review`.
- Runs the pi/deepseek harness with a SEPARATE system prompt and a SEPARATE typed
  terminal tool (`submit_integrity_verdict`, not `submit_verdict`).
- **Two verdicts, peers on the receipt** (amended 2026-07-07 after Sab flagged the
  advisory-only version as toothless):
  - `criteria_verdict` — decided by the existing 12-row matrix, untouched.
  - `integrity_verdict` — `clear | concerns | breach-suspected`, with confidence
    and findings `[{severity, summary, affected_node_ids}]`.
  - Top-level `verdict` = deterministic combination rule (small, auditable, NOT
    model judgment): integrity `breach-suspected` DOWNGRADES a criteria pass to
    `needs-human-review` with reason `integrity_breach`; `concerns` annotates but
    does not downgrade; integrity can NEVER upgrade a criteria fail/indeterminate.
    Authority is scoped per lane, never absent and never crossed.
- Investigation scope given to the model:
  - the node's `why` (intent), `constraints`, `depends_on` + `unlocks` neighbors
    (their YAML loaded as context), and the diff/artifacts under review
  - question: "does this change break or degrade neighboring nodes, dependency
    contracts, declared constraints, or the stated intent?"
- **Receipt**: gains `criteria_verdict` + `integrity` section; top-level `verdict`
  becomes the combined value per the rule above. This IS a receipt-contract change —
  Sab's Pi impact scan required before implementation (bridge summary keys,
  decision-row reporting, any receipt consumers).
- Evidence-scope rule carries over: integrity findings cannot rescue or rewrite the
  criteria verdict; criteria verdict cannot suppress integrity findings.

## Constraints

- decision_engine 12-row matrix and Verdict enum unchanged; the combination rule is
  a new layer AFTER the matrix, not an edit to it.
- Guard (gddp_verifier_guard.ts) applies identically — read-only investigation.
- Reuses pi_runner plumbing (HOME sandbox, trace, verdict-file pattern) — new
  extension file `gddp_integrity.ts` alongside `gddp_verifier.ts`, not a fork of it.
- Skippable via flag (`--integrity off`) for test/dev runs only; live bridge default ON.
- Cost note: one extra semantic call per job return (~1-2 min deepseek). Acceptable.

## Acceptance sketch (for node YAML, Sab authors final)

- integrity phase runs on a deterministic-clean row-12 pass (the exact case that
  used to bypass semantic entirely) and produces a populated IntegrityReport
- receipt shows both sections; criteria verdict identical with integrity on/off
- suite-green via command_proof

## Open for Sab

- name check: "integrity lane" vs existing node id `evaluator-intent-integrity-verdict`
- does `breach-suspected` ever justify auto-blocking dispatch of dependent nodes? (v2)
