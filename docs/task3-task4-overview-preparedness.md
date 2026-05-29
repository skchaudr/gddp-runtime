# Task 3 & 4 — Conductor + Semantic Evaluator: Overview & Preparedness

**Date:** 2026-05-26 (post-Wave 1 + Task 5)
**Auditor:** Cline session
**Purpose:** Ground-truth brief for designing Task 3 and Task 4 packets (with GPT-5.5)

---

## 1. Where We Are — Build Progress

| Task | Status | Branch | Commit | Tests |
|------|--------|--------|--------|-------|
| **T1** Structural Validator | ✅ Complete | `feature/t1-structural` | `766f98d` | 23/23 pass |
| **T2** Decision Engine | ✅ Complete | `feature/t2-decision` | `1f66917` | 9/9 pass |
| **T3** Conductor | 🔴 No packet | — | — | — |
| **T4** Semantic Evaluator | 🔴 No packet | — | — | — |
| **T5** Shape Profiles | ✅ Complete | `feature/t5-shape-profiles` (gddp-config) | `c8a23cd` | YAML parse OK |

All on `main` parent commit `1713985`. None merged to main yet.

---

## 2. What Tasks 1 & 2 Actually Delivered

### Task 1 — Structural Validator (3 files, 186 lines of production code)

**`invariant_schema.py`** — Two Pydantic models:
- `InvariantResult(check: str, passed: bool, evidence: str)`
- `StructuralOutput(all_passed: bool, results: List[InvariantResult])`

**`structural.py`** — Five pure functions + runner, ALL keyword-only, ALL side-effect-free:
```python
check_graph_legality(graph: dict) -> InvariantResult
check_acyclic(graph: dict) -> InvariantResult
check_artifacts_exist(declared_artifacts: list[str], present_paths: list[str]) -> InvariantResult
check_files_in_scope(changed_files: list[str], allowed_paths: list[str]) -> InvariantResult
check_acceptance_not_weakened(acceptance_before: list[str], acceptance_after: list[str]) -> InvariantResult

run_structural_validator(
    *, graph: dict, node: dict, changed_files: list[str],
    present_paths: list[str], acceptance_before: list[str], acceptance_after: list[str],
) -> StructuralOutput
```
Key design: `changed_files`, `present_paths`, `acceptance_before/after` are **caller-supplied**. The validator never touches git, filesystem, or DB. Empty inputs → vacuous pass.

**Integration contract** Task 2 depends on: duck-typed `.all_passed: bool` and `.results: list`.

### Task 2 — Decision Engine (3 files, 68 lines of production code)

**`verdict_schema.py`** — One model:
```python
class DecisionOutput(BaseModel):
    verdict: Literal["ACCEPT", "FAIL", "NEEDS_REVIEW", "INVALID", "INCOMPLETE"]
    reason: str               # diagnostic: "preserved", "weakened", "drifted", etc.
    severity: Literal["warning", "blocking"] | None
    matrix_row: int
```

**`decision_engine.py`** — One pure function + 8-row lookup table:
```python
def decide(structural: Any, semantic: Optional[SemanticOutput] = None) -> DecisionOutput
```
- `structural` is **duck-typed** (reads `.all_passed` directly, no isinstance check)
- Imports from `semantic_schema.SemanticOutput` (frozen stub)
- Diagnostic derivation: None→"skipped", `requires_operator_review`→"operator_review_flagged", else→`semantic_fidelity`
- Matrix: first match wins. Row 1 short-circuits on structural failure.
- **Zero I/O. Pure function.**

### What Task 1+2 together give the conductor (Task 3):
```
git diff data → [changed_files, present_paths] ─┐
                                               ├─→ run_structural_validator() → StructuralOutput
node spec from gddp-config ──→ [graph, node]  ─┘                                                          │
                                                                                                          ▼
                                                                                              decide(structural, semantic?)
                                                                                                          │
                                                                                                  DecisionOutput
                                                                                                  ├─ verdict: ACCEPT/FAIL/...
                                                                                                  ├─ reason: diagnostic
                                                                                                  ├─ severity: warning/blocking
                                                                                                  └─ matrix_row: 1..8
```

The conductor is the **wiring** between the left side (data gathering from git + config) and the right side (the two pure functions above). It also decides what to do with the verdict.
---

## 3. Frozen Files — DO NOT MODIFY

These files are committed and have downstream dependencies. Task 3 and Task 4 must **read** them but **never edit** them:

