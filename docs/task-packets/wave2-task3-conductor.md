# Task 3 — Conductor (Wave 2)

**Branch:** `feature/t3-conductor` from `main` (after T1+T2 merge)
**Parent commit:** merge of T1 (`766f98d`) + T2 (`1f66917`)
**Status:** Ready to build

---

## Purpose

The conductor wires the verification module into the live runtime loop. It discovers jobs awaiting review, gathers the data the structural validator needs, runs the verification pipeline, stores the verdict, and — when the verdict is ACCEPT — proposes graph advancement via an evidence PR.

This is the **only task that bridges** `runtime/` and `verification/`. Everything else in the verification module is a pure function. The conductor is the impure orchestrator that calls them with real data.

---

## What the Conductor Does

```
 1. Poll for jobs in awaiting_review state
 2. Load the review receipt from the results table
 3. Load the node spec from gddp-config YAML
 4. Gather changed_files from the PR (via gh CLI or stored data)
 5. Build the inputs for run_structural_validator()
 6. Call run_structural_validator() -> StructuralOutput
 7. Call decide(structural, semantic=None) -> DecisionOutput
 8. Persist the verdict
 9. If verdict=ACCEPT -> call graph_updater.open_evidence_pr()
10. Return structured result
```

In this wave, semantic is always None (Task 4 will plug in later).

---

## Files to Create

| File | Purpose |
|------|----------|
| `scripts/runtime/review_queue.py` | Discover, claim, and complete verification jobs |
| `scripts/runtime/conductor.py` | Main verification orchestration |
| `scripts/runtime/test_review_queue.py` | Queue unit tests |
| `scripts/runtime/test_conductor.py` | Conductor unit tests |

## Files to Read Only (FROZEN — do not modify)

| File | What you import from it |
|------|------------------------|
| `scripts/runtime/verification/structural.py` | `run_structural_validator()` |
| `scripts/runtime/verification/invariant_schema.py` | `StructuralOutput`, `InvariantResult` (implicit via structural) |
| `scripts/runtime/verification/decision_engine.py` | `decide()` |
| `scripts/runtime/verification/verdict_schema.py` | `DecisionOutput` |
| `scripts/runtime/verification/semantic_schema.py` | `SemanticOutput` (imported but passed as None) |
| `scripts/runtime/verification/__init__.py` | No imports from here |

## Files to Call (existing, do not modify)

| File | What you call |
|------|--------------|
| `scripts/runtime/graph_updater.py` | `open_evidence_pr()` when verdict=ACCEPT |
| `scripts/runtime/results_store.py` | `write_result()` to persist verdict data |

## Files NOT to Touch

| File | Why |
|------|-----|
| `scripts/runtime/return_router.py` | Its job ends at receipt creation. Conductor picks up after. |
| `scripts/runtime/decision_loop/` | Separate module with known bugs. Do not import from it. |
| `scripts/runtime/heartbeat/` | Forward path. Not involved in verification. |
| `scripts/runtime/replay.py` | Replay is independent. |
| `scripts/runtime/verification/__init__.py` | Frozen. |
| `scripts/init_db.py` | DB init is in `results_store.init_db()`. |
| Any file in `gddp-config/` | Task 3 reads gddp-config but never writes to it (graph_updater handles writes). |

---

## API Contracts — Exact Signatures

### `run_structural_validator()` (from structural.py — READ ONLY)

```python
def run_structural_validator(
    *,                                          # all keyword-only
    graph: dict,                                # project graph: {"nodes": {node_id: {...}}}
    node: dict,                                 # single node spec with "artifacts", "allowed_paths"
    changed_files: list[str],                   # files changed in the PR
    present_paths: list[str],                   # files present in the working tree
    acceptance_before: list[str],               # acceptance criteria from gddp-config
    acceptance_after: list[str],                # acceptance criteria from the PR / executor
) -> StructuralOutput:                          # .all_passed: bool, .results: list
```

