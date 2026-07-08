# Frozen Audit Capture

Source Cline session: `1779716726677_jl1oa`

Workspace: `/home/sab-ssd`

Captured: 2026-05-25T16:43:08.592Z

This file preserves the implementation plan plus the separation-of-powers architecture outputs from the tail of the Cline session. The first section is adjacent context because it sets up the acceptance-criteria evaluator; the four important outputs follow.

Full rendered Cline export: [full-session-1779716726677_jl1oa.html](./full-session-1779716726677_jl1oa.html)

---

# Adjacent Context: Step 4 Criteria Evaluator

Message index: `37`  
Timestamp: `2026-05-25T11:07:12.078Z`  
Message id: `msg_kz3usL-r`

Architecture only. Here's step 4 — the acceptance-criteria evaluator — from a structural perspective.

---

## Step 4: The Criteria Evaluator (Architecture)

The problem: a node says something like:

```yaml
acceptance:
  - form accepts name, contact, project type, budget range, location, timeline
  - submission creates one canonical Lead record
  - no duplicate client record is created
```

These are natural language. The PR contains code changes. Someone/something has to decide: does the code satisfy these criteria?

### The Architectural Question Isn't "Which Model?"

It's: **where does the evaluation happen, who does it, and what is it allowed to do?**

Three possible architectures:

---

### Architecture A: Evaluator Is a Tool in Pi's Hands

Pi runs the review. When it hits the acceptance criteria, it calls a tool — same as it calls `git diff` or `grep`. The evaluator is just another tool in the harness.

```
Pi dispatches review packet to itself
  ↓
  Pi calls: git diff main...HEAD
  Pi calls: cat node.yaml (criteria)
  Pi calls: evaluate_criteria(diff, criteria)
                  ↓
         [tool returns structured verdict per criterion]
  Pi assembles final verdict
  Pi's verification commands confirm the tool was actually called
```

**Strength:** Pi stays the single decision-maker. Evaluator is a probe, not an authority.

**Risk:** The evaluator tool is still an LLM. Its output is non-deterministic. But the verification layer catches when the tool's verdict contradicts deterministic evidence.

---

### Architecture B: Evaluator Is a Separate, Smaller Agent

A small, purpose-built agent (not Pi, not Jules) receives the diff and criteria. It returns only PASS/FAIL/UNCERTAIN per criterion. It has no write access, no shell, no git — just read and classify.

```
Pi → dispatches criteria-eval packet to evaluator agent
       ↓
     Evaluator: reads diff + criteria
     Evaluator: returns [{criterion, verdict, confidence, reason}]
       ↓
Pi receives evaluator's verdict
Pi cross-checks against deterministic evidence
Pi issues final judgment
```

**Strength:** Separation of concerns. Evaluator can't mutate anything. Pi can override or escalate if the evaluator and deterministic evidence conflict.

**Risk:** Adds dispatch latency. Another moving part.

---

### Architecture C: Evaluator Is Invisible — Pi Reasons About Criteria Directly

Pi is given the full diff and the criteria as part of its context. It reads them and reasons about satisfaction. No separate evaluator.

```
Pi's context window contains:
  - Full PR diff
  - Full node spec (criteria, constraints)
  - Git state
Pi reviews the diff against each criterion
Pi produces verdict + evidence per criterion
Verification commands check: did Pi actually read the diff? (tool-trace confirms)
```

**Strength:** Simplest. No additional component. Pi already has the operating contract for this.

**Risk:** Pi is a frontier model doing reasoning. It could rationalize, confabulate, or miss things. But the deterministic checks (scope, tests, artifacts) form the floor — the reasoning is on top of those.

---

### My Read: Architecture A or C Fits What You Already Have

Architecture A (evaluator as tool) is the most Pi-harness-native. It treats the evaluator like any other verification probe — just like `grep` or `jq`, but with reasoning.

Architecture C (Pi reasons directly) is what the `agent1-jules-review.yaml` packet already does in its most basic form — just with a fuzzier prompt.

Architecture B (separate agent) is more infrastructure for marginal gain.

**The architectural decision isn't about model quality. It's about where uncertainty lives and who owns the override.** In A and C, Pi owns the final verdict. In B, the evaluator owns a subtask.

---

What's the further direction you wanted to tie in?

---

# Important Output 1: Problem With A and C

