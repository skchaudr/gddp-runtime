# E3 spec — command_proof probe for the deterministic layer

## Goal
A node acceptance criterion may declare an explicit command. When present, the
deterministic layer EXECUTES it and judges from the exit code — no model
involved. This closes the gap where `suite-green`-class criteria sit at
`no_probe`/indeterminate and the verdict depends on the semantic model
choosing to run the command.

## Config contract (gddp-config, human-authored truth)
Acceptance entries gain an OPTIONAL `command` key:

```yaml
acceptance:
  - id: suite-green
    criterion: .venv/bin/python -m pytest -q scripts/runtime/verification passes
    command: .venv/bin/python -m pytest -q scripts/runtime/verification
```

Commands come only from human-authored node YAML. Never derive commands from
criterion prose, model output, or receipts.

## Runtime behavior (gddp-runtime)
In `scripts/runtime/verification/deterministic/probes.py` `evaluate_criterion`:
- If the criterion dict has a non-empty `command` string, run it FIRST,
  before any keyword/probe logic:
  - `subprocess.run(command, shell=True, cwd=repo, capture_output=True,
    text=True, timeout=GDDP_COMMAND_PROOF_TIMEOUT (env, default 300))`
  - exit 0  -> status "pass", confidence 0.95, method "command_proof"
  - exit !=0 -> status "fail", confidence 0.9, method "command_proof"
  - timeout / OSError -> status "indeterminate", confidence 0.3,
    method "command_proof_error"
- Evidence: `["$ <command>", "exit <code>", <last ~1500 chars of combined
  stdout+stderr>]`. Reasoning: one sentence stating what ran and the result.
- The criterion dict reaching evaluate_criterion comes from node YAML loading —
  verify the `command` key survives the load path (check cli.py `_load_yaml` →
  orchestrator → deterministic input shape; adjust plumbing if the acceptance
  entries are reduced to strings anywhere).

## Constraints
- Do NOT touch decision_engine.py, schemas.py receipt contract, or semantic/.
- Match existing code style in probes.py.
- Failing command output is evidence, not an exception — never raise out of
  evaluate_criterion.

## Tests (deterministic/test_deterministic.py style)
1. command exits 0 -> pass@0.95, method command_proof
2. command exits 1 -> fail@0.9
3. command times out -> indeterminate@0.3, method command_proof_error
4. no `command` key -> existing behavior untouched (regression)
5. evidence includes command string and exit code

## Definition of done
`.venv/bin/python -m pytest -q scripts/` fully green (137 existing tests must
still pass). Do not commit — leave changes in the working tree for review.