### `decide()` (from decision_engine.py — READ ONLY)

```python
def decide(
    structural: Any,                            # duck-types: reads .all_passed
    semantic: Optional[SemanticOutput] = None,  # None in this wave
) -> DecisionOutput:                            # .verdict, .reason, .severity, .matrix_row
```

### `DecisionOutput` (from verdict_schema.py — READ ONLY)

```python
class DecisionOutput(BaseModel):
    verdict: Literal["ACCEPT", "FAIL", "NEEDS_REVIEW", "INVALID", "INCOMPLETE"]
    reason: str
    severity: Literal["warning", "blocking"] | None
    matrix_row: int
```

### `open_evidence_pr()` (from graph_updater.py — CALL ONLY)

```python
def open_evidence_pr(
    node_id: str,
    project_id: str,
    source_pr_number: int,
    source_pr_url: str,
    evidence: Dict[str, Any],
    config_path: Optional[str] = None,
) -> Dict[str, Any]:    # {"ok": bool, "evidence_pr_url": str, ...} or {"ok": False, "reason": str}
```

### `write_result()` (from results_store.py — CALL ONLY)

```python
def write_result(
    result_id: str,
    job_id: str,
    executor: str,
    outcome: str,
    status: str,
    received_at: str = None,
    execution_duration_seconds: int = None,
    changed_files=None,           # JSON-serializable
    patch_path: str = None,
    summary_path: str = None,
    logs_path: str = None,
    acceptance_check=None,        # JSON-serializable <- VERDICT GOES HERE
    risks=None,                   # JSON-serializable <- STRUCTURAL RESULTS GO HERE
    followup_candidates=None,
    github_action=None,
)
```

---

## New File Specifications

### `review_queue.py`

Three functions, all SQLite-backed, single responsibility each.

```python
def poll_awaiting_review() -> list[dict]:
    """
    Return all result rows with status='needs_review' that have not yet been
    claimed for verification.

    Returns list of dicts (from sqlite3.Row) with at minimum:
      result_id, job_id, status, github_action
    """

def claim_for_verification(result_id: str) -> bool:
    """
    Atomically mark a result as being verified.

    Sets status from 'needs_review' to 'verifying'.
    Returns True if the claim succeeded (row was in needs_review state).
    Returns False if already claimed or not found.

    Prevents concurrent verification of the same result.
    """

def complete_verification(
    result_id: str,
    verdict: str,        # from DecisionOutput.verdict
    reason: str,         # from DecisionOutput.reason
    severity: str | None,# from DecisionOutput.severity
    matrix_row: int,     # from DecisionOutput.matrix_row
    structural_passed: bool,
    structural_results: list[dict],  # serialized InvariantResult list
) -> None:
    """
    Write the verdict into the results row and update status.

    Uses write_result() to update the existing row:
    - acceptance_check = verdict JSON blob
    - risks = structural results JSON
    - status = verdict-appropriate final state

    Status mapping:
      ACCEPT        -> 'verified_accept'
      FAIL          -> 'verified_fail'
      NEEDS_REVIEW  -> 'escalated'
      INVALID       -> 'verified_fail'
      INCOMPLETE    -> 'verified_incomplete'
    """
```

### `conductor.py`

One main entry point, plus helpers for data gathering.

