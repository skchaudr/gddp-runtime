# Wave 1 · Task 2 — Decision rules engine (task packet)

**Intended executor:** Cline driven by GLM5-Turbo. This packet is deliberately explicit and
tightly scoped — not a comment on the model, but because an under-specified packet wandering into
the wrong module is exactly what burned the last session.
**Repo:** `~/repos/gddp-runtime` · **Branch:** `feature/t2-decision` · **Venv:** Use the Python environment where the current runtime test suite passes.

> Setup (run once; `main` is local-only right now, so skip any `git pull`):
> ```bash
> cd ~/repos/gddp-runtime
> git worktree add ../gddp-runtime-t2 -b feature/t2-decision main
> cd ../gddp-runtime-t2  # Python environment already configured with passing test suite
> ```

## Your job, in one sentence
Implement a **pure decision function** that maps structural + (optional) semantic evidence to a
verdict, using an explicit **8-row lookup table**. Nothing else.

## Create ONLY these files
- `scripts/runtime/verification/verdict_schema.py`
- `scripts/runtime/verification/decision_engine.py`
- `scripts/runtime/verification/test_decision_engine.py`

## DO NOT modify or create anything else
- `__init__.py` (frozen). `semantic_schema.py` (frozen — **import** from it, never edit it).
- **`structural.py` / `invariant_schema.py` / `test_structural.py` — Task 1 is building these IN
  PARALLEL.** Do not create, read, or import them. The integration contract below keeps you decoupled.
- **`scripts/runtime/decision_loop/` — NOT your module, and the name is a trap.** The existing
  `decision_loop/` is an unrelated job-dispatch *runtime*. You are building a brand-new pure
  function in `verification/decision_engine.py`. Same words, totally different code. **Do not open
  `decision_loop/`.** (A prior run confused exactly these two and burned a whole session — that is
  the specific mistake this line exists to stop.)
- `return_router.py`, `init_db.py`, `results_store.py`, `gddp-config`.

If you believe you need a file outside the create list, **STOP and report it.**

## Imports & integration contract (this is how you avoid depending on Task 1)
- Import the semantic contract: `from .semantic_schema import SemanticOutput`
- **Do NOT import `structural.py`** (built in parallel — it may not exist when you run). Define only
  `DecisionOutput` in `verdict_schema.py`:
```python
from typing import Literal
from pydantic import BaseModel

class DecisionOutput(BaseModel):
    verdict: Literal["ACCEPT", "FAIL", "NEEDS_REVIEW", "INVALID", "INCOMPLETE"]
    reason: str               # diagnostic: "preserved", "weakened", "drifted", etc.
    severity: Literal["warning", "blocking"] | None   # None only for ACCEPT
    matrix_row: int           # which rule fired, for auditability
```

Two-layer design:
- **verdict** is the routing layer — small, stable, drives what the runtime/operator does next.
- **reason** preserves the diagnostic layer — the `semantic_fidelity` value that produced this verdict.
- **severity** tags urgency: `"warning"` = needs human attention but may not block; `"blocking"` = cannot proceed.
- `matrix_row` is the ordinal of the rule that fired (1..N).
- The `structural` argument is **duck-typed** — do not define or import a type for it. It is any
  object exposing `.all_passed: bool` (and `.results: list`). Read `structural.all_passed` directly.
  **Do NOT** write `isinstance(structural, ...)` or any Protocol/`@runtime_checkable` check — just
  read the attribute.

## The function (`decision_engine.py`)
```python
from typing import Any, Optional
from .semantic_schema import SemanticOutput
from .verdict_schema import DecisionOutput

def decide(structural: Any, semantic: Optional[SemanticOutput] = None) -> DecisionOutput:
    """`structural` is the StructuralOutput produced by Task 1's run_structural_validator —
    any object with a boolean `.all_passed`. Typed `Any` on purpose: Task 1 builds in parallel,
    so we do not import its module. Read `structural.all_passed`; do not isinstance-check it."""
```
**PURE.** No I/O, no LLM, no randomness, no `datetime`, no global state. Same inputs → same output,
always. Implement the matrix as an explicit **lookup table**, not nested `if/else` chains.

### Step 1 — derive `diagnostic` (the semantic evidence, preserved as-is)
- `semantic is None` → `"skipped"`
- `semantic.requires_operator_review is True` → `"operator_review_flagged"`
- otherwise → `semantic.semantic_fidelity` directly: `"preserved"`, `"weakened"`, `"drifted"`, `"contradicted"`, `"insufficient"`

No bundling. Each literal is preserved as the diagnostic.

### Step 2 — the decision matrix (routing layer: verdict + severity)
| row | `structural.all_passed` | diagnostic                  | verdict       | severity   |
|-----|-------------------------|-----------------------------|---------------|------------|
| 1   | `False`                 | (any)                       | `FAIL`        | `blocking` |
| 2   | `True`                  | `skipped`                   | `ACCEPT`      | `None`     |
| 3   | `True`                  | `preserved`                 | `ACCEPT`      | `None`     |
| 4   | `True`                  | `weakened`                  | `NEEDS_REVIEW`| `warning`  |
| 5   | `True`                  | `drifted`                   | `NEEDS_REVIEW`| `warning`  |
| 6   | `True`                  | `contradicted`              | `INVALID`     | `blocking` |
| 7   | `True`                  | `insufficient`              | `INCOMPLETE`  | `warning`  |
| 8   | `True`                  | `operator_review_flagged`   | `NEEDS_REVIEW`| `warning`  |

Row 1 short-circuits: if `structural.all_passed` is `False`, verdict is `FAIL`/`blocking` regardless
of semantic. `reason` carries the diagnostic value (so the operator still knows *what* the semantic
layer found, even on a structural fail). Set `matrix_row` to the row that fired.

Routing contracts:
- `ACCEPT` — the node can proceed. `severity=None`.
- `FAIL` — structural invariants broken. `severity=blocking`.
- `NEEDS_REVIEW` — semantic concerns present but may be benign; operator/judge decides.
- `INVALID` — the work contradicts its contract. `severity=blocking`.
- `INCOMPLETE` — evidence insufficient to judge. `severity=warning`.

*(Reference: `gdd-architectura-review.md` lines 173–188 — any deterministic failure → FAIL;
everything clean → ACCEPT; semantic uncertainty/deviation/insufficiency or explicit operator-review
flag → ESCALATE to a human. The LLM evaluator is "a witness, not a judge" — it testifies, the
decision engine judges. The engine never reasons or generates; it only applies these rules.)*

## Tests (`test_decision_engine.py`) — pytest, ONE test per matrix row (8 total), all passing
- Build a tiny fake structural object with `types.SimpleNamespace(all_passed=..., results=[])` —
  you do **not** need Task 1's real class.
- For rows 3–8, build real `SemanticOutput` instances from `semantic_schema` (set
  `requires_operator_review`, `semantic_fidelity`, etc. to hit each diagnostic); row 2 uses
  `semantic=None`; row 1 uses `all_passed=False`.
- Assert `verdict`, `reason`, `severity`, and `matrix_row` for each row. **No mocking.**

## Termination contract — stop only when ALL are true
- The 3 files exist; `git diff --name-only` shows only those 3 (nothing out of scope, and you did
  not create `structural.py`).
- `pytest scripts/runtime/verification/test_decision_engine.py` passes.
- No new dependencies; record any you add.
- `git diff` reviewed; branch `feature/t2-decision` committed.
- Final summary: files changed, tests run + result, any ambiguity you hit.
