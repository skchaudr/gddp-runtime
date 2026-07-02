# Mission 001 — Harden Semantic Verification

**Goal:** Replace the semantic verifier's free-text JSON final answer with a typed `submit_verdict` tool, add validation-retry and forced termination, split criteria confidence from artifact completeness, and rerun the `vault-doctor` 7-node case against GLM and DeepSeek. The work lives on `sab-air` (`main` there, not yet pushed to `origin/main`).

**Strategic framing:** This is the choke point. The verification skeleton already proved itself on `sab-air`: structural + deterministic checks, an 11-row decision engine, a budget-capped tool loop, and a receipt sink are all in place. The next move is to harden the terminal verdict path so failures become operational/design failures instead of parser or model-loop failures. Do not jump to ANE, pydantic-ai adoption, more practice graphs, dashboards, or broader orchestration until this verdict path is hardened.

---

## Ground-truth current state (on `sab-air`, branch `main`)

- `sab-air:/Users/sab-mini/repos/gddp-runtime` has a working verification module under `scripts/runtime/verification/` with the latest commit `a5b4dfe`.
- Key files already exist and are functional:
  - `scripts/runtime/verification/semantic/agent.py` — budget-capped semantic tool loop with `AnthropicRunner`.
  - `scripts/runtime/verification/semantic/tools.py` — read-only evidence tools (`read_file`, `grep_code`, `run_command`, `git_diff`, etc.).
  - `scripts/runtime/verification/semantic/prompt.py` — system prompt that tells the model to **return free-text JSON matching `SemanticOutput`**. This is the exact failure mode the reflection targets.
  - `scripts/runtime/verification/decision_engine.py` — 11-row verdict matrix; returns a single `confidence` float that blends criteria confidence with artifact completeness.
  - `scripts/runtime/verification/orchestrator.py` — `verify()` runs deterministic checks, then semantic if needed, then `decide()`.
  - `scripts/runtime/verification/receipt_sink.py` — writes `VerdictReceipt` to `~/.gddp/receipts/<project>/<node>.json`.
  - `scripts/runtime/verification/schemas.py` — `VerdictReceipt` has one `confidence` field; `SemanticOutput` has no terminal tool.
- `origin/main` does **not** contain this work yet. The local `sab-mini` machine also does not have it.
- The `vault-doctor` graph in `gddp-config` has 7 nodes and is the acceptance case.
- Only `AnthropicRunner` exists; GLM and DeepSeek runners are not yet wired, so the reflection's acceptance run cannot be performed as-is.

---

## In scope

1. On `sab-air`, branch from `main` and implement `submit_verdict` as the **only accepted terminal action** for the semantic verifier.
2. Add a typed `SemanticVerdict` / `submit_verdict` schema and update `SemanticOutput` so the loop is invalid until the model calls the terminal tool.
3. Add validation-retry: if the `submit_verdict` payload fails schema validation, re-prompt with the exact error and request a corrected tool call.
4. Add forced termination: when remaining turns/tokens hit a threshold, inject a system message that says `You must now call submit_verdict using the evidence gathered so far.`
5. Split the confidence axis from the completeness axis:
   - `criteria_confidence` = confidence that criteria are satisfied.
   - `completeness_status` = artifact/trail/gate status.
   - `overall_verdict` = operational completion state.
6. Update the 11-row decision matrix and `VerdictReceipt` to use the split-axis fields.
7. Add GLM and DeepSeek runners (or a generic OpenAI-compatible runner) so the same tool path works across providers.
8. Rerun the `vault-doctor` 7-node case against GLM and DeepSeek and produce valid receipts.
9. Add tests for validation-retry, forced termination, and split-axis calibration. Run `pytest scripts/runtime/verification`.
10. Record any new dependency (LLM clients) in a dependency file. `gddp-runtime` currently has no `requirements.txt`; `deploy/setup.sh` installs Flask only.

## Out of scope