Message index: `40`  
Timestamp: `2026-05-25T11:17:45.346Z`  
Message id: `msg_kxqr2JjC`

You're right. I was missing the forest. Let me re-center.

---

## The Problem With A and C

If Pi is the sole verdict-owner, then:

1. **All graph truth reduces to one agent's judgment.** Every node's completion, every edge's validity, every project's progress — one LLM call away from being wrong. That's not a system. That's a puppet.

2. **The evaluator-as-tool is architectural sugar.** It looks like separation of concerns ("Pi has a tool for criteria evaluation") but structurally it's still Pi making the call. The tool just feeds Pi more information. Pi decides what to do with it. The buck still stops at one agent.

3. **It contradicts the graph.** The graph defines what "done" means — acceptance criteria, constraints, contracts, artifacts. The whole point of the graph is to **remove that judgment from any single agent's runtime reasoning**. If we hand the diff to Pi and say "you decide," we've just reinjected the very ambiguity the graph was built to eliminate.

---

## The Forest: Graph-Level Verification Architecture

The vision from `gdd-next.md` was:

```
builder agent → node verifier → edge verifier → graph invariant verifier → semantic verifier → human
```

Not: builder agent → one agent decides. That's the forest.

The architecture that honors this:

### Each Verification Layer Is Independent and Produces Structured Evidence

| Layer | Who | Input | Output | Deterministic? |
|-------|-----|-------|--------|:---:|
| **Structural** | No agent needed — shell commands | `git diff --name-only`, node constraints, artifact paths | `[{check, pass/fail, evidence}]` | ✅ Yes |
| **Test status** | No agent — GitHub API | PR commit SHA | `{tests: pass/fail, coverage: N%}` | ✅ Yes |
| **Criteria** | A **dedicated verifier agent** (not Pi, not Jules) | Diff + acceptance criteria text | `[{criterion, verdict, confidence, reason}]` | ⚠️ Semi |
| **Edge contracts** | **Deterministic loop** | Upstream/downstream node status + declared contracts | `{downstream_contracts_hold: true/false}` | ✅ Yes |
| **Graph invariants** | **Deterministic loop** | Full graph state | `{invariants_hold: true/false, violations: [...]}` | ✅ Yes |

### No Single Agent Owns the Verdict

The **decision loop** is pure logic. It receives structured evidence from every layer and applies a decision matrix:

```
IF all deterministic layers pass
   AND criteria verifier says PASS on all criteria
   AND criteria confidence ≥ threshold
   THEN verdict = ACCEPT

IF any deterministic layer fails
   THEN verdict = FAIL (with evidence)

IF deterministic layers pass
   BUT criteria verifier has UNCERTAIN or FAIL
   THEN verdict = ESCALATE (with evidence packet)

IF edge contracts or graph invariants violated
   THEN verdict = FAIL (with evidence)
```

The decision loop has **no LLM in it**. It doesn't generate anything. It doesn't reason. It applies rules to structured inputs.

### The Verifier Agent Is Architecturally Constrained

The criteria verifier (the only LLM in the verification path) is **structurally prevented from owning the verdict**:

- **It cannot write.** Its tool surface is `read` only. No git, no shell, no file mutation.
- **It cannot decide.** Its output is evidence, not a verdict. The decision loop makes the verdict.
- **It cannot see the loop's decision.** It has no access to other layers' outputs. It sees only the diff and the criteria text.
- **Its task is classification, not generation.** For each criterion: PASS, FAIL, or UNCERTAIN with a reason. Structured output, not prose.

This makes the verifier agent a **witness**, not a **judge**. It testifies. The loop judges.

### The Decision Loop Is the Harness, Not an Agent

This is the key architectural distinction.

| Decision Loop | Decision Agent |
|---------------|---------------|
| Pure rules: if/then on structured inputs | LLM: reasons about unstructured inputs |
| Deterministic — same inputs always produce same output | Non-deterministic — can vary across runs |
| All reasoning is visible and auditable | Reasoning is inscrutable |
| Cannot confabulate or rationalize | Can confabulate, miss things, be overconfident |
| **Is the harness** | **Is an agent** |

The decision loop lives in the harness. It's not dispatched to. It doesn't wake up. It doesn't have a context window. It runs as a shell script or a small Python module that reads JSON inputs and produces a JSON verdict.

### Where Pi Fits

Pi is not the verdict-owner. Pi is the **conductor** — it:

