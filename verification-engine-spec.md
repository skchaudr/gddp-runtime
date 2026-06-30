# GDDP Verification Engine — Specification

**Status:** Draft for amendment
**Date:** 2026-06-30
**Location:** `scripts/runtime/verification/` in this repo
**Supersedes:** `verification-parallel-build-revised.md` Task 4 (single-call semantic evaluator)
**Predecessor:** `gddp-config/scripts/verify_node.py` (deterministic harness, to be ported)

---

## 1. Purpose

The verification engine is the agentic evaluation layer for GDDP. It wakes
when a node is reported complete, inspects the node's source repo against its
acceptance criteria and the project graph's structural integrity, and reports
one of six verdicts. It never mutates graph status. It writes a receipt. The
human decides.

The engine replaces `review_pr` in the decision loop. Where `review_pr` did
lightweight file-touch checks, the engine does a two-phase investigation:
deterministic probes first, then an agentic multi-turn semantic investigation
that can reason about meaning, not just presence.

### System roles (unchanged)

- Jules = hands (executes coding work)
- gddp-runtime = nervous system (dispatch, webhook, SQLite, graph reads)
- verification engine = judge (inspects completed work, reports verdict)
- decision loop = brain (reads state, decides what to do next, acts, exits)
- gddp-config = source of truth (graph state advances only via human-merged PRs)
- Human = merge authority

### What changed from the prior plan

The `verification-parallel-build-revised.md` plan described Task 4 as a
single LLM call that renders a prompt from `node_spec x pr_diff x
shape_profile`, calls an LLM, extracts JSON. That model is too weak. The
semantic layer must be an agentic multi-turn investigation with read-only
tools, bounded by hard caps, where the LLM investigates turn after turn
until it can justify a judgment. The verdict is then computed by a
deterministic decision engine, not by the LLM itself.

---

## 2. Architecture

```
scripts/runtime/verification/
  __init__.py
  deterministic/
    __init__.py
    probes.py              — ported probe registry + evaluation logic
    constraints.py         — forbidden-pattern scan
    artifacts.py           — required-artifact presence check
    deps.py                — graph dependency status check
    result.py              — DeterministicResult dataclasses + taxonomy
  semantic/
    __init__.py
    agent.py               — multi-turn agentic loop (tool-calling LLM)
    tools.py               — read-only tool implementations (whitelist)
    prompt.py              — system prompt builder (node + graph context)
    result.py              — SemanticOutput dataclasses
  decision_engine.py       — pure lookup matrix: structural + semantic -> verdict
  receipt.py               — writes result.json + transcript.md to SQLite
  schemas.py               — Pydantic models: VerdictReceipt, Verdict enum
  test_*.py                — per-module tests (mock LLM + mock tools)
```

### Data flow (one wake cycle)

```
handle_cron() or handle_event()
  -> decision loop finds node in awaiting_review
  -> calls verification_engine.verify(project_id, node_id, repo_path)
  -> PHASE 1: deterministic floor
       probes.py    -> per-criterion CriterionCheck (pass/fail/indeterminate + taxonomy)
       constraints  -> per-constraint ConstraintCheck (clear/violated)
       artifacts    -> presence dict
       deps         -> dependency status dict
       -> DeterministicResult
  -> GATE: hard fail (missing files, constraint violation) -> skip semantic, verdict from matrix
  -> GATE: indeterminate / needs_evidence / mismatch_kind -> feed to semantic
  -> PHASE 2: semantic investigation
       agent.py     -> LLM + tool loop over read-only tools
       -> per-criterion SemanticJudgment (judged_pass/judged_fail/indeterminate + evidence + confidence)
       -> SemanticOutput
  -> PHASE 3: decision engine
       decision_engine.decide(deterministic, semantic) -> one of 6 verdicts
  -> receipt.py  -> writes VerdictReceipt to SQLite + file receipt
  -> returns VerdictReceipt to decision loop
  -> decision loop acts: pass -> accept_node (evidence PR), else -> escalate/flag
```

---

## 3. Phase 1 — Deterministic Floor

