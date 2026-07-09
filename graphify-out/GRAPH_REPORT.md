# Graph Report - gddp-runtime  (2026-07-09)

## Corpus Check
- 159 files · ~95,680 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1686 nodes · 3047 edges · 122 communities (108 shown, 14 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 326 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6a4effac`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]
- [[_COMMUNITY_Community 98|Community 98]]
- [[_COMMUNITY_Community 99|Community 99]]
- [[_COMMUNITY_Community 100|Community 100]]
- [[_COMMUNITY_Community 101|Community 101]]
- [[_COMMUNITY_Community 102|Community 102]]
- [[_COMMUNITY_Community 103|Community 103]]
- [[_COMMUNITY_Community 104|Community 104]]
- [[_COMMUNITY_Community 105|Community 105]]
- [[_COMMUNITY_Community 106|Community 106]]
- [[_COMMUNITY_Community 107|Community 107]]
- [[_COMMUNITY_Community 108|Community 108]]
- [[_COMMUNITY_Community 109|Community 109]]
- [[_COMMUNITY_Community 110|Community 110]]
- [[_COMMUNITY_Community 111|Community 111]]
- [[_COMMUNITY_Community 112|Community 112]]
- [[_COMMUNITY_Community 113|Community 113]]
- [[_COMMUNITY_Community 114|Community 114]]
- [[_COMMUNITY_Community 115|Community 115]]
- [[_COMMUNITY_Community 116|Community 116]]
- [[_COMMUNITY_Community 117|Community 117]]

## God Nodes (most connected - your core abstractions)
1. `SemanticToolbox` - 73 edges
2. `SemanticOutput` - 54 edges
3. `LLMResponse` - 42 edges
4. `_DecisionContext` - 41 edges
5. `Verdict` - 39 edges
6. `ToolCall` - 36 edges
7. `SemanticAgent` - 36 edges
8. `DeterministicResult` - 34 edges
9. `CriterionCheck` - 31 edges
10. `IntegrityOutput` - 31 edges

## Surprising Connections (you probably didn't know these)
- `Row` --uses--> `NodeData`  [INFERRED]
  scripts/runtime/heartbeat/classifier.py → scripts/runtime/heartbeat/graph_reader.py
- `Path` --uses--> `VerdictReceipt`  [INFERRED]
  scripts/runtime/verification/test_cli.py → scripts/runtime/verification/schemas.py
- `DispatchResult` --uses--> `JulesActionAdapter`  [INFERRED]
  scripts/runtime/heartbeat/dispatcher.py → scripts/adapters/jules_action_adapter.py
- `Path` --uses--> `JulesActionAdapter`  [INFERRED]
  scripts/heartbeat.py → scripts/adapters/jules_action_adapter.py
- `Row` --uses--> `JulesActionAdapter`  [INFERRED]
  scripts/heartbeat.py → scripts/adapters/jules_action_adapter.py

## Import Cycles
- None detected.

## Communities (122 total, 14 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.15
Nodes (19): context_reader.py - builds the context payload the runtime decision loop needs., Build the full context payload for one decision cycle., Load project graph and categorize nodes by status., Pull recent rows from SQLite to understand momentum and detect stale state., read_context(), read_project_state(), read_recent_activity(), in_memory_db() (+11 more)

### Community 1 - "Community 1"
Cohesion: 0.17
Nodes (26): connect(), DispatchOutcome, _execute_dispatches(), main(), _plan_dispatches(), PlannedDispatch, runner.py — Heartbeat vNext main loop.  Replaces scripts/heartbeat.py with a gra, Phase A: Fetch events, classify, scope-check, and reserve jobs on the main threa (+18 more)

### Community 2 - "Community 2"
Cohesion: 0.13
Nodes (37): Any, Path, audit(), _checkpoint_marker(), classify_command(), _contains_auth_verb(), _contains_negation(), _decision() (+29 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (18): DispatchResult, _flatten(), JulesActionAdapter, jules_action_adapter.py — Option A dispatch adapter.  Dispatches a job to Jules, Convert any YAML value (str, dict, list) to a readable string., Dispatches a job to Jules via a GitHub issue labeled 'jules'.     Jules's GitHub, Format the job packet as a structured issue body.         Jules reads this as it, TestJulesActionAdapter (+10 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (54): init_db(), init_decision_results(), _json_or_none(), _now(), results_store.py — Persistence helpers for review receipts.  Runtime return hand, Ensure the decision-loop results table exists.      Distinct from the `results`, Insert a decision-loop result row. Does NOT touch graph truth., Ensure the canonical review-receipt table exists. (+46 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (58): ArgumentParser, OpenAICompatibleRunner, Protocol, Any, LLMResponse, Path, Any, SemanticOutput (+50 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (32): _build_adapter_payload(), dispatch(), DispatchResult, dispatcher.py — Routes a job to the correct adapter.  Dispatch stays executor-dr, Build the executor packet from the persisted job payload., _init_db(), _insert_event(), _mock_id_generation() (+24 more)

### Community 7 - "Community 7"
Cohesion: 0.10
Nodes (19): 1. `dispatch_next`, 1. gddp-config graph YAML, 2. `review_pr`, 2. SQLite recent rows, 3. `accept_node`, 3. Current event, 4. `escalate`, Context Window (+11 more)

### Community 8 - "Community 8"
Cohesion: 0.12
Nodes (17): connect(), normalize_event(), now(), intake_server.py — Webhook intake server for Phase 3.  Receives raw GitHub webho, Map a raw GitHub webhook payload to our normalized event schema.     Returns Non, verify_signature(), webhook(), Test when WEBHOOK_SECRET is not set (empty string). (+9 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (89): BaseModel, Enum, IntegrityHarness, CriterionCheck, CriterionJudgment, DeterministicResult, SemanticOutput, Verdict (+81 more)

### Community 10 - "Community 10"
Cohesion: 0.06
Nodes (71): check_artifacts(), Required-artifact presence checks — ported from verify_node.py., Look for required_artifacts in repo root and a few likely spots.      merged_pr, collect_constraint_files(), evaluate_constraint(), Constraint forbidden-pattern scan — ported from verify_node.py., Files the constraints scope: explicit probe files + named source files., Scan referenced lib files for forbidden patterns. (+63 more)

### Community 11 - "Community 11"
Cohesion: 0.24
Nodes (3): _init_repo(), PasteMarkerTests, ToolGateTests

### Community 12 - "Community 12"
Cohesion: 0.05
Nodes (39): Adjacent Context: Step 4 Criteria Evaluator, Architecture A: Evaluator Is a Tool in Pi's Hands, Architecture B: Evaluator Is a Separate, Smaller Agent, Architecture C: Evaluator Is Invisible — Pi Reasons About Criteria Directly, Does This Align?, Each Verification Layer Is Independent and Produces Structured Evidence, Existing Assets, Frozen Audit Capture (+31 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (12): [1.0.0] - 2026-03-13, [1.1.0] - 2026-03-13, [1.1.1] - 2026-03-19, [1.1.2] - 2026-04-07, Added, Added, Added, Changed (+4 more)

### Community 14 - "Community 14"
Cohesion: 0.08
Nodes (22): _confidence_all_criteria(), _confidence_blocked(), _confidence_constraint_violation(), _confidence_fail_criteria(), _confidence_semantic_blend(), _criterion_satisfaction_confidence(), _DecisionContext, _mean() (+14 more)

### Community 15 - "Community 15"
Cohesion: 0.20
Nodes (9): Active Paths, Active Services, Big Pi Runbook, Canonical Commands, First Real Dispatch Preflight, Mutation Boundaries, Review Workflow, Source Of Truth (+1 more)

### Community 16 - "Community 16"
Cohesion: 0.14
Nodes (11): has_evidence_references(), Retry budget logic for the evaluator-to-executor retry loop.  When the evaluator, Check whether integrity findings contain actionable evidence references.      Fi, Determine whether a non-pass verdict should trigger an executor retry.      Cond, should_retry(), Tests for retry budget logic (evaluator-to-executor retry loop)., attempt=2 with budget=3 and max_attempts=3: one retry left., retry_budget=1 means only one retry even if max_attempts=3. (+3 more)

### Community 17 - "Community 17"
Cohesion: 0.25
Nodes (4): DispatchResult, JulesCliAdapter, jules_cli_adapter.py — Option B dispatch adapter (stub).  Dispatches a job to Ju, Dispatches a job to Jules via the Jules CLI.     More GDDP-pure than Option A: t

### Community 18 - "Community 18"
Cohesion: 0.22
Nodes (8): Host Roles — OpenClaw Topology, Intended Roles, mac — Operator Host, Pre-Cutover Blockers, Remote Access Path, ssd-big — Sole Gateway, ssd-small — Worker Node, Topology Rules

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (25): Any, Path, Any, Path, SemanticOutput, Path, build_canonical_pointers(), Canonical context builder for evaluator prompts.  Assembles file pointers (paths (+17 more)

### Community 20 - "Community 20"
Cohesion: 0.32
Nodes (3): getCurrentChapter(), jumpChapter(), updateHighlights()

### Community 21 - "Community 21"
Cohesion: 0.08
Nodes (28): accept_node.py — Propose a graph truth change by opening an evidence PR.  The de, _config_repo_slug(), _ensure_config_repo_clean(), _format_evidence_block(), _mark_node_complete_in_yaml(), open_evidence_pr(), graph_updater.py — Opens evidence-packaged PRs against gddp-config.  The decisio, Set status: complete in the project.yaml nodes list for this node. (+20 more)

### Community 22 - "Community 22"
Cohesion: 0.11
Nodes (30): _build_toolbox(), _check_stuck_jobs(), _clean_stale_state(), _connect(), handle_cron(), handle_event(), main(), engine.py - runtime decision loop.  Wake → read context → decide → act → write r (+22 more)

### Community 23 - "Community 23"
Cohesion: 0.29
Nodes (6): Autonomous Chunks, Natural Bounded Autonomy, Paste Markers, Planning, Receipts, Version Control as the Safety Net

### Community 24 - "Community 24"
Cohesion: 0.22
Nodes (8): Agent-driven development workflow, AGENTS.md — gddp-runtime, During-work rules, End-of-session contract, Handoff requirement, Not-done triggers, Project snapshot, Start-of-session contract

### Community 25 - "Community 25"
Cohesion: 0.60
Nodes (4): connect(), now(), rollback.py — Revert a job and restore node state.  Usage:     python3 scripts/r, rollback()

### Community 26 - "Community 26"
Cohesion: 0.09
Nodes (10): _fake_paths_exist(), Tests for the return-path verification bridge (E1)., The bridge must default --integrity on and respect GDDP_INTEGRITY_MODE., The CLI command includes --integrity on by default., GDDP_INTEGRITY_MODE=off passes --integrity off to the CLI., Patch the yaml/repo existence checks to pass., TestCredentialFetch, TestIntegrityFlag (+2 more)

### Community 27 - "Community 27"
Cohesion: 0.14
Nodes (17): AcceptResult, AcceptResult, EvidencePacket, Structured evidence attached to an accept_node decision., Proposes a graph truth change by opening an evidence PR against gddp-config., AcceptResult must include the evidence packet., The status literal enforces the correct value., test_accept_result_accepts_full_data() (+9 more)

### Community 28 - "Community 28"
Cohesion: 0.83
Nodes (3): _reload_module(), test_legacy_scripts_keep_opclaw_root_fallback(), test_legacy_scripts_prefer_gddp_runtime_root()

### Community 40 - "Community 40"
Cohesion: 0.29
Nodes (26): decide(), Pure function. No I/O, no LLM, no side effects., _constraint(), _criterion(), _deterministic(), _judgment(), Tests for the pure verdict decision engine., Semantic judged_fail outranks budget exhaustion (row 4 before row 7). (+18 more)

### Community 48 - "Community 48"
Cohesion: 0.12
Nodes (21): DispatchResult, EscalateResult, schema.py - Pydantic models enforcing the decision loop output contract.  Every, v0 placeholder - review_pr ships in the review-gate node., ReviewResult, Pydantic should reject a DispatchResult with missing fields., test_dispatch_result_accepts_good_data(), test_dispatch_result_rejects_bad_data() (+13 more)

### Community 49 - "Community 49"
Cohesion: 0.08
Nodes (25): Architecture, Canonical Documents, Current Limits, Environment Variables, For Engineers, For Operators & Reviewers, GDDP Runtime, Initialize the DB (+17 more)

### Community 50 - "Community 50"
Cohesion: 0.08
Nodes (24): Architecture, Current Limits, Environment Variables, For Engineers, For Operators & Reviewers, GDDP Runtime, Initialize the DB, License (+16 more)

### Community 51 - "Community 51"
Cohesion: 0.15
Nodes (12): 000 — *Session Name / Stopping Point*, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 52 - "Community 52"
Cohesion: 0.20
Nodes (9): Current state (post-hygiene), gddp-config, gddp-runtime, Gotchas, Handoff for Pi README Agent, Pi agent deliverables, Portfolio framing (Pi agent voice — quote verbatim), Project identity (+1 more)

### Community 53 - "Community 53"
Cohesion: 0.29
Nodes (6): 002 — Return-path model + vocabulary lock (conductor → verification loop), Canonical Model & Vocabulary (from Sab's vault notes — AUTHORITATIVE), Empirical Reality (AGENT ONLY) — confirmed against code this session, How to work with Sab next session (guardrails — earned the hard way this session), Narrative / Trajectory (SAB ONLY), Where Sab is now + the goal

### Community 54 - "Community 54"
Cohesion: 0.25
Nodes (7): Canonical documents, Current direction, Deeper docs, GDDP — Brief, Ground state, Known gaps / risks, Narrative

### Community 55 - "Community 55"
Cohesion: 0.18
Nodes (10): classify(), Returns a classification dict if the event maps to a dispatchable node, else Non, FakeEvent, FakeNode, _issue_event(), Tests for classifier node-tag matching (item 1.5 hardening)., Minimal stand-in for graph_reader.NodeData., Dict-like stand-in for a sqlite3.Row used by the classifier. (+2 more)

### Community 56 - "Community 56"
Cohesion: 0.18
Nodes (16): Any, IntegrityOutput, Path, Path, _build_integrity_prompt(), _empty_integrity(), _neighbor_pointers(), Pi-harness runner for the integrity lane (lane 2: fresh-eyes drift review).  Sib (+8 more)

### Community 57 - "Community 57"
Cohesion: 0.50
Nodes (3): 001 — Repo Hygeine and Sanity Checking README, Empirical Reality (AGENT ONLY), Narrative / Trajectory (SAB ONLY)

### Community 60 - "Community 60"
Cohesion: 0.16
Nodes (11): GraphReader, ProjectGraph, graph_reader.py — Reads gddp-config YAML and returns graph state.  Replaces the, Returns nodes that are status=ready in project.yaml AND have a node YAML file., check_scope(), scope_checker.py — Guards against duplicate dispatch.  Before creating a job, ve, Returns ScopeCheckResult. safe=True means it is OK to dispatch., ScopeCheckResult (+3 more)

### Community 61 - "Community 61"
Cohesion: 0.11
Nodes (17): 030 — Terminology Lock, Canon Declaration, Fleet Sync, Artifacts (Filepath - Description, 1 line max per artifact), Canon documents (the list; small, human-owned, wins over all other prose), Constrained areas touched (none / list + justification), Coupling hazard for the next agent, Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated (+9 more)

### Community 62 - "Community 62"
Cohesion: 0.36
Nodes (15): DecisionContext, ProjectState, RecentActivity, NoOpResult, Nothing to do — all nodes complete or blocked, no stale state., _context(), FakeConnection, _node() (+7 more)

### Community 63 - "Community 63"
Cohesion: 0.16
Nodes (8): _build_decision_loop_runner(), _LazyRunner, Builds a semantic runner lazily, using the same env-based provider     resolutio, Resolve a semantic runner from the environment.      Priority: DEEPSEEK_API_KEY, Tests for the decision loop's runner resolution (item 1.1).  Verifies that _buil, When no API keys are set and anthropic is not installed, the         decision lo, The _LazyRunner class used by _run_verification must build a         runner with, TestRunnerResolution

### Community 64 - "Community 64"
Cohesion: 0.12
Nodes (15): Cleanup, Core model, Environment, GDDP Verification Module — Parallel Build Setup, Per-agent stop condition, Pre-work on main, Quick reference, Shared shape profile interface (+7 more)

### Community 65 - "Community 65"
Cohesion: 0.13
Nodes (14): Canonical direction, Execution + commit policy, GDDP — Implementation Plan, How the pieces fit, Open (Sab decides), Phase 0 — Pre-work / dependency gate, Phase 1 — Structural validator + decision engine (build Wave 1), Phase 2 — Conductor / return-path wiring (build Wave 2, standalone) (+6 more)

### Community 66 - "Community 66"
Cohesion: 0.25
Nodes (7): _mem_con(), _Node, Tests for X2 hardening: event claiming and the awaiting_review dispatch guard., The claim UPDATE in runner._plan_dispatches: exercised at SQL level., TestAwaitingReviewGuard, TestEventClaiming, Connection

### Community 67 - "Community 67"
Cohesion: 0.15
Nodes (12): 017 - Verdict confidence split, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 68 - "Community 68"
Cohesion: 0.15
Nodes (12): 018 - Runtime receipt proves node evidence attachment, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 69 - "Community 69"
Cohesion: 0.15
Nodes (12): 019 — Reconciliation baseline + verdict-confidence-split evidence, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 70 - "Community 70"
Cohesion: 0.15
Nodes (12): 020 — Verifier harness allows python; clean scan-vault-core live receipt, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 71 - "Community 71"
Cohesion: 0.15
Nodes (12): 021 — Pi harness for the semantic evaluator (visibility), Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 72 - "Community 72"
Cohesion: 0.15
Nodes (12): 022 — Pi harness guard: broad inputs, enforced outputs, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 73 - "Community 73"
Cohesion: 0.15
Nodes (12): 023 — Calibrated Baseline Run + Constraint-Checker Fix, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 74 - "Community 74"
Cohesion: 0.15
Nodes (12): 024 — First live pi trials + guard/trace fixes, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 75 - "Community 75"
Cohesion: 0.15
Nodes (12): 025 — Evidence-scope rule + two-node rerun (self-referential vs baseline), Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 76 - "Community 76"
Cohesion: 0.15
Nodes (12): 026 — Return-path bridge: evaluator auto-runs on merged PR (E1+E2), Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 77 - "Community 77"
Cohesion: 0.15
Nodes (12): 027 — Hardening: E3 command_proof + X2 claiming, both proven live, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 78 - "Community 78"
Cohesion: 0.15
Nodes (12): 028 — Pathway hardening spec: Phase 1 + Phase 2 implementation, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 79 - "Community 79"
Cohesion: 0.15
Nodes (12): 029 — Pi-Big Live Intake: Webhooks, Secrets, Funnel, Artifacts (Filepath - Description, 1 line max per artifact), Constrained areas touched (none / list + justification), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went (+4 more)

### Community 80 - "Community 80"
Cohesion: 0.17
Nodes (11): 029 Artifact — Pi-Big Live Intake: System State & Runbook, Event flow (end to end), gddp-intake.service (systemd), GitHub webhooks (all owner `skchaudr`), Health check (run this first when picking up), Heartbeat (cron on pi-big), Host topology, Not yet done / next (+3 more)

### Community 81 - "Community 81"
Cohesion: 0.17
Nodes (11): 012 - Semantic verifier typed verdict hardening, Artifacts (Filepath - Description, 1 line max per artifact), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went, Narrative / Trajectory (SAB ONLY) (+3 more)

### Community 82 - "Community 82"
Cohesion: 0.17
Nodes (11): 013 - Verifier receipt compatibility, Artifacts (Filepath - Description, 1 line max per artifact), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went, Narrative / Trajectory (SAB ONLY) (+3 more)

### Community 83 - "Community 83"
Cohesion: 0.17
Nodes (11): 014 - Verifier CLI real receipt run, Artifacts (Filepath - Description, 1 line max per artifact), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went, Narrative / Trajectory (SAB ONLY) (+3 more)

### Community 84 - "Community 84"
Cohesion: 0.17
Nodes (11): 015 - Live semantic verifier runner, Artifacts (Filepath - Description, 1 line max per artifact), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went, Narrative / Trajectory (SAB ONLY) (+3 more)

### Community 85 - "Community 85"
Cohesion: 0.17
Nodes (11): Acceptance criteria, Deliverables, Execution plan (on `sab-air`), Ground-truth current state (on `sab-air`, branch `main`), In scope, Mission 001 — Harden Semantic Verification, Out of scope, Post-mission (do not start until this mission is closed) (+3 more)

### Community 86 - "Community 86"
Cohesion: 0.18
Nodes (10): 1. bridge._parse_cli_summary, 2. cli.py summary printing, 3. receipt_sink.py, 4. return_router.py, 5. Existing receipts in gddp-config/verification-runtime-live/, 6. test_bridge.py, 7. test_return_router.py, Conclusion (+2 more)

### Community 87 - "Community 87"
Cohesion: 0.31
Nodes (8): load_shape_profile(), Read-only shape profile loader for the semantic verification agent., Load ``<project_type>.yaml`` from this package directory, or return None., _assert_valid_profile(), Tests for the read-only shape profile loader., test_load_cli_tool_profile(), test_load_nonexistent_profile_returns_none(), test_load_runtime_orchestrator_profile()

### Community 88 - "Community 88"
Cohesion: 0.22
Nodes (8): Cleanup, Environment, GDDP Verification Module — Parallel Build Setup, Pre-work on main (one commit, before any branching), Quick reference, Wave 1 — Tasks 1 + 2 in parallel, Wave 2 — Task 3 standalone, Wave 3 — Tasks 4 + 5 in parallel

### Community 89 - "Community 89"
Cohesion: 0.25
Nodes (7): Config contract (gddp-config, human-authored truth), Constraints, Definition of done, E3 spec — command_proof probe for the deterministic layer, Goal, Runtime behavior (gddp-runtime), Tests (deterministic/test_deterministic.py style)

### Community 90 - "Community 90"
Cohesion: 0.25
Nodes (7): Commit 1 — schemas.py (the receipt contract), Commit 2 — integrity_combiner.py (the authority boundary), Commit 3 — orchestrator.py (where lane 2 runs), Commit 4 — gddp_integrity.ts (the model's only output channel), Finding you should see first, Not in this branch (deliberately), Walkthrough: integrity-lane-draft branch

### Community 91 - "Community 91"
Cohesion: 0.25
Nodes (7): Doctrine terms currently binding (from session decisions — confirm as Accepted), Flagged fields, Impact-scan surfaces (for Sab's Pi, if schema/validation changes land), Known Non-canonical (agent-invented, never approved), Node YAML schema (53 nodes, 6 graphs, perfectly uniform — every node has all 15 fields), Reconciliation Inventory — raw vocabulary sweep (2026-07-07), Runtime vocabularies (all in active code — Schema at minimum; doctrine status is Sab's call)

### Community 93 - "Community 93"
Cohesion: 0.29
Nodes (6): 12. Per-Task Stop Condition, 14. Hard Constraints, 15. Resolved Decisions, 2. Architecture, Data flow (one wake cycle), GDDP Verification Engine — Specification

### Community 94 - "Community 94"
Cohesion: 0.29
Nodes (7): 4.1 Model, 4.2 Tool whitelist (read-only, always available), 4.3 Loop mechanics, 4.4 SemanticOutput schema, 4.5 LLM runner abstraction, 4.6 Bounded and testable, 4. Phase 2 — Semantic Investigation (Agentic)

### Community 95 - "Community 95"
Cohesion: 0.29
Nodes (6): Acceptance sketch (for node YAML, Sab authors final), Constraints, Doctrine (verbatim intent), Open for Sab, Spec: Integrity Lane — always-on evaluator mandate (evaluator-intent-integrity-verdict), v1 design (lean)

### Community 96 - "Community 96"
Cohesion: 0.29
Nodes (6): _pick_executor(), classifier.py — Maps implementation requests to ready nodes.  The heartbeat only, Places a `node: <id>` tag may legitimately appear., Pick the first declared execution mode, preserving graph ordering., _tag_sources(), NodeData

### Community 97 - "Community 97"
Cohesion: 0.43
Nodes (6): build_job(), now(), job_factory.py — Builds a job payload from a NodeData and event.  Returns a plai, ts_id(), Path, Row

### Community 98 - "Community 98"
Cohesion: 0.33
Nodes (5): 1. Architectural Paradigms: Control Flow and State Management, 2. Evaluation Strategies: Trajectory Optimization & Trust, 3. Empirical Findings (2024-2026 Research Snapshot), Conclusion, SOTA Graph-Driven Agent Frameworks vs. GDDP Manual Gating: A Critical Benchmark Matrix

### Community 99 - "Community 99"
Cohesion: 0.33
Nodes (6): 5.1 Principle, 5.2 Precedence (load-bearing), 5.3 Decision matrix (in evaluation order), 5.4 Confidence, 5.5 Implementation shape, 5. Phase 3 — Decision Engine (Pure, Deterministic)

### Community 100 - "Community 100"
Cohesion: 0.33
Nodes (6): 6.1 Schema location, 6.2 Profile location, 6.3 Schema shape, 6.4 Project binding, 6.5 Initial profiles (4), 6. Shape Profiles

### Community 101 - "Community 101"
Cohesion: 0.33
Nodes (5): 016 — Semantic Loop Budget Trace And Completion Boundary, Interpretation, Summary, Validation, What changed

### Community 102 - "Community 102"
Cohesion: 0.40
Nodes (5): asText(), execute(), IntegrityFindingSchema, SubmitIntegrityVerdictArgs, SubmitIntegrityVerdictParams

### Community 103 - "Community 103"
Cohesion: 0.40
Nodes (5): asText(), execute(), JudgmentSchema, SubmitVerdictArgs, SubmitVerdictParams

### Community 105 - "Community 105"
Cohesion: 0.40
Nodes (5): 8.1 Replace `review_pr`, 8.2 Trigger, 8.3 Decision-loop spec update, 8.4 Decision-loop-runtime node update, 8. Integration with Decision Loop

### Community 106 - "Community 106"
Cohesion: 0.50
Nodes (3): For Engineers, What This Is, Why This Matters

### Community 107 - "Community 107"
Cohesion: 0.50
Nodes (4): 11. Build Waves, Wave 1 — Deterministic port + Decision engine (parallel, 2 branches), Wave 2 — Conductor wiring (standalone, 1 branch), Wave 3 — Semantic agent + Shape profiles (parallel, 2 branches)

### Community 108 - "Community 108"
Cohesion: 0.50
Nodes (4): 13.1 Unit tests (per module, no LLM, no network), 13.2 Integration test (dry_run.py extension), 13.3 Receipt auditability, 13. Test Strategy

### Community 109 - "Community 109"
Cohesion: 0.50
Nodes (4): 3.1 Source, 3.2 Taxonomy preservation, 3.3 Gate logic (by kind, not pass/fail), 3. Phase 1 — Deterministic Floor

### Community 110 - "Community 110"
Cohesion: 0.50
Nodes (3): Constraints, Deliverables (commit each as its own conventional commit on this branch), Task: implement the integrity lane (fresh-eyes drift review)

### Community 111 - "Community 111"
Cohesion: 0.67
Nodes (3): 10.1 Items, 10.2 DoD for pre-work, 10. Pre-Work on Main (Before Any Branching)

### Community 112 - "Community 112"
Cohesion: 0.67
Nodes (3): 1. Purpose, System roles (unchanged), What changed from the prior plan

### Community 113 - "Community 113"
Cohesion: 0.67
Nodes (3): 7.1 VerdictReceipt (Pydantic), 7.2 Persistence, 7. Receipt and Verdict Output

### Community 114 - "Community 114"
Cohesion: 0.67
Nodes (3): 9.1 New dependency, 9.2 Pydantic, 9. LLM Dependency

## Knowledge Gaps
- **484 isolated node(s):** `setup.sh script`, `DecisionContext`, `Any`, `AcceptResult`, `EscalateResult` (+479 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GraphReader` connect `Community 60` to `Community 0`, `Community 1`, `Community 22`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Why does `SemanticOutput` connect `Community 9` to `Community 40`, `Community 19`, `Community 5`, `Community 14`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `Verdict` connect `Community 9` to `Community 40`, `Community 5`, `Community 22`, `Community 14`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 30 inferred relationships involving `SemanticToolbox` (e.g. with `ArgumentParser` and `OpenAICompatibleRunner`) actually correct?**
  _`SemanticToolbox` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 41 inferred relationships involving `SemanticOutput` (e.g. with `IntegrityHarness` and `CriterionCheck`) actually correct?**
  _`SemanticOutput` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `LLMResponse` (e.g. with `ArgumentParser` and `OpenAICompatibleRunner`) actually correct?**
  _`LLMResponse` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `_DecisionContext` (e.g. with `CriterionCheck` and `CriterionJudgment`) actually correct?**
  _`_DecisionContext` has 5 INFERRED edges - model-reasoned connections that need verification._