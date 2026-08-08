# Verdict Receipt: Two-Lane Evaluation

A **VerdictReceipt** is the output of the two-lane evaluator. It combines deterministic criteria checks with semantic integrity analysis to produce a verdict that is evidence for human review, not autonomous authority.

## VerdictReceipt Structure

Defined in `scripts/runtime/verification/schemas.py`:

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `str` | Project identifier |
| `node_id` | `str` | Node identifier |
| `verdict` | `Verdict` | Combined verdict (see below) |
| `criteria_verdict` | `Verdict \| None` | Deterministic lane verdict |
| `integrity` | `IntegrityOutput \| None` | Integrity lane output |
| `confidence` | `float` | Combined confidence (0.0-1.0) |
| `criteria_confidence` | `float` | Deterministic lane confidence |
| `completeness` | `float` | Evidence completeness (0.0-1.0) |
| `graph_readiness` | `float` | Graph readiness score (0.0-1.0) |
| `completeness_status` | `Literal[...]` | `complete`, `partial`, `not-run` |
| `deterministic` | `DeterministicResult` | Deterministic lane output |
| `semantic` | `SemanticOutput \| None` | Semantic lane output |
| `decision_reasoning` | `str` | Why this verdict was chosen |
| `required_next_action` | `str` | What the human should do next |
| `generated_at` | `str` | ISO timestamp |
| `evaluated_tree_sha` | `str \| None` | Git tree object SHA (legacy) |
| `evaluated_commit_sha` | `str \| None` | Git commit SHA that was evaluated |
| `merge_commit_sha` | `str \| None` | Git merge commit SHA (if applicable) |
| `expected_base_commit_sha` | `str \| None` | Git base commit at dispatch |
| `pr_ref` | `str \| None` | Pull request reference (if applicable) |
| `job_id` | `str \| None` | Associated job identifier |
| `execution_attempt_id` | `str \| None` | Durable attempt identifier |
| `evidence_manifest_sha256` | `str \| None` | SHA-256 of evidence manifest |
| `mission_receipt_id` | `str \| None` | Mission receipt identifier (if applicable) |
| `canonical_context` | `dict[str, str] \| None` | Context offered to evaluator |
| `context_coverage` | `ContextCoverage \| None` | Per-lane coverage signal |

**Source:** `scripts/runtime/verification/schemas.py` (VerdictReceipt class, lines ~200-280)

## Verdict Values

### Combined Verdict (Verdict enum)

| Verdict | Meaning |
|---------|---------|
| `pass` | All criteria satisfied, integrity preserved |
| `fail` | One or more criteria failed |
| `blocked` | Hard blocker (dependency failed, integrity violation) |
| `needs-human-review` | Evaluator cannot decide; human must review |
| `needs-more-evidence` | Insufficient evidence to judge |
| `out-of-scope-change-detected` | Executor touched files outside node scope |

**Source:** `scripts/runtime/verification/schemas.py` (Verdict enum, lines ~20-30)

### Integrity Verdict (IntegrityOutput.verdict)

| Verdict | Meaning |
|---------|---------|
| `pass` | Intent and integrity preserved |
| `block` | Hard integrity violation |
| `drift` | Intent drift detected |
| `insufficient` | Not enough evidence to judge integrity |
| `contradicted` | Evidence contradicts node intent |
| `unknown` | Cannot determine integrity status |

**Source:** `scripts/runtime/verification/schemas.py` (IntegrityOutput class, lines ~100-120)

## Two-Lane Evaluation

### Lane 1: Deterministic (Criteria)

Checks acceptance criteria against concrete evidence (files, tests, artifacts).

#### DeterministicResult Structure

| Field | Type | Description |
|-------|------|-------------|
| `criteria` | `list[CriterionCheck]` | Per-criterion checks |
| `constraints` | `list[ConstraintCheck]` | Per-constraint checks |
| `artifacts_present` | `dict[str, bool]` | Required artifacts presence |
| `deps_status` | `dict[str, str]` | Dependency statuses |
| `criteria_mismatches` | `list[CriterionMismatch]` | Criterion mismatches |
| `missing_evidence` | `list[MissingEvidence]` | Missing evidence |
| `human_review_questions` | `list[HumanReviewQuestion]` | Questions for human |
| `subject_diff` | `dict \| None` | Neutral narration of base..HEAD |