### 3.1 Source

Ported from `gddp-config/scripts/verify_node.py` (1467 lines). The probe
registry, evaluation logic, constraint scanner, artifact checker, and
dependency checker move into `deterministic/`. The CLI wrapper and receipt
writers stay in gddp-config for standalone use; the runtime imports the
module.

### 3.2 Taxonomy preservation

The existing `CriterionCheck` dataclass carries structured uncertainty
fields. These are preserved verbatim in `DeterministicResult`:

```python
@dataclass
class CriterionCheck:
    id: str
    criterion: str
    status: str               # pass | fail | indeterminate
    confidence: float
    method: str               # symbol | func | path | paths | tier_distinct | human_review | project_policy | ...
    evidence: list[str]
    reasoning: str
    # Taxonomy (populated when status != pass):
    mismatch_kind: str        # wording | source_path | alias_integration | tier_distinct | human_review | ""
    mismatch_detail: str
    needs_evidence: bool      # code exists but no test/live coverage
    human_question: str       # a question a human must answer
```

The flat-list addendum fields from `verify_node.py` are also preserved:

```python
@dataclass
class DeterministicResult:
    criteria: list[CriterionCheck]
    constraints: list[ConstraintCheck]
    artifacts_present: dict[str, bool]
    deps_status: dict[str, str]
    criteria_mismatches: list[CriterionMismatch]      # {criterion_id, kind, detail}
    missing_evidence: list[MissingEvidence]            # {criterion_id, what_is_missing, what_exists}
    human_review_questions: list[HumanReviewQuestion]  # {criterion_id, question}
```

### 3.3 Gate logic (by kind, not pass/fail)

The gate determines whether the semantic phase runs:

| Deterministic outcome | Gate action |
|---|---|
| All criteria `pass`, all constraints `clear`, all artifacts present | Skip semantic. Decision engine -> `pass`. |
| Any criterion `fail` (missing files, pattern absent) | **Hard gate.** Skip semantic. Decision engine -> `fail`. |
| Any constraint `violated` | **Hard gate.** Skip semantic. Decision engine -> `out-of-scope-change-detected`. |
| Missing required artifacts | Skip semantic. Decision engine -> `needs-more-evidence`. |
| Dependencies not complete | Skip semantic. Decision engine -> `blocked`. |
| Criteria `indeterminate` with `mismatch_kind` or `needs_evidence` or `human_question` | **Feed to semantic.** This is the semantic layer's job. |

The key correction: `indeterminate` is not a gate. It is the signal that
the semantic layer should investigate. The deterministic floor says "I
cannot resolve this with regex." The semantic layer says "I will read the
code and reason about whether the implementation matches the intent."

---

## 4. Phase 2 — Semantic Investigation (Agentic)

### 4.1 Model

An LLM with a custom tool-calling loop. The agent receives:
- The node YAML (acceptance criteria, constraints, why, dependencies)
- The project graph context (project vision, architecture notes, execution policy)
- The deterministic result (which criteria passed, which are indeterminate and why)
- A shape profile (if one exists for this project type, see section 6)

The agent investigates turn after turn using read-only tools until it can
justify a per-criterion judgment. It does not pick the final verdict. It
produces a `SemanticOutput` containing per-criterion judgments.

### 4.2 Tool whitelist (read-only, always available)

```python
TOOLS = [
    "read_file",         # read a file from the source repo (path required)
    "list_directory",    # list contents of a directory
    "grep_code",         # regex search across files (returns matches + context)
    "run_command",       # run a shell command in the repo (read-only enforced)
    "read_node_yaml",    # read the node's YAML definition
    "read_project_yaml", # read the project graph YAML
    "git_diff",          # git diff of the repo (unstaged or vs a ref)
    "git_log",           # recent git log entries
]
```

**Hard constraint:** no tool may write, create, delete, or modify any file.
`run_command` is restricted to a read-only allowlist (test runners, git
read commands, lint checks). No network access. No `git push`, `git commit`,
`pip install`, or any mutation. The tool layer enforces this; the LLM prompt
instructs it, but enforcement is in code, not prompt.

