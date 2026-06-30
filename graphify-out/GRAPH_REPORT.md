# Graph Report - gddp-runtime  (2026-06-24)

## Corpus Check
- 79 files · ~43,810 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 698 nodes · 1028 edges · 60 communities (51 shown, 9 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 26 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `GraphReader` - 19 edges
2. `handle_merged_pr()` - 16 edges
3. `open_evidence_pr()` - 14 edges
4. `_plan_dispatches()` - 14 edges
5. `GDDP Runtime` - 14 edges
6. `GDDP Runtime` - 14 edges
7. `evaluate_pre_tool_use()` - 13 edges
8. `JulesActionAdapter` - 13 edges
9. `TestJulesActionAdapter` - 13 edges
10. `handle_event()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `DispatchResult` --uses--> `JulesActionAdapter`  [INFERRED]
  scripts/runtime/heartbeat/dispatcher.py → scripts/adapters/jules_action_adapter.py
- `Path` --uses--> `JulesActionAdapter`  [INFERRED]
  scripts/heartbeat.py → scripts/adapters/jules_action_adapter.py
- `Row` --uses--> `JulesActionAdapter`  [INFERRED]
  scripts/heartbeat.py → scripts/adapters/jules_action_adapter.py
- `DecisionResult` --uses--> `DecisionContext`  [INFERRED]
  scripts/runtime/decision_loop/engine.py → scripts/runtime/decision_loop/context_reader.py
- `Connection` --uses--> `DecisionContext`  [INFERRED]
  scripts/runtime/decision_loop/engine.py → scripts/runtime/decision_loop/context_reader.py

## Import Cycles
- None detected.

## Communities (60 total, 9 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.15
Nodes (21): DecisionContext, ProjectState, context_reader.py - builds the context payload the runtime decision loop needs., Build the full context payload for one decision cycle., Load project graph and categorize nodes by status., Pull recent rows from SQLite to understand momentum and detect stale state., read_context(), read_project_state() (+13 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (50): classify(), _pick_executor(), classifier.py — Maps implementation requests to ready nodes.  The heartbeat only, Returns a classification dict if the event maps to a dispatchable node, else Non, Pick the first declared execution mode, preserving graph ordering., GraphReader, NodeData, ProjectGraph (+42 more)

### Community 2 - "Community 2"
Cohesion: 0.13
Nodes (37): Any, Path, audit(), _checkpoint_marker(), classify_command(), _contains_auth_verb(), _contains_negation(), _decision() (+29 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (18): DispatchResult, _flatten(), JulesActionAdapter, jules_action_adapter.py — Option A dispatch adapter.  Dispatches a job to Jules, Convert any YAML value (str, dict, list) to a readable string., Dispatches a job to Jules via a GitHub issue labeled 'jules'.     Jules's GitHub, Format the job packet as a structured issue body.         Jules reads this as it, TestJulesActionAdapter (+10 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (30): init_db(), init_decision_results(), _json_or_none(), _now(), results_store.py — Persistence helpers for review receipts.  Runtime return hand, Ensure the decision-loop results table exists.      Distinct from the `results`, Insert a decision-loop result row. Does NOT touch graph truth., Ensure the canonical review-receipt table exists. (+22 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (24): Architecture, Current Limits, Environment Variables, For Engineers, For Operators & Reviewers, GDDP Runtime, Initialize the DB, License (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.20
Nodes (15): _build_adapter_payload(), dispatch(), DispatchResult, dispatcher.py — Routes a job to the correct adapter.  Dispatch stays executor-dr, Build the executor packet from the persisted job payload., _init_db(), _insert_event(), _mock_id_generation() (+7 more)

### Community 7 - "Community 7"
Cohesion: 0.10
Nodes (19): 1. `dispatch_next`, 1. gddp-config graph YAML, 2. `review_pr`, 2. SQLite recent rows, 3. `accept_node`, 3. Current event, 4. `escalate`, Context Window (+11 more)

### Community 8 - "Community 8"
Cohesion: 0.13
Nodes (17): connect(), normalize_event(), now(), intake_server.py — Webhook intake server for Phase 3.  Receives raw GitHub webho, Map a raw GitHub webhook payload to our normalized event schema.     Returns Non, verify_signature(), webhook(), Test when WEBHOOK_SECRET is not set (empty string). (+9 more)

### Community 9 - "Community 9"
Cohesion: 0.05
Nodes (39): Adjacent Context: Step 4 Criteria Evaluator, Architecture A: Evaluator Is a Tool in Pi's Hands, Architecture B: Evaluator Is a Separate, Smaller Agent, Architecture C: Evaluator Is Invisible — Pi Reasons About Criteria Directly, Does This Align?, Each Verification Layer Is Independent and Produces Structured Evidence, Existing Assets, Frozen Audit Capture (+31 more)

### Community 10 - "Community 10"
Cohesion: 0.12
Nodes (15): Cleanup, Core model, Environment, GDDP Verification Module — Parallel Build Setup, Per-agent stop condition, Pre-work on main, Quick reference, Shared shape profile interface (+7 more)

### Community 11 - "Community 11"
Cohesion: 0.24
Nodes (3): _init_repo(), PasteMarkerTests, ToolGateTests

### Community 12 - "Community 12"
Cohesion: 0.40
Nodes (13): classify_and_scope(), connect(), create_job(), enqueue(), inject_event(), job_dir(), main(), now() (+5 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (12): [1.0.0] - 2026-03-13, [1.1.0] - 2026-03-13, [1.1.1] - 2026-03-19, [1.1.2] - 2026-04-07, Added, Added, Added, Changed (+4 more)

### Community 14 - "Community 14"
Cohesion: 0.21
Nodes (7): connect(), main(), replay.py — Replay failed or partial runtime steps from persisted state.  Usage:, replay_job(), replay_result(), test_replay.py — Tests for the replay logic., TestReplay

### Community 15 - "Community 15"
Cohesion: 0.20
Nodes (9): Active Paths, Active Service, Big Pi Runbook, Canonical Commands, First Real Dispatch Preflight, Mutation Boundaries, Review Workflow, Source Of Truth (+1 more)

### Community 16 - "Community 16"
Cohesion: 0.08
Nodes (24): Architecture, Current Limits, Environment Variables, For Engineers, For Operators & Reviewers, GDDP Runtime, Initialize the DB, License (+16 more)

### Community 17 - "Community 17"
Cohesion: 0.25
Nodes (4): DispatchResult, JulesCliAdapter, jules_cli_adapter.py — Option B dispatch adapter (stub).  Dispatches a job to Ju, Dispatches a job to Jules via the Jules CLI.     More GDAD-pure than Option A: t

### Community 18 - "Community 18"
Cohesion: 0.22
Nodes (8): Host Roles — OpenClaw Topology, Intended Roles, mac — Operator Host, Pre-Cutover Blockers, Remote Access Path, ssd-big — Sole Gateway, ssd-small — Worker Node, Topology Rules

### Community 19 - "Community 19"
Cohesion: 0.22
Nodes (8): Cleanup, Environment, GDDP Verification Module — Parallel Build Setup, Pre-work on main (one commit, before any branching), Quick reference, Wave 1 — Tasks 1 + 2 in parallel, Wave 2 — Task 3 standalone, Wave 3 — Tasks 4 + 5 in parallel

### Community 20 - "Community 20"
Cohesion: 0.32
Nodes (3): getCurrentChapter(), jumpChapter(), updateHighlights()

### Community 21 - "Community 21"
Cohesion: 0.09
Nodes (27): _config_repo_slug(), _ensure_config_repo_clean(), _format_evidence_block(), _mark_node_complete_in_yaml(), open_evidence_pr(), graph_updater.py — Opens evidence-packaged PRs against gddp-config.  The decisio, Set status: complete in the project.yaml nodes list for this node., Format the evidence packet as a markdown PR body. (+19 more)

### Community 22 - "Community 22"
Cohesion: 0.15
Nodes (20): _check_stuck_jobs(), _clean_stale_state(), _connect(), handle_cron(), handle_event(), engine.py - runtime decision loop.  Wake → read context → decide → act → write r, Main entry point — called by webhook router or cron.      Args:         trigger:, Cron entry point — same logic, cron trigger. (+12 more)

### Community 23 - "Community 23"
Cohesion: 0.29
Nodes (6): Autonomous Chunks, Natural Bounded Autonomy, Paste Markers, Planning, Receipts, Version Control as the Safety Net

### Community 24 - "Community 24"
Cohesion: 0.20
Nodes (9): Agent-driven development workflow, AGENTS.md — gddp-runtime, During-work rules, End-of-session contract, Environment, Handoff requirement, Not-done triggers, Project snapshot (+1 more)

### Community 25 - "Community 25"
Cohesion: 0.60
Nodes (4): connect(), now(), rollback.py — Revert a job and restore node state.  Usage:     python3 scripts/r, rollback()

### Community 26 - "Community 26"
Cohesion: 0.50
Nodes (3): For Engineers, What This Is, Why This Matters

### Community 27 - "Community 27"
Cohesion: 0.14
Nodes (17): AcceptResult, AcceptResult, EvidencePacket, Structured evidence attached to an accept_node decision., Proposes a graph truth change by opening an evidence PR against gddp-config., AcceptResult must include the evidence packet., The status literal enforces the correct value., test_accept_result_accepts_full_data() (+9 more)

### Community 28 - "Community 28"
Cohesion: 0.83
Nodes (3): _reload_module(), test_legacy_scripts_keep_opclaw_root_fallback(), test_legacy_scripts_prefer_gddp_runtime_root()

### Community 48 - "Community 48"
Cohesion: 0.19
Nodes (11): BaseModel, DispatchResult, EscalateResult, schema.py - Pydantic models enforcing the decision loop output contract.  Every, v0 placeholder - review_pr ships in the review-gate node., ReviewResult, Pydantic should reject a DispatchResult with missing fields., test_dispatch_result_rejects_bad_data() (+3 more)

### Community 49 - "Community 49"
Cohesion: 0.13
Nodes (14): Canonical direction, Execution + commit policy, GDDP — Implementation Plan, How the pieces fit, Open (Sab decides), Phase 0 — Pre-work / dependency gate, Phase 1 — Structural validator + decision engine (build Wave 1), Phase 2 — Conductor / return-path wiring (build Wave 2, standalone) (+6 more)

### Community 50 - "Community 50"
Cohesion: 0.18
Nodes (13): dispatch_next should escalate if a job is already active., test_dispatch_blocked_when_job_active(), DispatchResult, _build_issue_body(), _find_eligible_node(), _has_active_job(), Find the highest-priority pending node whose dependencies are all complete., Check if there's already a dispatched/running job for this project. (+5 more)

### Community 51 - "Community 51"
Cohesion: 0.17
Nodes (11): 000 — *Session Name / Stopping Point*, Artifacts (Filepath - Description, 1 line max per artifact), Current Git state (2-3 sentences max, anything more must be critically justifiable), Empirical Reality (2-3 sentences max, anything more must be critically justifiable), Friction experienced or anticipated, Intent going into/at start of session, Interpretation of how the session went, Narrative / Trajectory (SAB ONLY) (+3 more)

### Community 52 - "Community 52"
Cohesion: 0.20
Nodes (9): Current state (post-hygiene), gddp-config, gddp-runtime, Gotchas, Handoff for Pi README Agent, Pi agent deliverables, Portfolio framing (Pi agent voice — quote verbatim), Project identity (+1 more)

### Community 53 - "Community 53"
Cohesion: 0.29
Nodes (6): 002 — Return-path model + vocabulary lock (conductor → verification loop), Canonical Model & Vocabulary (from Sab's vault notes — AUTHORITATIVE), Empirical Reality (AGENT ONLY) — confirmed against code this session, How to work with Sab next session (guardrails — earned the hard way this session), Narrative / Trajectory (SAB ONLY), Where Sab is now + the goal

### Community 54 - "Community 54"
Cohesion: 0.29
Nodes (6): Current direction, Deeper docs, GDDP — Brief, Ground state, Known gaps / risks, Narrative

### Community 55 - "Community 55"
Cohesion: 0.33
Nodes (5): 1. Architectural Paradigms: Control Flow and State Management, 2. Evaluation Strategies: Trajectory Optimization & Trust, 3. Empirical Findings (2024-2026 Research Snapshot), Conclusion, SOTA Graph-Driven Agent Frameworks vs. GDDP Manual Gating: A Critical Benchmark Matrix

### Community 56 - "Community 56"
Cohesion: 0.50
Nodes (4): test_escalate_returns_valid_schema(), Create an escalation result. The engine handles writing it to SQLite., run(), EscalateResult

### Community 57 - "Community 57"
Cohesion: 0.50
Nodes (3): 001 — Repo Hygeine and Sanity Checking README, Empirical Reality (AGENT ONLY), Narrative / Trajectory (SAB ONLY)

## Knowledge Gaps
- **203 isolated node(s):** `setup.sh script`, `DecisionContext`, `Any`, `AcceptResult`, `EscalateResult` (+198 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GraphReader` connect `Community 1` to `Community 0`, `Community 22`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `open_evidence_pr()` connect `Community 21` to `Community 48`, `Community 27`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `JulesActionAdapter` connect `Community 3` to `Community 6`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `GraphReader` (e.g. with `DispatchOutcome` and `PlannedDispatch`) actually correct?**
  _`GraphReader` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Return (kind, text, start_line) segments where kind is operator|paste.`, `Return the git toplevel for path's directory, or None if not in a repo.`, `Return a short-circuit decision if the write is unsafe, else None to proceed.` to the rest of the system?**
  _298 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.14624505928853754 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07213114754098361 - nodes in this community are weakly interconnected._