# Wave 1 · Task 1 — Structural Validator (task packet)

**Intended executor:** Cline driven by GLM5-Turbo. This packet is deliberately explicit and
tightly scoped — not a comment on the model, but because an under-specified packet wandering into
the wrong module is exactly what burned the last session.
**Repo:** `~/repos/gddp-runtime` · **Branch:** `feature/t1-structural` · **Venv:** Use the Python environment where the current runtime test suite passes.

> Setup (run once; `main` is local-only right now, so skip any `git pull`):
> ```bash
> cd ~/repos/gddp-runtime
> git worktree add ../gddp-runtime-t1 -b feature/t1-structural main
> cd ../gddp-runtime-t1  # Python environment already configured with passing test suite
> ```

## Your job, in one sentence
Implement the deterministic **Structural Validator** for the verification module: five pure check
functions plus a runner, each returning structured evidence, with tests. Nothing else.

## Create ONLY these files
- `scripts/runtime/verification/invariant_schema.py`
- `scripts/runtime/verification/structural.py`
- `scripts/runtime/verification/test_structural.py`

## DO NOT modify or create anything else
Read-for-context-only, never edit:
- `scripts/runtime/verification/__init__.py` (frozen) and `semantic_schema.py` (frozen contract)
- **`scripts/runtime/decision_loop/` — this is NOT your module.** It is a separate, pre-existing
  job-dispatch runtime. Do not open it, import it, or "fix" it. (A prior run wrecked a whole
  session by confusing it with verification work. Don't.)
- `return_router.py`, `init_db.py`, `results_store.py`, `heartbeat/`, `openclaw/`, the `gddp-config` repo
- `verdict_schema.py`, `decision_engine.py` — Task 2 owns these, building in parallel.

If you believe you need to touch a file not in the create list, **STOP and report it** — do not do it.

## Background (read once; do not expand scope from it)
The verification module judges whether a merged PR for a graph node is acceptable. It has
independent layers, each emitting structured evidence; a separate decision engine (Task 2, parallel,
not your job) consumes that evidence. You build the **Structural** layer: pure, deterministic, no
LLM, no network, no filesystem, no git. Ref: `gdd-architectura-review.md` → "Each Verification
Layer Is Independent", layer table (~line 163): Structural input is `git diff --name-only` + node
constraints + artifact paths; output is `[{check, pass/fail, evidence}]`.

## Data models — implement EXACTLY (`invariant_schema.py`)
```python
from typing import List
from pydantic import BaseModel

class InvariantResult(BaseModel):
    check: str          # stable check name, e.g. "graph_acyclic"
    passed: bool
    evidence: str       # human-readable explanation of the pass/fail

class StructuralOutput(BaseModel):
    all_passed: bool            # True iff every result.passed is True
    results: List[InvariantResult]
```
**FROZEN INTEGRATION CONTRACT** (Task 2 depends on this exact shape): a structural result exposes
exactly `.all_passed: bool` and `.results: list[InvariantResult]`. Do not rename either.

## The five checks (`structural.py`) — pure functions, each returns `InvariantResult`
Each takes plain Python inputs so tests construct them inline — **no DB, no git, no filesystem.**

1. `check_graph_legality(graph: dict) -> InvariantResult`
   `graph = {"nodes": {node_id: {... "depends_on": [...]}}}`. Every `depends_on` entry must
   reference an existing node id. Fail (listing the bad refs) if not. `check="graph_legality"`.
2. `check_acyclic(graph: dict) -> InvariantResult`
   The `depends_on` edges must form a DAG. Detect cycles (DFS or topo sort); on failure put the
   cycle path in `evidence`. `check="graph_acyclic"`.
3. `check_artifacts_exist(declared_artifacts: list[str], present_paths: list[str]) -> InvariantResult`
   Every declared artifact path must appear in `present_paths` (the paths that exist / are in the
   PR). Fail listing the missing ones. **Pure** — caller supplies `present_paths`; do not touch the
   filesystem. `check="artifacts_exist"`.
4. `check_files_in_scope(changed_files: list[str], allowed_paths: list[str]) -> InvariantResult`
   Every changed file must sit under at least one `allowed_paths` prefix. Fail listing out-of-scope
   files. `check="files_in_scope"`.
5. `check_acceptance_not_weakened(acceptance_before: list[str], acceptance_after: list[str]) -> InvariantResult`
   No criterion present in `_before` may be absent from `_after` (criteria may be added, never
   dropped/weakened). Fail listing dropped criteria. `check="acceptance_not_weakened"`.

## The runner (`structural.py`)
```python
def run_structural_validator(
    *, graph: dict, node: dict, changed_files: list[str],
    present_paths: list[str], acceptance_before: list[str], acceptance_after: list[str],
) -> StructuralOutput
```
- `node` is the node under review (e.g. `graph["nodes"][node_id]`); use `node.get("artifacts", [])`
  for declared artifacts and `node.get("allowed_paths", [])` for scope.
- Run all five checks, collect `List[InvariantResult]`, set `all_passed = all(r.passed for r in results)`.
- A check with empty/inapplicable inputs simply passes vacuously.
- **Provenance:** `changed_files`, `present_paths`, and `acceptance_before/after` are supplied BY
  THE CALLER (the Task 3 conductor, derived from `git diff` + the node spec). This validator never
  computes them — no filesystem, no git, no network.
- Keyword-only args, plain inputs — testability without mocks is the whole point.

## A reference input that passes all five checks (your happy-path fixture)
Use this verbatim as the "valid graph" test fixture; the negative tests mutate one field of it.
```python
graph = {
    "nodes": {
        "spec":   {"depends_on": [],       "artifacts": ["docs/spec.md"],  "allowed_paths": ["docs/"]},
        "parser": {"depends_on": ["spec"], "artifacts": ["src/parser.py"], "allowed_paths": ["src/"]},
    }
}
node = graph["nodes"]["parser"]

run_structural_validator(
    graph=graph,
    node=node,
    changed_files=["src/parser.py"],            # under allowed_paths ["src/"]      → files_in_scope ✓
    present_paths=["docs/spec.md", "src/parser.py"],  # declared artifact present   → artifacts_exist ✓
    acceptance_before=["parses valid input"],
    acceptance_after=["parses valid input", "rejects malformed input"],  # added, not dropped ✓
)  # -> StructuralOutput(all_passed=True, results=[...5 passing...])
```

## Tests (`test_structural.py`) — pytest, must cover EXACTLY these, all passing
- valid graph → `all_passed is True`
- cyclic DAG → `check_acyclic` fails, `all_passed is False`
- missing artifact → `check_artifacts_exist` fails
- out-of-scope file → `check_files_in_scope` fails
- acceptance weakening → `check_acceptance_not_weakened` fails

A couple of extra happy-path unit tests per function are welcome. **No mocking.**

## Termination contract — stop only when ALL are true
- The 3 files exist; `git diff --name-only` shows only those 3 files (nothing out of scope).
- `pytest scripts/runtime/verification/test_structural.py` passes.
- No new dependencies (pydantic is already present); if you added any, record them in the repo's dep file.
- `git diff` reviewed; branch `feature/t1-structural` committed.
- Final summary: files changed, tests run + result, any ambiguity you hit.