### 4.3 Loop mechanics

```python
def investigate(node, project, deterministic_result, shape_profile) -> SemanticOutput:
    messages = build_system_prompt(node, project, deterministic_result, shape_profile)
    tool_budget = MAX_TOOL_CALLS   # hard cap, e.g. 40
    turn_budget = MAX_TURNS        # hard cap, e.g. 15

    for turn in range(turn_budget):
        response = llm.chat(messages, tools=TOOL_SCHEMAS)
        if response.tool_calls:
            for call in response.tool_calls:
                if tool_budget <= 0:
                    break
                result = execute_tool(call.name, call.args)
                messages.append(tool_result(call.id, result))
                tool_budget -= 1
        if response.finish_reason == "stop":
            # LLM is done investigating; parse SemanticOutput from final message
            return parse_semantic_output(response.content)

    # Budget exhausted; return what we have with lowered confidence
    return partial_semantic_output(messages, reason="budget_exhausted")
```

### 4.4 SemanticOutput schema

```python
class CriterionJudgment(BaseModel):
    criterion_id: str
    judgment: Literal["judged_pass", "judged_fail", "indeterminate"]
    confidence: float                    # 0.0-1.0
    evidence: list[str]                  # what the agent found (file:line, command output)
    reasoning: str                       # why the agent reached this judgment

class SemanticOutput(BaseModel):
    judgments: list[CriterionJudgment]
    overall_reasoning: str               # narrative summary of the investigation
    risks: str | None                    # any risks the agent noticed
    followup_candidates: str | None      # nodes this work might unblock or affect
    budget_exhausted: bool               # true if the agent hit a hard cap
```

### 4.5 LLM runner abstraction

```python
class LLMRunner(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse: ...
```

The production runner uses a direct API call (OpenAI or Anthropic). Tests
use a mock runner that returns canned responses. No network in tests. The
runner is injected, not hardcoded.

### 4.6 Bounded and testable

- `MAX_TURNS`: hard cap on conversation turns (default 15)
- `MAX_TOOL_CALLS`: hard cap on total tool invocations (default 40)
- All tools are mockable (filesystem operations against a temp dir, command
  execution mocked or sandboxed)
- No network calls in tests. The LLM runner is mocked. Tools operate on a
  temp directory fixture.

---

## 5. Phase 3 — Decision Engine (Pure, Deterministic)

### 5.1 Principle

The LLM does not pick the verdict. The decision engine is a pure function
that combines `DeterministicResult` + `SemanticOutput` and returns one of
the 6 verdicts via a lookup matrix. This is testable without an LLM.

### 5.2 Precedence (load-bearing)

The matrix is evaluated in strict precedence order. **Row order in §5.3 is
the evaluation order**, highest precedence first. The first matching row
fires. This mirrors `decide_verdict()` in `verify_node.py:1065`, extended
with the semantic layer. Earlier guards (deps, constraints, hard fail)
short-circuit before any semantic judgment is consulted — a real
`judged_fail` from the agent therefore outranks `budget_exhausted`, because
fail is evaluated before exhaustion.

### 5.3 Decision matrix (in evaluation order)

| # | Deterministic | Semantic | Artifacts | Deps | Verdict |
|---|---|---|---|---|---|
| 1 | * | * | * | incomplete | `blocked` |
| 2 | constraint violated | * | * | complete | `out-of-scope-change-detected` |
| 3 | any fail | (skipped) | * | complete | `fail` |
| 4 | indeterminate only | any judged_fail | * | complete | `fail` |
| 5 | all pass | (skipped) | missing | complete | `needs-more-evidence` |
| 6 | indeterminate only | all judged_pass | missing | complete | `needs-more-evidence` |
| 7 | indeterminate only | budget_exhausted | * | complete | `needs-more-evidence` |
| 8 | indeterminate only | no judgments (empty) | * | complete | `needs-more-evidence` |
| 9 | indeterminate only | any indeterminate | present | complete | `needs-human-review` |
| 10 | indeterminate only | all judged_pass | present | complete | `pass` |
| 11 | all pass | (skipped) | present | complete | `pass` |