1. Wakes (cron or webhook trigger)
2. Dispatches evidence-gathering packets (to itself or to dedicated verifier agents)
3. Collects evidence artifacts
4. Runs the **decision loop** (deterministic, no LLM) on the collected evidence
5. Writes the final verdict to SQLite
6. Either auto-accepts (if verdict = ACCEPT) or escalates (if verdict = FAIL or UNCERTAIN)

Pi dispatches. The loop decides. The graph advances.

---

## Does This Align?

The architecture I'm describing makes no single agent the owner of graph truth. The graph's acceptance criteria, constraints, and contracts are digested into structured evidence by independent layers. A deterministic decision loop — not an agent — maps evidence to verdict. The human boundary remains the escalation path.

Is this closer to what you're driving at?

---

# Important Output 2: Three-Layer Architecture

Message index: `42`  
Timestamp: `2026-05-25T11:27:19.208Z`  
Message id: `msg_VQKrqdfE`

This is it. This is the architecture. Let me lay it out as I now understand it.

---

## The Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     OPERATOR BOUNDARY                       │
│  Approves semantic changes above threshold                  │
│  Owns graph truth. Owns "what done means."                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
              HUMAN_REVIEW_REQUIRED when:
              SEMANTIC_RISK ≥ medium OR DRIFT present
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              DECISION LOOP (Deterministic)                   │
│                                                             │
│  Reads structured outputs from both layers.                 │
│  Applies rules. No LLM. No reasoning.                       │
│                                                             │
│  IF PASS_STRUCTURAL + PASS_ARTIFACT + SEMANTIC_RISK=low     │
│     + no drift → AUTO_ACCEPT                                │
│                                                             │
│  IF PASS_STRUCTURAL + PASS_ARTIFACT + SEMANTIC_RISK≥medium  │
│     → HUMAN_REVIEW_REQUIRED                                 │
│                                                             │
│  IF any structural/artifact FAIL → REJECT (escalate)        │
└──────┬───────────────────────────────────┬──────────────────┘
       │                                   │
       ▼                                   ▼