- ANE / implementer edit tool / patch.diff producer.
- pydantic-ai adoption beyond the specific validation-retry primitive described here.
- New practice graphs, dashboards, or broader orchestration beyond the verifier loop.
- Pushing the current `sab-air/main` state to `origin/main` is a prerequisite, not the mission itself; do it safely as the first step if needed.
- Direct source-of-truth graph mutation; the runtime must continue proposing evidence PRs, not silently mutating graphs.

---

## Deliverables

| # | Deliverable | Location | Acceptance check |
|---|-------------|----------|------------------|
| 1 | `submit_verdict` tool schema + `SemanticVerdict` model | `scripts/runtime/verification/semantic/tools.py` + `schemas.py` | Pydantic validates every field; terminal tool is distinct from evidence tools. |
| 2 | Verifier loop with terminal tool contract | `scripts/runtime/verification/semantic/agent.py` | Model may reason/inspect/call evidence tools, but run is invalid until `submit_verdict` is called. |
| 3 | Validation-retry logic | `scripts/runtime/verification/semantic/agent.py` | On schema failure, re-inject the exact error and request a corrected `submit_verdict`. |
| 4 | Forced termination | `scripts/runtime/verification/semantic/agent.py` | If `remaining_turns <= threshold`, inject mandatory finalization instruction. |
| 5 | Split-axis receipt + decision engine | `scripts/runtime/verification/schemas.py` + `decision_engine.py` | `VerdictReceipt` has `criteria_confidence`, `completeness_status`, `missing_artifacts` separate from `verdict`. |
| 6 | Multi-provider runners | `scripts/runtime/verification/semantic/agent.py` or new `semantic/runners.py` | GLM and DeepSeek complete the same tool path; Anthropic runner stays intact. |
| 7 | Orchestrator integration | `scripts/runtime/verification/orchestrator.py` | Calls semantic verifier, persists typed receipt, never tolerates prose JSON. |
| 8 | Acceptance run | `vault-doctor` 7-node case on `sab-air` | GLM completes via `submit_verdict`; DeepSeek completes or fails cleanly; missing artifacts yield `NEEDS_MORE_EVIDENCE` without crushing `criteria_confidence`. |

---

## `submit_verdict` schema

```python
submit_verdict({
  node_id: str,
  graph_id: str,
  criteria: [
    {
      criterion_id: str,
      verdict: Literal["judged_pass", "judged_fail", "needs_more_evidence", "unknown"],
      confidence: float,  # 0.0–1.0, independent of artifact completeness
      rationale: str,
      evidence_refs: list[str],
      risks: list[str]
    }
  ],
  overall_verdict: Literal["PASS", "FAIL", "NEEDS_MORE_EVIDENCE", "INVALID", "INCOMPLETE"],
  criteria_confidence: float,  # aggregate across criteria
  completeness_status: Literal["complete", "missing_execution_artifacts", "missing_trail", "gate_blocked"],
  missing_artifacts: list[str],
  recommended_next_action: str
})
```

Key rule: **criteria_confidence and completeness_status are separate**. Do not let the artifact gate crush the confidence score again. The honest state from the reflection is:

```python
overall_verdict: NEEDS_MORE_EVIDENCE
criteria_confidence: ~0.95
completeness_status: missing_execution_artifacts
reason: code appears to satisfy criteria, but required receipts/trail are absent
```

---

## Execution plan (on `sab-air`)