| File | Why frozen |
|------|-----------|
| `verification/__init__.py` | No exports — keeps modules decoupled |
| `verification/semantic_schema.py` | `SemanticOutput` field signatures are the contract between T2 and T4 |
| `verification/invariant_schema.py` | `StructuralOutput.all_passed` is what T2 duck-types against |
| `verification/structural.py` | T1's deliverable — T3 calls it |
| `verification/verdict_schema.py` | T2's deliverable — T3 reads DecisionOutput from it |
| `verification/decision_engine.py` | T2's deliverable — T3 calls `decide()` |

Task 3 creates `review_queue.py` (new file). Task 4 creates `semantic_evaluator.py` (new file) — it imports from `semantic_schema.py` but does not edit it.

---

## 4. Existing Runtime Files Task 3 Will Touch

### `results_store.py` — The persistence layer

**Actual `write_result()` signature:**
```python
def write_result(
    result_id: str, job_id: str, executor: str, outcome: str, status: str,
    received_at: str = None, execution_duration_seconds: int = None,
    changed_files=None, patch_path=None, summary_path=None, logs_path=None,
    acceptance_check=None, risks=None, followup_candidates=None, github_action=None,
)
```

**Design decision needed:** How to store verification verdicts. Options:
- **(a)** Extend `write_result()` with verdict-specific fields (e.g. `verdict`, `verdict_reason`, `structural_passed`, `semantic_fidelity`) — requires schema migration
- **(b)** Write verdict data into existing `github_action` JSON blob — no migration, but hacky
- **(c)** Create a separate `verdicts` table — cleanest, but new table
- **(d)** Use `acceptance_check` and `risks` fields (already exist, underused) — minimal

### `return_router.py` — The entry point for merged PRs

- `handle_merged_pr(event)` is called when a PR merges
- It writes a `write_result()` with `status="needs_review"` and calls `_mark_job_awaiting_review()`
- **Task 3's conductor needs to be triggered after this** — the return_router produces the review receipt, the conductor runs verification on it
- Already has an ADR comment (lines 8–15): "write_verdict -> graph_updater creates a reviewable PR-proposal, it does not mutate the graph directly"

### `graph_updater.py` — The evidence PR system

- `open_evidence_pr(node_id, project_id, source_pr_number, source_pr_url, evidence, config_path)` → proposes graph mutation
- Already implemented and tested (7 tests)
- When conductor gets verdict=ACCEPT, it calls this to propose advancing the graph

### `review_queue.py` — **Does not exist yet.** Task 3 creates it.

No design exists beyond the plan's wire diagram. This needs to be designed in the Task 3 packet. Purpose: track jobs awaiting verification review.

### `decision_loop/context_reader.py` — ⚠️ Known Bug

Queries a `return_results` table that doesn't exist (should query `results`). **Task 3 should NOT depend on `decision_loop/`** — it's a separate module. Document this boundary explicitly in the packet.
---

## 5. Design Decisions Still Open for Task 3

These are the questions the Task 3 packet must answer:

### 5.1 — Trigger Flow
The return_router already handles merged PRs and creates review receipts. The conductor needs to:
1. Discover jobs in `awaiting_review` state
2. Gather git diff data for the PR
3. Load the node spec from gddp-config
4. Call `run_structural_validator()` → `decide()` → get `DecisionOutput`
5. Store the verdict somewhere
6. If verdict=ACCEPT, call `graph_updater.open_evidence_pr()`

**Question:** Is the conductor triggered synchronously inside `handle_merged_pr()` (extend return_router), or is it an independent polling/queue loop?

### 5.2 — Git Data Gathering
`run_structural_validator()` needs `changed_files`, `present_paths`, `acceptance_before`, `acceptance_after`:
- `changed_files` → `git diff --name-only base...head`
- `present_paths` → files in the PR
- `acceptance_before` → node spec in gddp-config YAML
- `acceptance_after` → acceptance criteria from the PR/executor output

### 5.3 — Verdict Persistence
See options in section 4 (4a–4d). The `write_result()` signature is fixed; verdict data needs a home.

### 5.4 — `review_queue.py` Design
No spec exists. Needs: discover awaiting_review jobs, track verification state, prevent re-processing.

### 5.5 — Pi Harness Packet
`~/.pi/harness/packets/review-node.yaml` doesn't exist (32 other packets do). May or may not be in scope.

### 5.6 — `init_db.py`
Does not exist. DB init is in `results_store.init_db()`.