#### CriterionCheck Structure

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Criterion identifier |
| `criterion` | `str` | Criterion text |
| `status` | `str` | `pass`, `fail`, `untested` |
| `confidence` | `float` | Confidence (0.0-1.0) |
| `method` | `str` | Check method (e.g., `file_exists`, `content_check`) |
| `evidence` | `list[str]` | Evidence paths/lines |
| `reasoning` | `str` | Why this status was chosen |
| `mismatch_kind` | `str` | Mismatch category (if any) |
| `mismatch_detail` | `str` | Mismatch details (if any) |
| `needs_evidence` | `bool` | Whether more evidence is needed |
| `human_question` | `str` | Question for human (if any) |

**Source:** `scripts/runtime/verification/schemas.py` (CriterionCheck dataclass, lines ~40-60)

### Lane 2: Semantic (Integrity)

Analyzes intent preservation and graph integrity using LLM-based reasoning.

#### IntegrityOutput Structure

| Field | Type | Description |
|-------|------|-------------|
| `verdict` | `Literal[...]` | Integrity verdict (see above) |
| `intent_preserved` | `bool` | Whether intent is preserved |
| `graph_integrity_preserved` | `bool` | Whether graph integrity is preserved |
| `required_human_review` | `bool` | Whether human review is required |
| `confidence` | `float` | Confidence (0.0-1.0) |
| `findings` | `list[IntegrityFinding]` | Integrity findings |
| `reasoning` | `str` | Why this verdict was chosen |
| `tool_trace` | `list[dict] \| None` | Ground-truth tool trace |
| `graph_observations` | `list[GraphObservation] \| None` | Forward-looking observations |
| `lane_status` | `LaneExecutionStatus \| None` | Lane execution status |
| `harness_error` | `str \| None` | Harness error (if any) |

#### IntegrityFinding Structure

| Field | Type | Description |
|-------|------|-------------|
| `severity` | `Literal[...]` | `low`, `medium`, `high` |
| `summary` | `str` | Finding summary |
| `affected_node_ids` | `list[str]` | Affected nodes |

#### GraphObservation Structure

Forward-looking observations that do NOT affect the current verdict:

| Field | Type | Description |
|-------|------|-------------|
| `severity` | `Literal[...]` | `low`, `medium`, `high` |
| `summary` | `str` | Observation summary |
| `affected_node_ids` | `list[str]` | Affected nodes |

**Source:** `scripts/runtime/verification/schemas.py` (IntegrityOutput class, lines ~100-140)

## Semantic Lane Output

### SemanticOutput Structure

| Field | Type | Description |
|-------|------|-------------|
| `judgments` | `list[CriterionJudgment]` | Per-criterion judgments |
| `overall_reasoning` | `str` | Overall reasoning |
| `risks` | `str \| None` | Identified risks |
| `followup_candidates` | `str \| None` | Suggested follow-up nodes |
| `budget_exhausted` | `bool` | Whether token budget was exhausted |
| `budget_trace` | `dict \| None` | Token usage trace |
| `lane_status` | `LaneExecutionStatus \| None` | Lane execution status |
| `harness_error` | `str \| None` | Harness error (if any) |

### CriterionJudgment Structure

| Field | Type | Description |
|-------|------|-------------|
| `criterion_id` | `str` | Criterion identifier |
| `judgment` | `Literal[...]` | `judged_pass`, `judged_fail`, `indeterminate` |
| `confidence` | `float` | Confidence (0.0-1.0) |
| `evidence` | `list[str]` | Evidence paths/lines |
| `reasoning` | `str` | Why this judgment was chosen |

**Source:** `scripts/runtime/verification/schemas.py` (SemanticOutput class, lines ~80-100)

## Lane Execution Status

### LaneExecutionStatus Enum

| Status | Meaning |
|--------|---------|
| `completed` | Model called submit tool, verdict recorded |
| `no-verdict` | Process exited 0 but no verdict file |
| `crashed` | Process exited non-zero |
| `timed-out` | Subprocess timeout |

**Source:** `scripts/runtime/verification/schemas.py` (LaneExecutionStatus enum, lines ~10-20)

## Context Coverage

### ContextCoverage Structure

| Field | Type | Description |
|-------|------|-------------|
| `criteria` | `LaneCoverage \| Literal["not_run"]` | Criteria lane coverage |
| `integrity` | `LaneCoverage` | Integrity lane coverage |
| `overall` | `Literal[...]` | `none`, `low`, `medium`, `high` |

