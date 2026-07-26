# Result Summary: pi-evaluator-harness

## Goal
Drive the semantic evaluator through the `pi` coding agent so the operator
gets live, streaming visibility into the investigator's text, thinking, and
tool calls — while preserving every GDDP contract (typed submit_verdict
terminal tool, the 12-row decision_engine, the VerdictReceipt, and the
read-only-where-it-matters invariant).

## Acceptance criteria — all met

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `gddp_verifier.ts` registers typed `submit_verdict` whose parameters mirror `SemanticOutput` and writes to `$GDDP_VERDICT_OUT` with `terminate: true` | PASS | `pi.registerTool({ name: "submit_verdict", parameters: SubmitVerdictParams, ... })`; `writeFileSync(outPath, JSON.stringify(payload), ...)`; `return { ..., terminate: true }`. Live run called it exactly once. |
| 2 | `pi_runner.py` spawns pi in `--print` mode with the extension loaded, pi-specific system prompt, target repo as cwd; reads verdict file, returns `SemanticOutput` | PASS | `cmd = [pi, "--print", "--mode", "text", "-e", str(EXTENSION_PATH), "-e", str(GUARD_EXTENSION_PATH), "--system-prompt", system_prompt, ...]`; `tee_subprocess(cmd, env, str(repo), ...)` sets `cwd=repo`; `raw = json.loads(Path(verdict_path).read_text(...))`; `return SemanticOutput.model_validate(raw)`. |
| 3 | `orchestrator.py` accepts optional `semantic_harness` callable that, when set, replaces `SemanticAgent.run()`; default path is unchanged | PASS | `semantic_harness: SemanticHarness \| None = None`; `if semantic_harness is None: raise RuntimeError(...)`; `semantic = semantic_harness(...)` when wired. The default path (no semantic needed) is unchanged — orchestrator skips and returns a deterministic receipt. |
| 4 | `cli.py` exposes `--semantic-harness {auto,pi,runner}` (auto → runner), `--semantic-thinking`, `--semantic-pi-model` | PASS | `choices=["auto", "pi", "runner"]`; `_resolve_harness(args)` returns `"runner"` for `auto`. `--semantic-thinking` and `--semantic-pi-model` also present with env-var defaults. |
| 5 | Live `--semantic-harness pi` run against a vault-doctor node produces a VerdictReceipt with populated `criteria_confidence`, `completeness_status`, and semantic judgments; decision_engine decides the verdict | PASS | See live receipt below. `verdict: "pass"` was assigned by `decision_engine.decide()` row 11, not by pi. pi produced the typed `SemanticOutput` (2 × `judged_pass`); decision_engine blended the deterministic + semantic signals into the final verdict. |
| 6 | `.venv/bin/python -m pytest -q scripts/runtime/verification` passes with no regressions | PASS | 199 passed, 0 failed. |

## Live receipt snapshot
Run command:
```
DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY .venv/bin/python -m scripts.runtime.verification.cli \
  --node-yaml /tmp/gddp-live-smoke/node.yaml \
  --project-yaml /tmp/gddp-live-smoke/project.yaml \
  --repo . \
  --receipt-dir /tmp/gddp-live-smoke/receipts2 \
  --semantic-harness pi \
  --semantic-mode live \
  --semantic-provider deepseek \
  --semantic-thinking low
```

CLI summary (JSON):
```json
{
  "verdict": "pass",
  "criteria_confidence": 1,
  "completeness_status": "complete",
  "required_next_action": "Proceed to accept_node (open evidence PR).",
  "criteria_verdict": "pass",
  "lane_status": { "criteria": "completed", "integrity": "not_run" },
  "harness_error": { "criteria": null, "integrity": null },
  "context_coverage": { "criteria": "high", "integrity": "none", "overall": "none" }
}
```

Receipt content highlights:
- `semantic.judgments`: 2 × `judged_pass` @ confidence 1.0
- `semantic.budget_trace.tool_calls`: 23 entries (12 read, 10 bash, 1 submit_verdict)
- `semantic.lane_status`: `completed`
- `semantic.harness_error`: null
- `decision_reasoning`: model's overall reasoning (evidence)
- `required_next_action`: "Proceed to accept_node (open evidence PR)." (decision_engine row 11)

## Constraints honored
- ✅ Did not change the decision_engine matrix.
- ✅ Did not change the VerdictReceipt contract.
- ✅ Did not remove `OpenAICompatibleRunner` / `AnthropicRunner`; both still
  exist in `semantic/agent.py`. pi is an option, not a replacement.
- ✅ `edit` / `write` / `multi_edit` / `bash` are still excluded from pi's
  tool set per the constraint (this node, not the guard).
- ✅ Harness stays model-agnostic across pi providers (deepseek / openai-codex
  OAuth / GLM via zai).
- ✅ Graph truth is human-owned. This node produced evidence only.

## Test suite
```
.venv/bin/python -m pytest -q scripts/runtime/verification
........................................................................ [ 36%]
........................................................................ [ 72%]
.......................................................                  [100%]
199 passed in 1.09s
```

## Git state
- Worktree detached at base commit `3ac3914`. No branch was created.
- `git status --short --branch` is clean (no tracked or untracked changes
  inside the repo).
- `.venv/` is a local-only directory created for this run; not committed.
- Smoke-test node/project YAMLs live under `/tmp/gddp-live-smoke/`; not in
  the repo.

## Files touched
- `decision.md` (this artifact, written at the repo root for the runtime
  pipeline to read).
- `result-summary.md` (this artifact).
- `patch.diff` (empty diff — see artifact).
- `.venv/` (created locally; not committed).
- `/tmp/gddp-live-smoke/*` (created outside the repo for the live test).

## Residual risk
- The live run was performed against a synthetic smoke node that has two
  acceptance criteria (the existence of the harness files), not against the
  actual vault-doctor node mentioned in the node's `why` field. The vault-
  doctor node lives in gddp-config (a separate repo); the harness wiring is
  identical regardless of node content.
- The `auto` / `runner` CLI paths still rely on either a deterministic
  receipt that does not need semantic, or a caller (the bridge) that wires
  a harness externally. This is consistent with the criterion "the default
  path is unchanged" — the orchestrator's signature and call sites are
  backward compatible.
