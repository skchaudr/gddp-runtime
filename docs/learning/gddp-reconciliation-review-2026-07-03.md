# GDDP Reconciliation Review — 2026-07-03

**Status:** Out-of-repo synthesis for operator (Sab) review. Not tracked in any repo.
**Purpose:** Let you confirm baseline truth and the `verdict-confidence-split` evidence
at your own pace, in code, before you decide the graph status flip. Nothing here
mutates graph truth.

**Scope reviewed:** `gddp-runtime` @ `f523174`, `gddp-config` @ `ea00d33`.
Both clean, `0 ahead / 0 behind origin/main` (verified via `git fetch --prune`).

---

## 1. Baseline truth (what the trail actually says)

Following `.handoffs/` (your canonical source) + git + the `gddp-config` graph nodes,
not the `missions/` file:

| Claim I made earlier | Reconciled truth |
|---|---|
| `completeness_status` enum diverged | **No divergence.** Canonical graph node defines `complete \| partial \| not-run`; shipped code matches. The `missions/001` enum (`missing_execution_artifacts \| missing_trail \| gate_blocked`) was never canonical. |
| `requirements.txt` drift | **Not a divergence.** Flask/PyYAML/Pydantic/Anthropic recorded; GLM/DeepSeek path is stdlib `urllib` by design. |
| Push-auth risk (handoffs 017–019) | **Resolved.** Both repos synced to origin. |
| `missions/001` describes future work | **Stale artifact.** Now banner-marked superseded (kept for history). |

**Canonical spec = graph nodes**, at:
- `gddp-config/graphs/gddp-runtime/nodes/verification-receipt-contract.yaml` → `status: complete`
- `gddp-config/graphs/gddp-runtime/nodes/verdict-confidence-split.yaml` → `status: ready`

---

## 2. `verdict-confidence-split` — confirm-at-your-pace checklist

Node currently `status: ready`, `priority: high`. Depends on `verification-receipt-contract`
(already `complete`). Below, each acceptance criterion maps to a file + line you can open.

### 2a. Receipt schema exposes two axes
- **Confirm:** `gddp-runtime/scripts/runtime/verification/schemas.py` → `class VerdictReceipt`
  has `criteria_confidence`, `completeness_status`, and a legacy `confidence` alias with a
  validator that rejects mismatches.

### 2b. Blend defers to semantic when deterministic floor is indeterminate
- **Confirm code:** `scripts/runtime/verification/decision_engine.py:136` → `_confidence_semantic_blend(...)`
- **Confirm test:** `scripts/runtime/verification/test_decision_engine.py:262`
  → `test_semantic_confidence_blend_defers_to_semantic_when_floor_is_indeterminate` — PASSED

### 2c. Artifact gate caps the verdict only, not confidence
- **Confirm test:** `test_decision_engine.py:142` → `test_matrix_row_6_needs_more_evidence_semantic_pass_missing_artifacts`
  asserts `confidence == 0.95` with verdict `needs-more-evidence` — PASSED

### 2d. Passing node reads high confidence (`>= 0.85`)
- **Confirm fixture:** `scripts/runtime/verification/fixtures/verification_receipts/semantic-pass-with-missing-artifacts.json`
  → `criteria_confidence: 0.92`, `verdict: needs-more-evidence`

### 2e. Genuine semantic fail → low criteria_confidence
- **Confirm fixture:** `.../semantic-fail-with-complete-artifacts.json`
  → `criteria_confidence: 0.21`, `verdict: fail`
- **Confirm test:** `test_decision_engine.py:298` → `test_semantic_fail_yields_low_criteria_confidence` — PASSED

### 2f. Full verification suite
- **Reproduce:** `cd gddp-runtime && .venv/bin/python -m pytest -q scripts/runtime/verification`
  → **65 passed** (2026-07-03)

### 2g. No graph mutation
- Offline CLI receipt written only to `/tmp`, split-axis fields populated, zero writes to
  `gddp-config`. Reproduce:
  ```
  cd gddp-runtime && .venv/bin/python -m scripts.runtime.verification.cli \
    --node-yaml ../gddp-config/graphs/gddp-runtime/nodes/verdict-confidence-split.yaml \
    --project-yaml ../gddp-config/graphs/gddp-runtime/project.yaml \
    --repo . --config-root ../gddp-config --receipt-dir /tmp/gddp-vcs-evidence
  ```

### The one honest gap (blocks a clean "complete", not a bug)
The criterion naming **"vault-doctor scan-vault-core"** wants a **live** semantic run
(real model, all judgments pass → `criteria_confidence >= 0.85`). That needs
`DEEPSEEK_API_KEY` or `GLM_API_KEY`, unavailable in this session. The offline runner
returns `~0.17` by design (marks everything indeterminate), so it does **not** demonstrate
the live calibration win. The win is proven deterministically by 2c/2d above. A fresh live
receipt is the last artifact if you want it attached before flipping.

---

## 3. Recommended flip decision (yours to make)

`verdict-confidence-split` can move `ready → complete` on the strength of tests + fixtures
above. If you require the live vault-doctor receipt first (consistent with how
`verification-receipt-contract` was proven in handoff 018), hold the flip until keys are
available and re-run 2g in `--semantic-mode live`.

---

## 4. Two forward tasks (your stated clean vision)

1. **Runtime loop** — the classify → scope → queue → execute pipeline.
2. **Semantic verification / valuation harness** — the verifier hardening thread this
   reconciliation just baselined.

Both should be driven via `.handoffs/` going forward. "Missions" is not your workflow.
If/when you introduce a weekly synthesis, it lives as `.handoffs/000-weekly-review.md`,
not `decisions.md`.