### LaneCoverage Structure

| Field | Type | Description |
|-------|------|-------------|
| `rating` | `Literal[...]` | `none`, `low`, `medium`, `high` |
| `offered` | `int` | Number of context items offered |
| `content_accessed` | `int` | Number of items accessed |
| `not_observed` | `int` | Number of items not observed |
| `accessed_paths` | `list[str]` | Paths that were accessed |
| `not_observed_paths` | `list[str]` | Paths that were not observed |

**Source:** `scripts/runtime/verification/schemas.py` (ContextCoverage class, lines ~160-180)

## Completeness Status

| Status | Meaning |
|--------|---------|
| `complete` | All lanes ran successfully |
| `partial` | Some lanes ran, some did not (e.g., budget exhausted) |
| `not-run` | No lanes ran (e.g., evaluator crashed) |

**Inference:** If `semantic` is None, completeness is `not-run`. If `budget_exhausted` is True or no judgments, completeness is `partial`.

**Source:** `scripts/runtime/verification/schemas.py` (VerdictReceipt._infer_completeness_status)

## Provenance Fields

### evaluated_tree_sha vs. evaluated_commit_sha

**Historical context:** Early receipts recorded the git tree object SHA. Later receipts record the commit SHA separately for truthful comparison with `merge_commit_sha`.

**Legacy compatibility:** Both fields default to None for old receipts.

### expected_base_commit_sha

Records the base commit at dispatch time. Enables diff-based evidence downstream.

### evidence_manifest_sha256

SHA-256 hash of the evidence manifest file. Binds the receipt to specific evidence.

## Systems That Produce/Consume

### Producers

- **Evaluator orchestrator** (`scripts/runtime/verification/orchestrator.py`) — runs two-lane evaluation
- **Verification bridge** (`scripts/runtime/verification/bridge.py`) — adapter between runtime and evaluator

### Consumers

- **Reconciler** (`scripts/runtime/heartbeat/reconciler.py`) — reads verdicts to decide next actions
- **Provisional gate** (`scripts/runtime/heartbeat/provisional_gate.py`) — marks nodes provisional on pass
- **Human reviewer** — reads verdicts to accept/reject nodes

## Relationships

```
Executor Session (1) → (0..1) Verdict Receipt
Verdict Receipt (1) → (1) Node
Verdict Receipt (1) → (0..1) Gate Token
Verdict Receipt (1) → (0..1) Evidence Manifest
```

## Key Invariants

1. Verdict receipts are evidence, not graph truth
2. The runtime never marks a node `complete` based on a verdict
3. Two-lane evaluation combines deterministic and semantic analysis
4. Forward-looking graph observations do not affect the current verdict
5. Completeness status tracks whether lanes ran successfully
6. Provenance fields bind receipts to specific git states and evidence

## Example

```python
receipt = VerdictReceipt(
    project_id="gddp-runtime",
    node_id="neutral-executor-contract",
    verdict=Verdict.PASS,
    criteria_verdict=Verdict.PASS,
    integrity=IntegrityOutput(
        verdict="pass",
        intent_preserved=True,
        graph_integrity_preserved=True,
        required_human_review=False,
        confidence=0.95,
        findings=[],
        reasoning="All criteria satisfied, no integrity violations",
    ),
    confidence=0.95,
    criteria_confidence=0.95,
    completeness=1.0,
    graph_readiness=0.95,
    completeness_status="complete",
    deterministic=DeterministicResult(
        criteria=[...],
        constraints=[...],
        artifacts_present={"scripts/adapters/executor_protocol.py": True},
        deps_status={},
        criteria_mismatches=[],
        missing_evidence=[],
        human_review_questions=[],
        subject_diff={...},
    ),
    semantic=SemanticOutput(
        judgments=[...],
        overall_reasoning="Intent preserved, no drift detected",
        risks=None,
        followup_candidates=None,
        budget_exhausted=False,
    ),
    decision_reasoning="Both lanes passed with high confidence",
    required_next_action="Human review and accept node",
    generated_at="2026-08-08T12:00:00Z",
    evaluated_commit_sha="def456abc789",
    expected_base_commit_sha="abc123def456",
    job_id="job-abc123",
    execution_attempt_id="job-abc123:attempt:0",
    evidence_manifest_sha256="a1b2c3d4e5f6...",
)
```
