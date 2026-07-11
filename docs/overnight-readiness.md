# Overnight Readiness Checklist

Source: Phase 3 of the "GDDP Pathway Hardening & Readiness Spec" (GLM5.2, 2026-07-07),
promoted out of paste-cache so it stops going missing. Implementation tracked in
`.handoffs/028-pathway-hardening-spec-implementation.md`.

A task box, not a pass/fail gate. Each item is something verified or completed
before unattended operation.

## Done

- [x] Full cycle e2e test passes in CI
- [x] dry_run.py exercises the real return path, not a fake one
- [x] decision_loop engine does not crash on missing anthropic
- [x] bridge credential source is configurable, not hardcoded
- [x] heartbeat no longer does runtime ALTER TABLE
- [x] classifier respects `node:` tags in event metadata
- [x] v2 verdict contract deployed: receipts carry intent/integrity fields
- [x] canonical context builder deployed: evaluator reads README + DAG, not AGENTS.md
- [x] integrity lane deployed: always-on, independent evidence, no worst-of
- [x] suite-green: `python3 -m pytest -q scripts/` passes, no regressions
- [x] receipt backward compat: old receipts still parse with new schema
- [x] gddp-config graph status reflects current reality (reconciliation pass, 2026-07-09)
- [x] reconciliation verbiage pass complete — spec field names aligned
- [x] heartbeat cron configured on pi-big (2026-07-09)
- [x] DEEPSEEK_API_KEY available in overnight execution environment (verified via pass, 2026-07-10)

## Remaining (live-fire proofs)

- [x] X1: heartbeat live-fire (2026-07-11) — full loop ran end-to-end: heartbeat dispatched
      job_20260711T16020485 to Jules (issue #91), PR #92 merged with metadata block intact,
      return path (newly wired into runner) parsed it, two-lane evaluator ran, verdict pass,
      job parked awaiting_review. Verdict receipt on droid machine (gitignored — unversioned).
- [x] Integrity lane proven live (2026-07-10) — live pi run on vault-doctor/find-duplicates
      produced populated IntegrityReport (integrity verdict `drift`, 3 findings; criteria
      verdict `fail` @0.075; graph truth untouched, receipt in session scratchpad)
- [x] Retry loop proven live (2026-07-11) — canary-retry-proof node with a hidden
      criterion (docs/echo-usage.md) drew a fail verdict with file-path evidence;
      should_retry fired, _redispatch_with_findings created issue #101 with
      "Previous Attempt Findings" in the body, attempt 0→1 after dispatch. Verdict
      receipt versioned at .handoffs/artifacts/032-live-retry-proof-canary-fail-verdict.json
      (240fb84). JSON double-parse bug in the redispatch path found+fixed by the same run.
- [x] `retry_budget: 3` added to all gddp-config execution_policy blocks (600a6cc, 2026-07-10)
- [ ] heartbeat restart-on-crash behavior tested (cron exists; crash-recovery unproven)

## Constraints carried from the spec

- Human-gated completion invariant never violated: only Sab moves a node to complete.
- Graph truth stays human-owned; runtime never mutates gddp-config.
- Evaluator is read-only (guard blocks mutations, network, dangerous bash).
- Criteria verdict and integrity findings are independent evidence; neither rescues
  nor suppresses the other, no mechanical combination rule.