Notes:
- Rows 1–3 are the deterministic short-circuit (deps → constraints → fail),
  identical precedence to `verify_node.py`.
- Row 4 inserts the semantic fail **above** budget/exhaustion (row 7) so a
  real finding wins even if the agent later ran out of budget.
- Row 6 is the previously-missing combo: agent judges pass but a required
  artifact is absent → evidence still incomplete.
- Anything not matched falls through to row 11 (`pass`) only when fully
  clean; otherwise it is structurally impossible to reach (every `*` is
  covered by an earlier row).

### 5.4 Confidence

`decide()` returns `(verdict, confidence, required_next_action)`. Confidence
is derived deterministically:

- **Deterministic-only verdicts** (rows 1–3, 5, 11): use the same
  per-branch confidence as `verify_node.decide_verdict` (mean of the
  contributing criteria, or the fixed branch constant for deps/constraints).
- **Semantic-influenced verdicts** (rows 4, 6–10): `confidence =
  min(deterministic_floor_confidence, mean(judgment.confidence for the
  judgments that drove the row))`. The blend never exceeds the weaker of the
  two layers — the engine is no more confident than its least-confident
  input.
- `budget_exhausted` (row 7) caps confidence at 0.5 regardless of judgment
  confidence.

### 5.5 Implementation shape

```python
def decide(deterministic: DeterministicResult,
           semantic: SemanticOutput | None) -> tuple[str, float, str]:
    """Pure function. No I/O, no LLM, no side effects."""
    # Rows are dicts in a list, evaluated top-to-bottom (§5.3 order).
    # 1. deps incomplete            -> blocked
    # 2. constraint violated        -> out-of-scope-change-detected
    # 3. deterministic fail         -> fail
    # 4. semantic judged_fail       -> fail
    # 5-8. missing artifacts / budget / empty -> needs-more-evidence
    # 9. semantic indeterminate     -> needs-human-review
    # 10-11. clean                  -> pass
    # confidence per §5.4
    # Return (verdict, confidence, required_next_action)
```

The matrix is a lookup table, not nested if-chains: an ordered list of row
predicates, first match wins.

---

## 6. Shape Profiles

**Decision: include in v1.**

Shape profiles encode "what this kind of project should look like." They are
fed into the semantic agent's context so it can reason about project-type
expectations (e.g., a CLI tool should have a console-scripts entry point; a
runtime orchestrator should not source executor-specific modules from a
common layer).

### 6.1 Schema location

`gddp-config/schemas/v1/shape_profile.yaml` (schema only, in pre-work).

### 6.2 Profile location

`gddp-config/profiles/<profile_id>.yaml` (content, in Wave 3).

### 6.3 Schema shape

```yaml
profile_id: cli-tool
description: CLI tool shape profile
expected_node_chain:
  - spec
  - parser
  - validator
  - executor
  - tests
invariant_rules:
  - Graph legality must be preserved
  - Acceptance criteria must not weaken
anti_patterns:
  - Runtime silently mutates source graph
  - Acceptance criteria removed without replacement
```

### 6.4 Project binding

`project.yaml` gets an optional `shape_profile` field:

```yaml
shape_profile: cli-tool   # optional; absent = generic
```

When absent, the semantic agent runs without a profile. Default behavior
remains generic.

### 6.5 Initial profiles (4)

| Profile | Description |
|---|---|
| `cli-tool` | Console-script entry points, arg parsing, read-only-by-default |
| `runtime-orchestrator` | Event-driven loop, no config mutation, receipt-based return |
| `web-app` | Route handlers, auth boundary, template/render separation |
| `automation` | Folder-based intake, dry-run gates, human-review-before-submit |

The `automation` profile is the one sell-valuables would use.

---

## 7. Receipt and Verdict Output

### 7.1 VerdictReceipt (Pydantic)

