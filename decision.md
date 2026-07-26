# Decision: pi-evaluator-harness

## Outcome
Verified, did not modify. The base commit `3ac3914` already implements the
node's wiring. Live `--semantic-harness pi` run against a vault-style smoke
node produced a valid VerdictReceipt end-to-end.

## Why verify instead of build
- The base commit's tree already contains every file the criterion set names:
  - `scripts/runtime/verification/semantic/pi_harness/gddp_verifier.ts`
  - `scripts/runtime/verification/semantic/pi_runner.py`
  - `scripts/runtime/verification/semantic/pi_harness/gddp_verifier_guard.ts`
- The CLI, orchestrator, and bridge already pass `semantic_harness` through.
- The decision_engine matrix is untouched and the VerdictReceipt contract is
  unchanged, per the node's hard constraints.
- The OpenAICompatibleRunner / AnthropicRunner classes are still present in
  `semantic/agent.py`; pi is wired as an option, not a replacement.

## What I changed
- Created `.venv/` so the venv-interpreted test command in criterion 6 could
  actually run. The repo's `.gitignore` does not list `.venv/`, so this
  directory is untracked but ignored by convention (matches the runtime
  pattern where `db/`, `jobs/`, `events/` are similarly local-only).
- Wrote a smoke `node.yaml` and `project.yaml` under `/tmp/gddp-live-smoke/`
  (outside the repo) for the live end-to-end test. No repo files modified.
- Wrote the three required artifacts (`decision.md`, `result-summary.md`,
  `patch.diff`).

## What I did NOT change
- Decision engine matrix and VerdictReceipt contract (per constraint).
- `gddp_verifier.ts`, `gddp_verifier_guard.ts`, `gddp_integrity.ts`
  extensions — the typed submit_verdict contract is correct.
- `pi_runner.py` — already spawns `pi --print` with the extension, system
  prompt, and target repo as cwd.
- `orchestrator.py` — already accepts the optional `semantic_harness` callable.
- `cli.py` — already exposes `--semantic-harness {auto,pi,runner}`,
  `--semantic-thinking`, `--semantic-pi-model`.
- The OpenAICompatibleRunner / AnthropicRunner / SemanticAgent paths —
  preserved per constraint.

## Verification evidence
- `.venv/bin/python -m pytest -q scripts/runtime/verification` → 199 passed.
- Live run with `DEEPSEEK_API_KEY` against `/tmp/gddp-live-smoke/node.yaml`:
  - `verdict: pass` (assigned by decision_engine row 11, not by pi)
  - `criteria_confidence: 1.0` (decision_engine signals)
  - `completeness_status: complete` (orchestrator)
  - `semantic.judgments`: 2 × `judged_pass` @ confidence 1.0
  - `semantic.budget_trace.tool_calls`: 23 (12 read, 10 bash, 1 submit_verdict)
  - `context_coverage.criteria: high` (pi accessed PROJECT-BRIEF.md + README.md)
  - `lane_status.criteria: completed`, `harness_error.criteria: null`
  - Receipt written to `/tmp/gddp-live-smoke/receipts2/gddp-runtime/smoke-node.json`

## Graph truth
Untouched. This node produced evidence only.