---

## 6. Design Decisions for Task 4

### 6.1 — File Structure
New file `semantic_evaluator.py` imports `SemanticOutput` from `semantic_schema.py` and defines an `evaluate()` function. Keeps `semantic_schema.py` frozen.

### 6.2 — LLM Client Dependency
Task 4 will need an LLM client (openai, anthropic, or similar). Forces `requirements.txt` creation.

### 6.3 — Prompt Design
Evaluator needs: node spec (acceptance criteria), changed files/diff, prompt asking LLM to judge semantic fidelity, JSON extraction, mapping to `SemanticOutput` fields.

### 6.4 — Integration with Conductor
Conductor calls: `structural_output = run_structural_validator(...)` then `semantic_output = evaluate(...)` then `verdict = decide(structural_output, semantic_output)`. Task 4 defines `evaluate()`. Task 3 wires it in.

---

## 7. What the Task 3 Packet Must Specify

1. **Files to create:** `review_queue.py` (and possibly `conductor.py`)
2. **Files to modify:** `return_router.py` (trigger point), possibly `results_store.py` (verdict storage)
3. **Files to read only:** structural.py, decision_engine.py, graph_updater.py, semantic_schema.py
4. **Files to NOT touch:** decision_loop/, __init__.py, any file outside create/modify list
5. **Conductor function signature** — inputs and outputs
6. **Verdict storage design** — which option (4a–4d) and schema
7. **Trigger flow** — synchronous in return_router vs independent loop
8. **Git data gathering approach** — how to get changed_files, present_paths, acceptance criteria
9. **review_queue design** — data model, discovery, dedup
10. **Tests** — unit tests for conductor logic, mock git/config calls

---

## 8. What the Task 4 Packet Must Specify

1. **Files to create:** `semantic_evaluator.py`, `test_semantic_evaluator.py`
2. **`evaluate()` function signature** — what inputs, returns `SemanticOutput`
3. **LLM client choice** — which library, API key handling
4. **Prompt template** — actual prompt text or template structure
5. **JSON extraction** — how to parse LLM response into `SemanticOutput`
6. **Error handling** — LLM returns garbage, timeouts, etc.
7. **Test strategy** — mock LLM calls, test JSON extraction, test prompt rendering
8. **`requirements.txt`** — what to add
9. **Frozen contract reminder** — `semantic_schema.py` field names and literal types MUST NOT change

---

## 9. Current File Tree (verification module, post-T1+T2)

```
scripts/runtime/verification/
├── __init__.py                    # frozen — no exports
├── semantic_schema.py             # frozen — SemanticOutput stub (Task 4 target)
├── invariant_schema.py            # T1 — InvariantResult + StructuralOutput
├── structural.py                  # T1 — 5 checks + runner
├── test_structural.py             # T1 — 23 tests
├── verdict_schema.py              # T2 — DecisionOutput
├── decision_engine.py             # T2 — decide() + 8-row matrix
└── test_decision_engine.py        # T2 — 9 tests

# Task 3 will create: review_queue.py (and possibly conductor.py)
# Task 4 will create: semantic_evaluator.py + test_semantic_evaluator.py
```

---

## 10. Full `semantic_schema.py` (frozen contract for T2 and T4)

```python
class CriterionVerdict(BaseModel):
    criterion: str
    satisfied: bool
    confidence: float          # 0.0 – 1.0
    reasoning: str

class SemanticOutput(BaseModel):
    semantic_fidelity: Literal["preserved", "weakened", "drifted", "contradicted", "insufficient"]
    risk_level: Literal["low", "medium", "high"]
    drift_type: Literal["none", "acceptance_weakening", "responsibility_loss", "shape_change"]
    requires_operator_review: bool
    criteria_verdicts: List[CriterionVerdict] = []
    evidence: dict = {}
    reasoning_summary: str = ""
```

---

## 11. Key Risk Reminders

- **Task 3 is where scope-creep burned the last session.** The packet must be ironclad on what NOT to touch.
- **`decision_loop/` is a trap.** It sounds related but is a separate module. Do not import from or modify it.
- **`results_store.write_result()` has a fixed signature.** Don't try to call it with nonexistent params.
- **`init_db.py` does not exist.** DB init is in `results_store.init_db()`.
- **`review_queue.py` has zero design.** The packet must specify its data model and API.
- **The Pi harness packet `review-node.yaml` may or may not be in scope.** Decide and state explicitly.