```python
class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    NEEDS_HUMAN_REVIEW = "needs-human-review"
    NEEDS_MORE_EVIDENCE = "needs-more-evidence"
    OUT_OF_SCOPE_CHANGE_DETECTED = "out-of-scope-change-detected"

class VerdictReceipt(BaseModel):
    project_id: str
    node_id: str
    verdict: Verdict
    confidence: float
    deterministic: DeterministicResult
    semantic: SemanticOutput | None
    decision_reasoning: str           # from the decision engine
    required_next_action: str
    generated_at: str                 # ISO timestamp
```

### 7.2 Persistence

- **SQLite:** written to the `results` table with `status=verdict` and the
  receipt as JSON. This is the same table `return_router.py` writes to.
- **File receipt (optional):** `verification/<project>/<node>/result.json`
  + `transcript.md` in the source repo or a configured output dir. Mirrors
  the existing `verify_node.py` receipt format for human readability.
- **No graph mutation.** The receipt is evidence. The decision loop reads
  it and decides whether to call `accept_node` (open evidence PR) or
  escalate.

---

## 8. Integration with Decision Loop

### 8.1 Replace `review_pr`

The decision loop spec (`docs/decision-loop-spec.md`) currently lists 4
powers: `dispatch_next`, `review_pr`, `accept_node`, `escalate`. The
verification engine replaces `review_pr`:

- **Before:** `handle_event` -> `review_pr` (lightweight file-touch check) -> `accept_node`
- **After:** `handle_event` -> `verification_engine.verify()` -> if `pass` -> `accept_node`

`review_pr` becomes a deprecated stub that delegates to the engine. The
spec doc is updated to reflect this.

### 8.2 Trigger

The engine runs when the decision loop finds a node in `awaiting_review`
state (set by `return_router.handle_merged_pr`). The decision loop calls:

```python
from runtime.verification import verify
receipt = verify(project_id, node_id, repo_path)
```

If `receipt.verdict == Verdict.PASS`, the decision loop proceeds to
`accept_node` (opens evidence PR via `graph_updater.open_evidence_pr`).
Otherwise it writes the receipt and escalates or flags for human review.

### 8.3 Decision-loop spec update

`docs/decision-loop-spec.md` section "Powers" is updated:

- `review_pr` -> renamed to `verify_node` (delegates to verification engine)
- The `review_pr` section is replaced with the engine's two-phase description
- The 4 powers become: `dispatch_next`, `verify_node`, `accept_node`, `escalate`

### 8.4 Decision-loop-runtime node update

The pending `decision-loop-runtime` graph node in `gddp-config` has its
acceptance criteria updated to reflect "engine replaces review_pr." The
node's criteria should reference the verification engine's contract:
two-phase evaluation, 6 verdicts, receipt to SQLite, no graph mutation.

---

## 9. LLM Dependency

### 9.1 New dependency

The runtime currently has no `requirements.txt` or `pyproject.toml`
(dependencies are documented in `AGENTS.md` as "stdlib + Flask"). The
semantic layer requires an LLM client library.

**Decision:** create `requirements.txt` in the runtime repo root:

```
flask>=3.0
pyyaml>=6.0
pydantic>=2.0
openai>=1.0       # or anthropic>=0.20, depending on chosen provider
```

The LLM runner abstraction (section 4.5) means the provider is swappable.
The initial implementation uses one provider; the abstraction makes
switching a one-file change.

### 9.2 Pydantic

The existing decision loop already uses Pydantic (`schema.py`). The
verification engine adds Pydantic models for `VerdictReceipt`,
`SemanticOutput`, and `CriterionJudgment`. This is not a new dependency,
just expanded use of an existing one.

---

## 10. Pre-Work on Main (Before Any Branching)

One commit on `main` before any parallel work. Every branch inherits these.

### 10.1 Items

1. **Module skeleton:**
   ```
   scripts/runtime/verification/__init__.py          (empty)
   scripts/runtime/verification/deterministic/__init__.py  (empty)
   scripts/runtime/verification/semantic/__init__.py      (empty)
   ```