┌──────────────────┐            ┌─────────────────────────────┐
│  DETERMINISTIC    │            │  SEMANTIC EVALUATOR          │
│  VALIDATOR        │            │  (LLM — classification only) │
│  (Code)           │            │                              │
│                   │            │  Input:                      │
│  Checks:          │            │  - Original graph state      │
│  - Graph legality │            │  - Variant graph state        │
│    (DAG, refs,    │            │  - PR diff                   │
│     statuses)     │            │  - Node criteria             │
│  - Execution      │            │  - Shape profile             │
│    legality       │            │                              │
│    (deps + mode)  │            │  Output:                     │
│  - Artifact       │            │  - Preserved invariants      │
│    accountability │            │  - Weakened invariants       │
│    (evidence)     │            │  - Added invariants          │
│  - Acceptance     │            │  - Removed responsibilities  │
│    preservation   │            │  - Suspicious edges          │
│    (not weakened) │            │  - Semantic drift detected   │
│  - Test pass/fail │            │  - Verdict per criterion     │
│                   │            │  - Confidence score          │
│                   │            │                              │
│  Output:          │            │  Output:                     │
│  - PASS/FAIL per  │            │  - SEMANTIC_RISK:            │
│    invariant      │            │    low/medium/high           │
│  - Evidence       │            │  - DRIFT_TYPE:               │
│                   │            │    acceptance_weakening /    │
│                   │            │    responsibility_loss /     │
│                   │            │    shape_change / none       │
│                   │            │  - Per-criterion verdicts    │
│                   │            │  - Structured reasoning      │
└──────────────────┘            └─────────────────────────────┘
```

---

## The Core Distinction

```
Deterministic code checks the graph's bones.
An LLM evaluator checks the graph's meaning.
Neither decides whether the node passes.
The decision loop decides — and it's pure rules.
The operator decides when meaning has changed — and they're human.
```

### What This Means for "How Does a Node Pass?"

A node passes when **both** conditions hold:

| Layer | Verdict | Meaning |
|-------|---------|---------|
| Deterministic | PASS_STRUCTURAL | The graph is legally valid. DAG holds. Refs are valid. Status transitions are allowed. Artifacts exist. Tests pass. Criteria weren't silently weakened. |
| Semantic | PASS or SEMANTIC_RISK=low | The graph's meaning is preserved. The implementation satisfies the spirit, not just the text. No drift detected. Or drift is explicitly labeled and the operator approved it. |

The verdict is not a model's opinion. It's the output of two independent evidence-generating layers, fed into a rules-based decision loop.

---

## Where Pi Fits (Revised)

Pi is **not** the semantic evaluator. Pi is also **not** the deterministic validator. Pi is the **conductor**:

1. Pi wakes and reads the event (merged PR).
2. Pi dispatches the **deterministic validator** (a shell script or Python module, no LLM) against the PR + node spec.
3. Pi receives: `PASS_STRUCTURAL: true/false` with evidence per invariant.
4. If structural fails → Pi escalates immediately. No need to check meaning.
5. If structural passes → Pi dispatches the **semantic evaluator** (a focused LLM call with a strict rubric). The evaluator is given the diff, the node criteria, the shape profile, and the original graph. It returns structured output: preserved/weakened invariants, drift type, risk level, per-criterion verdicts.
6. Pi feeds both outputs into the **decision loop** (pure rules).
7. The loop produces: `AUTO_ACCEPT | HUMAN_REVIEW | REJECT`.
8. Pi writes the verdict to SQLite. If AUTO_ACCEPT, Pi advances the graph. If HUMAN_REVIEW, Pi escalates with a structured evidence packet.

---

## The Shape Profiles

This is the part of the architecture that gives the evaluator leverage. Different project types have different expected graph shapes:

```
Parser:     Input → Parser → Model → Validation → Outputs → Tests → Docs
Runtime:    Truth → Reader → Select → Packet → Adapter → Record → Verify → Report
Web app:    Goal → Routes → Data → UI → Interaction → API → Tests → Deploy
CLI:        Contract → Args → Core → Output → Errors → Tests → Install
```

The evaluator isn't asked "is this good?" It's asked:

> *"Compare this node's implementation against the runtime shape profile. The node is supposed to be a `packet builder`. Does the implementation preserve that role? Did it drift into something else? Did it weaken any invariants the runtime profile expects?"*

This converts vague judgment into structured comparison.

---

## The Decision Matrix (Deterministic)

This is a table, not an agent. It lives in the loop as pure logic:

| PASS_STRUCTURAL | PASS_ARTIFACT | SEMANTIC_RISK | DRIFT | → Verdict |
|:---:|:---:|:---:|:---:|---|
| ✅ | ✅ | low | none | **AUTO_ACCEPT** |
| ✅ | ✅ | low | labeled + approved | **AUTO_ACCEPT** |
| ✅ | ✅ | medium | any | **HUMAN_REVIEW** |
| ✅ | ✅ | high | any | **HUMAN_REVIEW** |
| ❌ | any | any | any | **REJECT** (escalate) |
| any | ❌ | any | any | **REJECT** (escalate) |

---

## What This Architecture Achieves

1. **No single LLM owns the verdict.** The deterministic validator is code. The semantic evaluator is an LLM doing classification, not decision-making. The decision loop is rules.

2. **The graph is the source of truth.** It defines what invariants matter, what shape profile applies, what acceptance means. The system enforces the graph's definitions, not an agent's interpretation.

3. **Meaning changes are visible, not hidden.** If a PR silently weakens acceptance criteria or shifts project shape, the semantic evaluator surfaces that as DRIFT. The operator sees it. The graph records it.

4. **The floor is hard.** Structural invalidity → instant reject. No LLM gets a chance to rationalize around a broken DAG or missing artifact.

5. **The system scales by shrinking the human's cognitive load.** When all invariants hold and semantic risk is low → auto-accept. The human only sees the cases where meaning has genuinely shifted.

---

Does this architecture — the three layers, the shape profiles, the decision matrix — feel like the right foundation to move toward?

---

# Important Output 3: Architecture Final Form

Message index: `44`  
Timestamp: `2026-05-25T11:31:16.054Z`  
Message id: `msg_Wzomgyi5`

That's the distinction. Let me lock it in.

---

## The Architecture — Final Form

```
                               EVENT (merged PR)
                                      │
                                      ▼
                              ┌───────────────┐
                              │  Pi (conductor │
                              │  / orchestrator│
                              └───────┬───────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 │                  ▼
           ┌──────────────┐          │         ┌──────────────┐
           │ DETERMINISTIC │          │         │  SEMANTIC     │
           │ VALIDATOR     │          │         │  EVALUATOR    │
           │ (code, no LLM)│          │         │  (LLM,        │
           │               │          │         │   read-only)  │
           │ Checks:       │          │         │               │
           │ - DAG validity│          │         │ Analyzes:     │
           │ - refs valid  │          │         │ - fidelity    │
           │ - artifacts   │          │         │ - risk        │
           │   exist       │          │         │ - drift       │
           │ - tests pass  │          │         │ - criteria    │
           │ - dep check   │          │         │   satisfaction│
           │ - acceptance  │          │         │ - shape match │
           │   not weakened│          │         │               │
           │               │          │         │ Returns:      │
           │ Returns:      │          │         │ semantic_     │
           │ pass/fail per │          │         │ fidelity:     │
           │ invariant +   │          │         │ preserved     │
           │ evidence      │          │         │ | weakened    │
           └──────┬───────┘          │         │ | drifted     │
                  │                  │         │ | contradicted│
                  │                  │         │ | insufficient │
                  │                  ▼         │               │
                  │         ┌──────────────┐   │ risk_level:   │
                  │         │ Only if       │   │ low|med|high  │
                  │         │ structural    │   │               │
                  │         │ passes        │   │ drift_type:   │
                  │         └──────┬───────┘   │ none|accept_  │
                  │                │           │ weakening|... │
                  │                ▼           │               │
                  │         ┌──────────────┐   │ requires_     │
                  │         │ SEMANTIC      │   │ operator_     │
                  │         │ EVALUATOR     │   │ review:       │
                  │         │ RUNS          │   │ true|false    │
                  │         └──────┬───────┘   │               │
                  │                │           │ evidence +    │
                  │                │           │ reasoning     │
                  │                │           └──────┬────────┘
                  │                │                  │
                  └────────────────┼──────────────────┘
                                   │
                           Both outputs
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │    DECISION LOOP          │
                    │    (pure rules, no LLM)   │
                    │                           │
                    │  Reads structural evidence│
                    │  Reads semantic fidelity  │
                    │  Reads risk/drift         │
                    │                           │
                    │  Applies decision matrix: │
                    │  structural=fail → REJECT │
                    │  risk=low+fidelity=       │
                    │    preserved → ACCEPT     │
                    │  risk≥medium or           │
                    │    fidelity≠preserved →   │
                    │    HUMAN_REVIEW           │
                    └──────────┬───────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                    ▼                     ▼
              ACCEPT              HUMAN_REVIEW
          (Pi advances            (Pi escalates
           graph truth)            with evidence
                                   packet)
```

---

## The Separation of Powers

| Role | Who | Tool | Output | Decides? |
|------|-----|------|--------|:---:|
| **Conductor** | Pi (agent) | Harness dispatch | Orchestrates flow | ❌ |
| **Structural validator** | Shell/Python script | `git`, `jq`, schema check | `{invariant: pass/fail, evidence}` | ❌ |
| **Semantic evaluator** | LLM (read-only, no write) | Diff + criteria + shape profile | `{fidelity, risk, drift, reasoning}` | ❌ |
| **Decision loop** | Pure rules (if/then) | None — just logic | `{verdict: ACCEPT/REJECT/HUMAN_REVIEW}` | **Yes** |
| **Operator** | Human | Evidence packet | Approve/reject semantic changes | **Yes** (at threshold) |

**Neither LLM decides.** The model analyzes meaning. The rules make state transitions. The human gates meaning changes.

That's a system, not an AI-flavored checklist.

---

# Important Output 4: Implementation Plan

Message index: `55`  
Timestamp: `2026-05-25T13:53:22.462Z`  
Message id: `msg_iHQEYw36`

Now I have the full picture. Here's the implementation plan.

---

## Implementation Plan

### Existing Assets

| What Exists | Where | State |
|-------------|-------|-------|
| Graph reader (reads YAML nodes) | `gddp-runtime/scripts/runtime/heartbeat/graph_reader.py` | ✅ Working |
| Scope checker (deps, active jobs) | `gddp-runtime/scripts/runtime/heartbeat/scope_checker.py` | ✅ Working |
| Return router (PR → receipt) | `gddp-runtime/scripts/runtime/return_router.py` | ✅ Working, hardcoded allowlist |
| Results store (receipt persistence) | `gddp-runtime/scripts/runtime/results_store.py` | ✅ Working |
| State recorder (DB mutations) | `gddp-runtime/scripts/runtime/heartbeat/state_recorder.py` | ✅ Working |
| Graph updater | `gddp-runtime/scripts/runtime/graph_updater.py` | ❌ Disabled stub |
| Artifact verifications table | `gddp-runtime/scripts/init_db.py` | ✅ Schema exists, unused |
| Node schema (acceptance, constraints) | `gddp-config/schemas/v1/node.yaml` | ✅ Defined |
| Pi harness (packet runner, verify) | `~/.pi/harness/` | ✅ Working |
| Pi operating contract | `~/.pi/agent/AGENTS.md` | ✅ Defined |

### Missing Assets

| What's Missing | Purpose |
|----------------|---------|
| Structural validator | Deterministic invariant checks (DAG, refs, artifacts, tests, acceptance preservation) |
| Semantic evaluator | LLM-powered fidelity/drift analysis (read-only, classification) |
| Decision loop | Rules-based engine: structural + semantic → verdict |
| Conductor wiring | Pi as orchestrator between gddp-runtime events and validator/evaluator dispatch |
| Shape profiles | Project type templates the evaluator compares against |
| `graph_updater.py` re-enablement | Gated behind verification, writes graph truth on ACCEPT |

---

### Stage 0 — Structural Validator (Foundation)

**Principle:** Code only. No LLM. Returns structured pass/fail per invariant with evidence. Fails here → reject immediately, semantic evaluator never runs.

| # | Task | What It Does | Files |
|---|------|-------------|-------|
| 0.1 | **Define invariant schema** | JSON Schema for the structural validator's output contract. Every invariant check emits `{name, passed, evidence, severity}`. | New: `gddp-runtime/scripts/runtime/verification/invariant_schema.json` |
| 0.2 | **Graph legality checks** | Parse project graph from `gddp-config`. Verify: DAG is acyclic, all `depends_on` refs point to existing nodes, all `unlocks` refs point to existing nodes, no orphaned nodes, every node reachable from an entrypoint. Reuses `GraphReader`. | New: `gddp-runtime/scripts/runtime/verification/structural.py` (function: `check_graph_legality`) |
| 0.3 | **Artifact accountability** | For the completed node: verify every `required_artifacts` path exists on disk or in the PR. Check that `acceptance` criteria are non-empty and specific enough. Verify `constraints` are declared. | Same file: `check_artifact_accountability()` |
| 0.4 | **Scope + constraint enforcement** | Git diff the PR. Every changed file must fall within the node's declared scope. No changed file may violate explicit `constraints`. Every `out_of_scope` path must be untouched. | Same file: `check_scope_enforcement()` |
| 0.5 | **Test status check** | Query GitHub commit status API for the PR's head SHA. All required checks must pass. | Same file: `check_test_status()` |
| 0.6 | **Acceptance preservation** | Compare pre-PR node YAML vs post-PR node YAML (if the PR modifies the node spec itself). Detect: silently weakened criteria, removed criteria, criteria made vaguer. | Same file: `check_acceptance_preservation()` |
| 0.7 | **Structural validator runner** | Wraps all checks, runs them, collects results, emits the unified structural evidence JSON. Exit 0 if all pass, exit 1 if any fail. | Same file: `run_structural_validator()` |
| 0.8 | **Tests for structural validator** | Unit tests against known graph fixtures. Valid DAG passes. Cyclic DAG fails. Missing artifact fails. Scope violation fails. Acceptance weakening fails. | New: `gddp-runtime/scripts/runtime/verification/test_structural.py` |

**Stage 0 delivers:** A module you can invoke as:
```
python3 -m runtime.verification.structural --node triage-cli-core --project vault-doctor --pr-number 51
```
And get:
```json
{
  "overall": "pass" | "fail",
  "checks": [
    {"name": "graph_legality", "passed": true, "evidence": {}},
    {"name": "artifact_accountability", "passed": true, "evidence": {"present": ["decision.md", "patch.diff"], "missing": []}},
    {"name": "scope_enforcement", "passed": true, "evidence": {"in_scope": ["vault_doctor/triage.py"], "out_of_scope": []}},
    {"name": "test_status", "passed": true, "evidence": {"checks": [{"name": "pytest", "status": "completed", "conclusion": "success"}]}},
    {"name": "acceptance_preservation", "passed": true, "evidence": {"weakened": [], "removed": [], "added": []}}
  ]
}
```

---

### Stage 1 — Decision Loop

**Principle:** No LLM. Pure rules. Consumes structural evidence + semantic evidence (when available). Produces `ACCEPT | REJECT | HUMAN_REVIEW`.

| # | Task | What It Does | Files |
|---|------|-------------|-------|
| 1.1 | **Verdict schema** | Define the output contract: `{verdict, reason, evidence_summary, requires_operator}` | New: `verdict_schema.json` |
| 1.2 | **Decision engine** | Reads structural JSON + optional semantic JSON. Applies the decision matrix: structural fail → REJECT; risk=low + fidelity=preserved → ACCEPT; otherwise → HUMAN_REVIEW. | New: `gddp-runtime/scripts/runtime/verification/decision_loop.py` |
| 1.3 | **Tests** | Every path in the decision matrix tested. | New: `test_decision_loop.py` |

**Stage 1 delivers:** A pure function:
```python
from runtime.verification.decision_loop import decide

verdict = decide(structural_output, semantic_output=None)
# → {"verdict": "REJECT", "reason": "structural_failure", ...}
```

---

### Stage 2 — Conductor Wiring (Pi as Orchestrator)

**Principle:** Pi receives the trigger (merged PR), dispatches validators, collects evidence, runs the decision loop, acts on verdict.

| # | Task | What It Does | Files |
|---|------|-------------|-------|
| 2.1 | **Trigger integration** | When `intake_server.py` receives a `pull_request.closed` (merged) event, it currently routes to `return_router.py` which creates a `needs_review` receipt. Extend this: after receipt creation, enqueue a review task for Pi. Simple approach: write a review-needed marker that Pi's cron picks up. | Modify: `intake_server.py` or `return_router.py`. New: a SQLite function or marker file. |
| 2.2 | **Pi review packet template** | A harness packet that tells Pi how to run a review. Roughly: run structural validator, if pass then optionally dispatch semantic evaluator, feed both to decision loop, write verdict back. | New: `~/.pi/harness/packets/review-node.yaml` |
| 2.3 | **Pi review cron/dispatcher** | A systemd timer (or cron) that periodically checks for `needs_review` results in SQLite and dispatches the review packet to Pi. | New: `~/.pi/harness/bin/pi-review-loop` or systemd timer unit |
| 2.4 | **Verdict writeback** | When Pi produces a verdict: ACCEPT → call `graph_updater.py` (re-enabled, gated). REJECT → write to results table, update job status. HUMAN_REVIEW → send ntfy notification with evidence packet, leave in awaiting_review. | Modify: `results_store.py` and `state_recorder.py`. Re-enable: `graph_updater.py` with gate. |
| 2.5 | **Graph updater re-enablement** | Remove the disabled stub. Make `graph_updater.update_graph_node_complete()` call the GitHub Contents API to update the node's status in `gddp-config`. Guard: only callable from the decision loop path. | Modify: `graph_updater.py` |

**Stage 2 delivers:** End-to-end flow: PR merges → intake → receipt → Pi reviews → verdict → graph advances (or escalates).

---

### Stage 3 — Semantic Evaluator

**Principle:** LLM, read-only, classification only. Returns structured fidelity/drift analysis. Never returns "PASS." Returns `semantic_fidelity`, `risk_level`, `drift_type`, `requires_operator_review`.

| # | Task | What It Does | Files |
|---|------|-------------|-------|
| 3.1 | **Semantic output schema** | Pydantic model: `{semantic_fidelity, risk_level, drift_type, requires_operator_review, criteria_verdicts: [{criterion, satisfied, confidence, reasoning}], evidence, reasoning_summary}` | New: `gddp-runtime/scripts/runtime/verification/semantic_schema.py` |
| 3.2 | **Evaluator prompt template** | A structured prompt that gives the LLM: (a) the node's acceptance criteria from YAML, (b) the PR diff, (c) the shape profile for this project type, (d) strict instructions: classify only, emit structured JSON, no prose, claim-discipline. | New: `gddp-runtime/scripts/runtime/verification/evaluator_prompt.py` or a prompt template file |
| 3.3 | **Semantic evaluator runner** | Calls the LLM (via Pi's packet runner or direct API). Extracts structured JSON from response (reuses extraction patterns from `~/.pi/harness/lib/response-extract.sh`). Validates against semantic schema. Returns validated output. | New: `gddp-runtime/scripts/runtime/verification/semantic.py` |
| 3.4 | **Per-criterion evaluation** | For each acceptance criterion in the node spec, the evaluator must produce: `{criterion, satisfied: true/false, confidence: 0-1, reasoning}`. This is structured classification, not free-text judgment. | Inside the prompt template and output schema |
| 3.5 | **Tests** | Test that the schema rejects malformed evaluator output. Test prompt renders correctly. Mock LLM responses to test extraction. | New: `test_semantic.py` |

**Stage 3 delivers:** The ability to call:
```python
semantic_output = run_semantic_evaluator(
    node_id="triage-cli-core",
    pr_diff=diff_text,
    acceptance_criteria=node.acceptance,
    shape_profile="cli-tool"
)
# → {semantic_fidelity: "preserved", risk_level: "low", drift_type: "none", ...}
```

---

### Stage 4 — Shape Profiles

**Principle:** Project type templates that give the evaluator a reference frame. A CLI tool's graph should look different from a runtime's graph.

| # | Task | What It Does | Files |
|---|------|-------------|-------|
| 4.1 | **Shape profile schema** | Define what a shape profile contains: expected node types, expected edges, invariant rules, anti-patterns. | New: `gddp-config/schemas/v1/shape_profile.yaml` |
| 4.2 | **Built-in profiles** | Define initial profiles: `cli-tool`, `runtime-orchestrator`, `web-app`, `parser`, `automation`. Each describes the canonical node chain and what invariants to enforce. | New: `gddp-config/profiles/` directory |
| 4.3 | **Profile selection** | How does a project declare its profile? Add optional `shape_profile` field to `project.yaml`. Default: `generic`. | Modify: `project.yaml` schema and existing project files |
| 4.4 | **Evaluator integration** | Pass the selected profile into the semantic evaluator prompt. The LLM compares the node's implementation against the profile's expectations. | Modify: `semantic.py` prompt builder |

**Stage 4 delivers:** The evaluator has context. For `vault-doctor`, the profile says "CLI tools should have: command contract → argument parsing → core operation → output format → error handling → tests → install/docs." The evaluator checks if `triage-cli-core` preserves that chain.

---

### Stage 5 — Hardening & Edge Cases

| # | Task | Description |
|---|------|-------------|
| 5.1 | **Acceptance drift detection** | When a PR modifies a node's own YAML, detect and flag acceptance weakening separately from implementation review |
| 5.2 | **Edge contract verification** | If node A says it produces output that node B depends on, verify B's expected input still exists after A's implementation |
| 5.3 | **Allowlist removal** | `return_router.py` has `ALLOWED_REPOS = ["skchaudr/vault-doctor"]`. Generalize to read from project config. |
| 5.4 | **Retry policy** | When structural passes but semantic is uncertain, allow operator to re-trigger with adjusted criteria |
| 5.5 | **Audit trail** | Every verdict (structural, semantic, decision) persisted in SQLite with full evidence for replay |
| 5.6 | **Integration tests** | End-to-end: create mock PR, run full pipeline, verify verdict |
| 5.7 | **OpenClaw cleanup** | Remove or archive the stale `openclaw/` module. Its `dispatch_next` power is superseded by Pi dispatch. Its `review_pr`/`accept_node` stubs are superseded by the verification pipeline. |

---

### Summary

| Stage | Name | Tasks | New Files | Modified Files | LLM? |
|:-----:|------|:-----:|:----------:|:--------------:|:----:|
| 0 | Structural Validator | 8 | 2-3 | 0 | ❌ |
| 1 | Decision Loop | 3 | 2 | 0 | ❌ |
| 2 | Conductor Wiring | 5 | 2 | 3-4 | ❌ |
| 3 | Semantic Evaluator | 5 | 3 | 0 | ✅ |
| 4 | Shape Profiles | 4 | 2+ | 2 | ❌ |
| 5 | Hardening | 7 | 0 | 2-3 | ❌ |

**Total: ~32 tasks across 6 stages.**

Stages 0-2 are pure code and wiring — no LLM component. They produce a working verify-and-decide loop. Stages 3-4 add the semantic reasoning layer on top. Stage 5 is production hardening.

Does this decomposition feel right — the boundaries between stages, the task granularity, the ordering?