```python
def run_verification(result_id: str, config_path: str | None = None) -> dict:
    """
    Main conductor entry point. Run verification for one result.

    Steps:
      1. Load receipt from results table
      2. Claim the result for verification (claim_for_verification)
      3. Parse github_action JSON for repo_name, pr_number, node_id, merged_pr_url
      4. Load node spec from gddp-config YAML
      5. Gather changed_files from PR (via gh CLI: gh pr diff --name-only)
      6. Build acceptance_before from gddp-config node spec
      7. Build acceptance_after from PR body or executor output
      8. Call run_structural_validator(...)
      9. Call decide(structural, semantic=None)
     10. Call complete_verification(result_id, verdict, ...)
     11. If verdict == "ACCEPT":
           call graph_updater.open_evidence_pr(...)
     12. Return {"ok": True, "verdict": ..., "result_id": result_id}

    Error handling:
      - If any step fails, log the error and return {"ok": False, "error": str}
      - Never raise - always return a dict
    """

def load_node_spec(project_id: str, node_id: str, config_path: str) -> dict:
    """
    Read the node YAML from gddp-config.

    Looks for: config_path / graphs / project_id / nodes / node_id.yaml
    Falls back to inline node spec in project.yaml if node file doesn't exist.

    Returns dict with at minimum:
      id, acceptance (list[str]), artifacts (list[str]), allowed_paths (list[str])
    """

def gather_changed_files(repo_name: str, pr_number: str) -> list[str]:
    """
    Get the list of files changed in a PR via gh CLI.

    Runs: gh pr diff --name-only --repo repo_name pr_number

    Returns list of file paths. Returns [] on failure.
    """
```

---

## Verdict Storage Design

**Decision: Use existing `acceptance_check` and `risks` fields in `write_result()`.** No schema migration. No new table.

When `complete_verification()` calls `write_result()`:

```python
write_result(
    result_id=result_id,
    job_id=existing["job_id"],
    executor=existing["executor"],
    outcome=existing["outcome"],
    status=verdict_status,                    # mapped from verdict
    acceptance_check={
        "verdict": verdict,                    # "ACCEPT", "FAIL", etc.
        "reason": reason,                      # diagnostic string
        "severity": severity,                  # "warning", "blocking", None
        "matrix_row": matrix_row,              # 1-8
        "structural_passed": structural_passed,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    },
    risks=[r.model_dump() for r in structural_results],  # serialized InvariantResults
)
```

This reuses the existing upsert behavior of `write_result()` (it checks for existing `result_id` and updates in place).

---

## gddp-config Node YAML Shape

The conductor reads node specs from gddp-config. The expected shape:

```yaml
# graphs/<project-id>/nodes/<node-id>.yaml
id: structural-validator
title: Structural Validator
status: complete
acceptance:
  - Pydantic models exist exactly as specified
  - Five check functions return InvariantResult
  - run_structural_validator returns StructuralOutput
  - Tests cover valid graph, cyclic DAG, missing artifact, out-of-scope file, and acceptance weakening
artifacts:
  - scripts/runtime/verification/structural.py
  - scripts/runtime/verification/invariant_schema.py
allowed_paths:
  - scripts/runtime/verification/
```

The conductor extracts:
- `acceptance` -> `acceptance_before` for the structural validator
- `artifacts` -> used for `declared_artifacts` (passed via `node` dict)
- `allowed_paths` -> used for scope checking (passed via `node` dict)

---

## Test Specification

### `test_review_queue.py` — Queue Tests

| Test | What it proves |
|------|---------------|
| `test_poll_returns_needs_review` | Only rows with status='needs_review' are returned |
| `test_poll_excludes_other_statuses` | Verified/escalated rows are excluded |
| `test_claim_succeeds_for_needs_review` | Claiming a needs_review row succeeds |
| `test_claim_fails_for_wrong_status` | Claiming a non-needs_review row fails |
| `test_claim_prevents_double_claim` | Second claim on same row fails |
| `test_complete_writes_verdict_to_acceptance_check` | Verdict JSON appears in acceptance_check field |
| `test_complete_updates_status_to_verified_accept` | ACCEPT -> status='verified_accept' |
| `test_complete_updates_status_to_verified_fail` | FAIL -> status='verified_fail' |
| `test_complete_updates_status_to_escalated` | NEEDS_REVIEW -> status='escalated' |
| `test_complete_writes_structural_results_to_risks` | Structural details appear in risks field |

### `test_conductor.py` — Conductor Tests

