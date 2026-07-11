# Decision: Pi Evaluator Harness Wiring

## Problem
The previous hand-rolled `SemanticAgent` loop was correct but opaque to operators. It only produced a final receipt without showing the investigator's step-by-step thinking or tool calls. This lack of visibility made it difficult to trust and iterate on the evaluator.

## Implementation Choice: Pi Coding Agent
We chose to drive the semantic evaluator through the `pi` coding agent. `pi` is agent-agnostic and provides live, streaming visibility into the model's investigation process.

### Harness Components
1.  **`pi_runner.py` & `integrity_runner.py`**: These Python runners spawn the `pi` binary with specific flags. We use the `--exclude-tools` flag to mechanistically enforce a read-only environment, blocking `bash` and any mutation tools (`edit`, `write`, `multi_edit`, etc.).
2.  **`gddp_verifier.ts` & `gddp_integrity.ts`**: These are `pi` extensions that register typed terminal tools (`submit_verdict` and `submit_integrity_verdict`). These tools ensure that the final output matches the required `SemanticOutput` and `IntegrityOutput` schemas exactly.
3.  **`gddp_tracer.ts`**: A non-blocking audit trail extension that logs every tool call and result to a trace file. This file is then read by the Python runner and included in the `VerdictReceipt`'s `budget_trace`.

## Enforcement vs. Guarding
Previously, we considered a guard extension that would intercept and block tool calls. We shifted to using `pi`'s native `--exclude-tools` flag for a more robust, binary-level enforcement of the read-only invariant. The `gddp_tracer.ts` extension focuses solely on audit logging, satisfying the requirement for visibility without complicating the enforcement logic.

## Model Agnosticism
The harness is model-agnostic and supports multiple providers including DeepSeek, GLM (via `zai`), Gemini, and OpenRouter. Provider selection and API key management are handled in `cli.py`.