2. **Shared schema stubs** in `scripts/runtime/verification/schemas.py`:
   - `Verdict` enum (6 values, literal)
   - `VerdictReceipt` Pydantic model (fields defined, no logic)
   - `DeterministicResult` dataclass (fields defined, no logic)
   - `SemanticOutput` Pydantic model (fields defined, no logic)

3. **Shape profile schema** at `gddp-config/schemas/v1/shape_profile.yaml`:
   - Schema definition only, no profile content

4. **`requirements.txt`** in runtime repo root:
   - `flask`, `pyyaml`, `pydantic`, `openai` (or `anthropic`)

5. **Decision-loop spec update** (`docs/decision-loop-spec.md`):
   - Rename `review_pr` -> `verify_node`
   - Add verification engine description (two-phase, 6 verdicts, receipt, no mutation)

6. **Decision-loop-runtime node update** (`gddp-config/graphs/gddp-runtime/nodes/`):
   - Update acceptance criteria to reflect engine replaces `review_pr`

### 10.2 DoD for pre-work

- `python3 -m pytest -q` green (existing tests unaffected)
- `python3 -c "from runtime.verification.schemas import Verdict"` works
- `gddp-config/.venv/bin/python scripts/validate.py` clean (shape_profile schema validates)
- All items on `main`, committed, pushed

---

## 11. Build Waves

### Wave 1 — Deterministic port + Decision engine (parallel, 2 branches)

| Branch | Scope | Files |
|---|---|---|
| `feature/t1-deterministic` | Port `verify_node.py` probes, constraints, artifacts, deps into `deterministic/` | `deterministic/probes.py`, `deterministic/constraints.py`, `deterministic/artifacts.py`, `deterministic/deps.py`, `deterministic/result.py`, `test_deterministic.py` |
| `feature/t2-decision` | Pure decision engine: lookup matrix combining DeterministicResult + SemanticOutput -> verdict | `decision_engine.py`, `test_decision_engine.py` |

**Non-overlapping.** T1 writes `deterministic/` only. T2 writes
`decision_engine.py` only. Both import from `schemas.py` (frozen during
this wave).

### Wave 2 — Conductor wiring (standalone, 1 branch)

| Branch | Scope | Files |
|---|---|---|
| `feature/t3-conductor` | Wire engine into decision loop: `handle_event` calls `verify()` on `awaiting_review` nodes, writes receipt to SQLite, routes to `accept_node` or escalate | `scripts/runtime/decision_loop/engine.py`, `scripts/runtime/verification/receipt.py`, `scripts/runtime/verification/__init__.py` (exports `verify()`), `test_conductor.py` |

Touches existing files. No parallelism. The zero-config-write assert is
load-bearing: the engine must never write to `gddp-config` graph YAML.

### Wave 3 — Semantic agent + Shape profiles (parallel, 2 branches)

| Branch | Scope | Files |
|---|---|---|
| `feature/t4-semantic` | Agentic multi-turn loop, read-only tools, prompt builder, LLM runner abstraction, SemanticOutput parsing | `semantic/agent.py`, `semantic/tools.py`, `semantic/prompt.py`, `semantic/result.py`, `test_semantic.py` |
| `feature/t5-profiles` | 4 shape profile YAML files + project.yaml `shape_profile` field | `gddp-config/profiles/cli-tool.yaml`, `gddp-config/profiles/runtime-orchestrator.yaml`, `gddp-config/profiles/web-app.yaml`, `gddp-config/profiles/automation.yaml`, (project.yaml edits) |

**Non-overlapping.** T4 writes `semantic/` only. T5 writes
`gddp-config/profiles/` only. Both reference `shape_profile.yaml` schema
(frozen from pre-work).

---

## 12. Per-Task Stop Condition

Each task branch stops when:

```
- Task files are implemented.
- Task-local tests pass (python3 -m pytest scripts/runtime/verification/test_<module>.py).
- No out-of-scope files changed (enforced by scope lock in the task packet).
- New dependencies, if any, recorded in requirements.txt.
- git diff is reviewed.
- Branch is committed.
- Final summary names files changed, tests run, and unresolved questions.
```

