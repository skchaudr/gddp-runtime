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

- [ ] X1: heartbeat live-fire — one real heartbeat run dispatches a real job to a real executor
      (needs Sab's explicit go; only hardening item never executed live)
- [ ] Integrity lane proven live — one live pi run produces a populated IntegrityReport
- [ ] Retry loop proven live — one non-pass verdict with evidence refs re-dispatches
- [ ] `retry_budget` added to gddp-config project.yaml execution_policy (Sab; default 3)
- [ ] heartbeat restart-on-crash behavior tested (cron exists; crash-recovery unproven)

## Constraints carried from the spec

- Human-gated completion invariant never violated: only Sab moves a node to complete.
- Graph truth stays human-owned; runtime never mutates gddp-config.
- Evaluator is read-only (guard blocks mutations, network, dangerous bash).
- Criteria verdict and integrity findings are independent evidence; neither rescues
  nor suppresses the other, no mechanical combination rule.