| Test | What it proves |
|------|---------------|
| `test_run_verification_accept_flow` | ACCEPT -> verdict stored, graph_updater.open_evidence_pr called |
| `test_run_verification_fail_flow` | FAIL -> verdict stored, NO graph mutation |
| `test_run_verification_needs_review_flow` | NEEDS_REVIEW -> verdict stored, status='escalated' |
| `test_run_verification_invalid_flow` | INVALID -> verdict stored, NO graph mutation |
| `test_run_verification_incomplete_flow` | INCOMPLETE -> verdict stored, status='verified_incomplete' |
| `test_run_verification_missing_config` | gddp-config not found -> returns ok=False with error |
| `test_run_verification_missing_pr_data` | No github_action data -> returns ok=False with error |
| `test_load_node_spec_from_yaml` | Node YAML file is parsed correctly |
| `test_load_node_spec_missing_returns_empty` | Missing node file -> returns empty dict (graceful) |
| `test_gather_changed_files_success` | gh CLI returns file list correctly |
| `test_gather_changed_files_failure_returns_empty` | gh CLI fails -> returns empty list (doesn't crash) |

**Test strategy:**
- All conductor tests mock: `gh` CLI calls, gddp-config file reads, `graph_updater.open_evidence_pr()`
- All queue tests use in-memory SQLite (no mocking needed — real DB operations)
- No LLM calls to mock (semantic is None in this wave)

---

## Scope Discipline

### DO:
- Create exactly 4 new files (2 production, 2 test)
- Import from verification module (structural.py, decision_engine.py, verdict_schema.py)
- Call graph_updater.open_evidence_pr() when verdict is ACCEPT
- Call results_store.write_result() to persist verdicts
- Read gddp-config YAML files (graph, node specs)

### DO NOT:
- Modify any file in `verification/` (frozen)
- Modify `return_router.py` (its job is done)
- Modify `results_store.py` (use its existing API as-is)
- Modify `graph_updater.py` (call it, don't change it)
- Import from or modify `decision_loop/` (separate module)
- Import from or modify `heartbeat/` (forward path only)
- Create Pi harness packets (out of scope for this task)
- Add new dependencies (all needed libs are available: sqlite3, json, subprocess, pydantic, yaml)
- Implement semantic evaluation (that's Task 4)

### STOP CONDITIONS:
1. All 4 new files are implemented
2. All queue tests pass (~10 tests)
3. All conductor tests pass (~11 tests)
4. Full suite still passes (88 existing + ~21 new = ~109)
5. No out-of-scope files changed
6. Branch is committed

---

## Integration Point for Task 4 (Future)

When Task 4 is built, the conductor changes by **one line**:

```python
# Before (Task 3):
verdict = decide(structural, semantic=None)

# After (Task 4):
semantic_output = evaluate(node_spec, pr_diff, changed_files)
verdict = decide(structural, semantic=semantic_output)
```

That's it. The conductor is architected so Task 4 is a plug-in, not a rewrite.

---

## File Tree After Task 3

```
scripts/runtime/
  conductor.py                          <- NEW (Task 3)
  review_queue.py                       <- NEW (Task 3)
  test_conductor.py                     <- NEW (Task 3)
  test_review_queue.py                  <- NEW (Task 3)
  return_router.py                      (unchanged)
  results_store.py                      (unchanged)
  graph_updater.py                      (unchanged)
  replay.py                             (unchanged)
  heartbeat/                            (unchanged)
  decision_loop/                        (unchanged, do not import)
  verification/
    __init__.py                       (frozen)
    semantic_schema.py                (frozen, Task 4 target)
    invariant_schema.py               (T1, frozen)
    structural.py                     (T1, frozen)
    test_structural.py                (T1, frozen)
    verdict_schema.py                 (T2, frozen)
    decision_engine.py                (T2, frozen)
    test_decision_engine.py           (T2, frozen)
```