This is the termination contract from the prior plan, unchanged.

---

## 13. Test Strategy

### 13.1 Unit tests (per module, no LLM, no network)

- `test_deterministic.py`: mock repo dir, run probes, assert CriterionCheck
  statuses + taxonomy fields. Test all probe types (symbol, func, path,
  paths, tier_distinct, human_review, project_policy).
- `test_decision_engine.py`: feed DeterministicResult + SemanticOutput
  combinations, assert verdict from the matrix. One test per matrix row.
  No mocking needed (pure function).
- `test_semantic.py`: mock LLMRunner (canned responses), mock tools (temp
  dir fixture), assert SemanticOutput parsing, budget enforcement, tool
  whitelist enforcement.
- `test_conductor.py`: mock SQLite, mock GraphReader, assert engine
  writes receipt, does NOT write graph YAML, routes verdict to
  accept_node/escalate correctly.

### 13.2 Integration test (dry_run.py extension)

The existing `scripts/dry_run.py` end-to-end fake flow is extended to
include the verification engine: dispatch -> execute -> merged PR ->
verification engine -> receipt -> accept_node (evidence PR stub). The
zero-config-write assert proves the engine never mutates graph truth.

### 13.3 Receipt auditability

Every receipt includes:
- Full deterministic result (which probes ran, what they found, taxonomy)
- Full semantic output (which tools were called, what the agent found, per-criterion judgments)
- Decision engine reasoning (which matrix row fired)
- Required next action

A human (or another agent) can audit any verdict without re-running the
engine by reading the receipt.

---

## 14. Hard Constraints

1. **No graph mutation.** The engine writes receipts and verdicts only.
   Graph status advances via `graph_updater.open_evidence_pr` (PR-proposal
   model), which the decision loop calls after a `pass` verdict. Human
   merges.
2. **Read-only tools.** The semantic agent's tools cannot write, create,
   delete, or modify files. No network. No git mutations. Enforced in
   code, not prompt.
3. **LLM does not pick the verdict.** The decision engine is a pure
   deterministic lookup matrix. The LLM produces per-criterion judgments;
   the matrix combines them with the deterministic result.
4. **6 verdicts preserved.** No new verdicts, no removed verdicts.
5. **Taxonomy preserved.** `mismatch_kind`, `needs_evidence`,
   `human_question` flow from deterministic probes through to the receipt.
6. **Bounded.** Hard caps on turns and tool calls. Budget exhaustion
   produces `needs-more-evidence`, not a hang.
7. **No network in tests.** LLM runner is mocked. Tools operate on temp
   dir fixtures.
8. **Non-overlapping file scopes.** Parallel branches touch disjoint file
   sets. Pre-work items are frozen during branching waves.

---

## 15. Resolved Decisions

1. **LLM provider: Anthropic.** Claude (Opus/Sonnet) is the initial
   provider for the semantic investigation. The `LLMRunner` abstraction
   (§4.5) keeps it swappable; switching is a one-file change.
2. **Receipt storage: both.** SQLite `results` row (machine) **and** a file
   receipt (`result.json` + `transcript.md`) for human audit, mirroring
   `verify_node.py` parity. Output dir is configured, defaults to
   `verification/<project>/<node>/`.
3. **Shape profile binding: per-project.** One `shape_profile` field on
   `project.yaml`. Per-node binding is deferred; revisit only if a real
   project needs mixed profiles.
4. **Budgets: 15 turns / 40 tool calls, tunable.** Starting defaults;
   exposed as config constants and tuned empirically against real nodes.
5. **Semantic agent model: Anthropic Claude** (per #1). System prompt and
   tool schemas are validated against Claude's tool-calling during the Wave
   3 `feature/t4-semantic` build.

> The earlier "graph_updater PR-proposal vs direct-write" question is
> **resolved in shipped code**: `scripts/runtime/graph_updater.py`
> already implements `open_evidence_pr` (branch → commit → push → PR). The
> engine uses it; no ADR needed.
