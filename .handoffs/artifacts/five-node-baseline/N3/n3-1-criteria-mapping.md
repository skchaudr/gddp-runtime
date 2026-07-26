# N3-1 — Map N3 criteria to existing N2 receipt + evaluator code

- Date: 2026-07-26
- Node: `immediate-evaluator-round-trip` (gddp-config @ `4657c86`, unchanged)
- Evidence source: N2 attempt 1 receipt (`../N2/n2-live-attempt-1/evaluator-receipt.json`,
  job `job_20260726T081330259c7d2af87dc3`, evaluated commit `6c0a4b2d…b5ff`)
  + reconcile capture (`../N2/n2-live-attempt-1/n2-6-01.reconcile.stdout`)
- Code surveyed @ runtime `96435aa`: `scripts/runtime/heartbeat/reconciler.py`,
  `scripts/runtime/heartbeat/runner.py`, `scripts/runtime/verification/orchestrator.py`,
  `scripts/runtime/verification/integrity_combiner.py`
- Gate basis: plan v3.5 — "N3-1 can start as soon as N2 archive exists." Read-only.

## Criteria map

| Criterion | Evidence | Status |
|---|---|---|
| `automatic-evaluation-entry` | `reconciler.py:542 _trigger_evaluation` fires inside `_reconcile_one` on session completion; `reconcile_sessions` runs **every heartbeat tick** (`runner.py:133`) before planning. N2 live capture: `completed → evaluation: ok → verdict: pass` — no separate evaluation-start command, no manual evidence movement (result commit discovered by polling the executor session). | **Met.** Nuance: the N2 tick was operator-invoked (runbook step) rather than awaited from the launchd heartbeat; same function, same path, hand-fired timing. The services `com.gddp.heartbeat`/`com.gddp.intake` are loaded, so unattended ticks exist. |
| `per-criterion-judgment` | Receipt `deterministic.criteria[]` (5 entries: status, confidence, method, evidence, reasoning) + `semantic.judgments[]` (5 entries: judgment, confidence, evidence, reasoning). Each criterion has a visible judgment and the evidence used. | **Met.** |
| `intent-integrity-judgment` | Separate `integrity` lane: `verdict`, `intent_preserved`, `graph_integrity_preserved`, `confidence 0.95`, findings, reasoning; own `lane_status: completed`. Distinct from `criteria_verdict`. | **Met.** |
| `decision-shaped-no-decision` | `verdict: pass` + `required_next_action: "Proceed to accept_node"`; job left at `awaiting_review`; receipt filed as evidence only; graph unchanged (gddp-config HEAD `4657c86` before and after). The evaluator cannot move the node. | **Met.** |

## Constraint check

| Constraint | Evidence | Status |
|---|---|---|
| Lanes independent; neither rescues/suppresses | `orchestrator.py:239` "Overall = worst of the two lanes that ran"; `integrity_combiner.combine(criteria_verdict, integrity, action)`. Both lanes reported separately in the receipt. | Met |
| Read-only against graph truth + project canon | Evaluator reads gddp-config nodes + isolated eval worktree; writes only the receipt under `verification-runtime-live/<project>/<node>/`. No graph/status writes. | Met |
| No AGENTS.md; canonical context = README + PROJECT-BRIEF + foundational node | Receipt `canonical_context` lists exactly those three; `context_coverage.overall: high` (3/3 accessed, both lanes). | Met |
| Required artifacts are evidence, not the verdict | `artifacts_present` records `decision.md`, `result-summary.md`, `patch.diff`, `graph-update.yaml`; judgments cite them as evidence inputs. | Met |

## Which receipt fields N3 consumes vs ignores (bounded surface for N3-2/N3-4)

**Consumed:** `verdict`, `criteria_verdict`, `deterministic.criteria[]`, `semantic.judgments[]`,
`integrity.{verdict,intent_preserved,graph_integrity_preserved,confidence,reasoning}`,
both `lane_status` values, `artifacts_present`, `canonical_context`, `context_coverage`,
`required_next_action`, `job_id`, `evaluated_commit_sha`, `generated_at`.
**Not consumed for N3 criteria** (present, incidental to this node): `tool_trace` /
`budget_trace` (audit detail), `graph_observations`, `followup_candidates`, `risks`,
`decision_reasoning` (duplicates `semantic.overall_reasoning`), `completeness` /
`graph_readiness` rollups, `merge_commit_sha`, `pr_ref`.

## N3-2 record — no demonstrated gap → **no-change**

No criterion lacks evidence and no constraint lacks code backing. No evaluator code
was modified. The single nuance (operator-fired reconcile tick vs unattended
heartbeat tick) is recorded above as an observation, not a gap: the capability the
criterion names is the loop's own entry point, and that entry point fired.

## N3-3 — not needed by default

Rerun evaluation only if Sab names a missing criterion. Candidate if he wants it:
unattended-tick proof — let the next attempt's result sit until a launchd heartbeat
tick reconciles it, demonstrating entry with zero operator calls. Cheap; requires no
code change; can ride on any future attempt (e.g. an N4 dispatch).

## N3-4 — archive + Sab decision

Archive = this file. **Pending Sab disposition** on `immediate-evaluator-round-trip`:
accept / retry / revise / defer / abandon. Graph status unchanged until then.