1. **Branch:** `git checkout -b feat/harden-semantic-verdict` from `sab-air:/Users/sab-mini/repos/gddp-runtime/main`. If the current work is not yet on `origin/main`, push or PR it as a separate sync step first.
2. **Schema:** add `SemanticVerdict` / `submit_verdict` to `scripts/runtime/verification/schemas.py` and register `submit_verdict` in `semantic/tools.py` as a terminal tool (no side effects, returns structured data only).
3. **Agent loop:** rewrite `SemanticAgent.run()` so the final accepted content is a `submit_verdict` tool call. Drop the `SemanticOutput.model_validate_json(content)` free-text parse path. Any non-tool final content is treated as a schema error and re-prompted.
4. **Validation-retry:** wrap the `submit_verdict` parse; on `ValidationError`, append the exact error to the message list and instruct the model to call the tool again with corrected arguments.
5. **Forced termination:** when `remaining_turns <= 2` (or `remaining_tokens <= threshold`), prepend a system message: `You must now call submit_verdict using the evidence gathered so far.`
6. **Decision engine calibration:** update `scripts/runtime/verification/decision_engine.py` so the matrix returns `criteria_confidence` and `completeness_status` separately, and update `VerdictReceipt` in `schemas.py` to store both.
7. **Multi-provider runners:** add GLM and DeepSeek runners that implement the same `Runner` protocol and use the same tool schema. Keep provider-specific quirks isolated in each runner.
8. **Acceptance run:** run the `vault-doctor` 7-node case against GLM and DeepSeek. Collect receipts, fix any harness-level failures, and record the scoreboard.
9. **Tests:** add unit tests for validation-retry, forced termination, and split-axis calibration. Run the full suite: `pytest scripts/runtime/verification`.
10. **Handoff:** write `docs/handoffs/002-semantic-verdict-hardening.md` capturing the scoreboard, known model quirks, and the next P1 item (let dispatched Jules issues produce real execution artifacts).

---

## Acceptance criteria

- [ ] `submit_verdict` is the only accepted terminal action; no free-text final JSON is parsed.
- [ ] Schema validation failures are caught and re-prompted with the exact error.
- [ ] Budget-forced termination produces a valid verdict without model looping.
- [ ] `vault-doctor` 7-node case runs end-to-end with GLM and DeepSeek.
- [ ] Missing artifacts produce `overall_verdict=NEEDS_MORE_EVIDENCE` while `criteria_confidence` stays high if the code evidence is strong.
- [ ] Receipts use split-axis fields (`criteria_confidence`, `completeness_status`, `missing_artifacts`).
- [ ] All verification tests pass: `pytest scripts/runtime/verification`.
- [ ] No dict/string risk shape errors occur in any output.
- [ ] New dependencies are recorded in a dependency file (e.g., `requirements.txt` or `pyproject.toml`).
- [ ] The hardened branch is pushed to `origin` (or prepared as a PR) so it is not stranded on `sab-air` again.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Work is stranded on `sab-air` and not on `origin/main`. | Push or PR the current `sab-air/main` state first; then branch for the hardening work. |
| DeepSeek ignores the tool instruction and loops. | Forced termination + validation-retry lift the model; if it still fails, record a clean harness-level reason, not a parser crash. |
| GLM/Anthropic tool protocol quirks differ. | Keep the tool schema identical for all models; isolate provider-specific adapter logic in each runner, not the verifier. |
| No `requirements.txt` means dependency changes are invisible. | Add one for the LLM clients and any new library; update `deploy/setup.sh` to install it. |
| The current `confidence` field is used downstream. | Search for `receipt.confidence` or `confidence` consumers and update them to use the split-axis fields. |

---

## Success metric

The mission is complete when the verifier harness on `sab-air` can take a `vault-doctor` node, run it through deterministic + semantic checks, and emit a typed `submit_verdict` receipt that a downstream consumer can trust without parsing invented JSON. GLM must complete cleanly; DeepSeek must complete or fail with a harness-level reason, never by looping or emitting prose.

---

## Post-mission (do not start until this mission is closed)

- Let dispatched Jules issues create the missing execution artifacts for the `vault-doctor` nodes that genuinely need them.
- Prototype ANE as an implementer edit tool / patch.diff producer.
- Write redesign nodes into the `gddp-runtime` graph so the runtime itself can be evolved under the same verifier.
- Sync the hardened result to `origin/main` and the `sab-mini` machine.
