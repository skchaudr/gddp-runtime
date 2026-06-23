# Graph Report - gddp-runtime  (2026-06-18)

## Corpus Check
- 71 files · ~32,510 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 539 nodes · 833 edges · 48 communities (39 shown, 9 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 26 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `bb1997ed`
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

## God Nodes (most connected - your core abstractions)
1. `GraphReader` - 19 edges
2. `handle_merged_pr()` - 16 edges
3. `_plan_dispatches()` - 14 edges
4. `GDDP Runtime` - 14 edges
5. `evaluate_pre_tool_use()` - 13 edges
6. `JulesActionAdapter` - 13 edges
7. `TestJulesActionAdapter` - 13 edges
8. `handle_event()` - 12 edges
9. `run()` - 12 edges
10. `NodeData` - 12 edges

## Surprising Connections (you probably didn't know these)
- `DispatchResult` --uses--> `JulesActionAdapter`  [INFERRED]
  scripts/runtime/heartbeat/dispatcher.py → scripts/adapters/jules_action_adapter.py
- `Path` --uses--> `JulesActionAdapter`  [INFERRED]
  scripts/heartbeat.py → scripts/adapters/jules_action_adapter.py
- `Row` --uses--> `JulesActionAdapter`  [INFERRED]
  scripts/heartbeat.py → scripts/adapters/jules_action_adapter.py
- `Row` --uses--> `NodeData`  [INFERRED]
  scripts/runtime/heartbeat/classifier.py → scripts/runtime/heartbeat/graph_reader.py
- `TestJulesActionAdapter` --uses--> `DispatchResult`  [INFERRED]
  scripts/adapters/test_jules_action_adapter.py → scripts/adapters/jules_action_adapter.py

## Import Cycles
- None detected.

## Communities (48 total, 9 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (69): BaseModel, DecisionContext, ProjectState, context_reader.py - builds the context payload the runtime decision loop needs., Build the full context payload for one decision cycle., Load project graph and categorize nodes by status., Pull recent rows from SQLite to understand momentum and detect stale state., read_context() (+61 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (45): classify(), _pick_executor(), classifier.py — Maps implementation requests to ready nodes.  The heartbeat only, Returns a classification dict if the event maps to a dispatchable node, else Non, Pick the first declared execution mode, preserving graph ordering., GraphReader, NodeData, ProjectGraph (+37 more)

### Community 2 - "Community 2"
Cohesion: 0.13
Nodes (37): Any, Path, audit(), _checkpoint_marker(), classify_command(), _contains_auth_verb(), _contains_negation(), _decision() (+29 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (18): DispatchResult, _flatten(), JulesActionAdapter, jules_action_adapter.py — Option A dispatch adapter.  Dispatches a job to Jules, Convert any YAML value (str, dict, list) to a readable string., Dispatches a job to Jules via a GitHub issue labeled 'jules'.     Jules's GitHub, Format the job packet as a structured issue body.         Jules reads this as it, TestJulesActionAdapter (+10 more)

### Community 4 - "Community 4"
Cohesion: 0.13
Nodes (16): _connect(), handle_merged_pr(), _load_job(), _mark_job_awaiting_review(), parse_job_id(), parse_node_id(), return_router.py — Convert merged PR events into review receipts.  Runtime does, Extract `node: <node_id>` from the PR body. (+8 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (24): Architecture, Current Limits, Environment Variables, For Engineers, For Operators & Reviewers, GDDP Runtime, Initialize the DB, License (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (21): _build_adapter_payload(), dispatch(), DispatchResult, dispatcher.py — Routes a job to the correct adapter.  Dispatch stays executor-dr, Build the executor packet from the persisted job payload., build_job(), now(), job_factory.py — Builds a job payload from a NodeData and event.  Returns a plai (+13 more)

### Community 7 - "Community 7"
Cohesion: 0.10
Nodes (19): 1. `dispatch_next`, 1. gddp-config graph YAML, 2. `review_pr`, 2. SQLite recent rows, 3. `accept_node`, 3. Current event, 4. `escalate`, Context Window (+11 more)

### Community 8 - "Community 8"
Cohesion: 0.13
Nodes (17): connect(), normalize_event(), now(), intake_server.py — Webhook intake server for Phase 3.  Receives raw GitHub webho, Map a raw GitHub webhook payload to our normalized event schema.     Returns Non, verify_signature(), webhook(), Test when WEBHOOK_SECRET is not set (empty string). (+9 more)

### Community 9 - "Community 9"
Cohesion: 0.19
Nodes (14): init_db(), init_decision_results(), _json_or_none(), _now(), results_store.py — Persistence helpers for review receipts.  Runtime return hand, Ensure the decision-loop results table exists.      Distinct from the `results`, Insert a decision-loop result row. Does NOT touch graph truth., Ensure the canonical review-receipt table exists. (+6 more)

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
Cohesion: 0.20
Nodes (9): Current state (post-hygiene), gddp-config, gddp-runtime, Gotchas, Handoff for Pi README Agent, Pi agent deliverables, Portfolio framing (Pi agent voice — quote verbatim), Project identity (+1 more)

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
Cohesion: 0.29
Nodes (6): graph_updater.py — Disabled runtime graph mutation entrypoint.  Graph and gddp-c, Legacy compatibility stub.      Returns a disabled response instead of mutating, update_graph_node_complete(), test_graph_updater.py — Verifies runtime graph mutation stays disabled., test_update_graph_node_complete_is_disabled(), Any

### Community 22 - "Community 22"
Cohesion: 0.29
Nodes (6): 002 — Return-path model + vocabulary lock (conductor → verification loop), Canonical Model & Vocabulary (from Sab's vault notes — AUTHORITATIVE), Empirical Reality (AGENT ONLY) — confirmed against code this session, How to work with Sab next session (guardrails — earned the hard way this session), Narrative / Trajectory (SAB ONLY), Where Sab is now + the goal

### Community 23 - "Community 23"
Cohesion: 0.29
Nodes (6): Autonomous Chunks, Natural Bounded Autonomy, Paste Markers, Planning, Receipts, Version Control as the Safety Net

### Community 24 - "Community 24"
Cohesion: 0.33
Nodes (5): AGENTS.md — gddp-runtime, Environment, Message envelope, Operator relay, Project snapshot

### Community 25 - "Community 25"
Cohesion: 0.60
Nodes (4): connect(), now(), rollback.py — Revert a job and restore node state.  Usage:     python3 scripts/r, rollback()

### Community 26 - "Community 26"
Cohesion: 0.50
Nodes (3): For Engineers, What This Is, Why This Matters

### Community 27 - "Community 27"
Cohesion: 0.50
Nodes (3): 001 — Repo Hygeine and Sanity Checking README, Empirical Reality (AGENT ONLY), Narrative / Trajectory (SAB ONLY)

### Community 28 - "Community 28"
Cohesion: 0.83
Nodes (3): _reload_module(), test_legacy_scripts_keep_opclaw_root_fallback(), test_legacy_scripts_prefer_gddp_runtime_root()

## Knowledge Gaps
- **117 isolated node(s):** `setup.sh script`, `DispatchResult`, `EscalateResult`, `EscalateResult`, `Any` (+112 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GraphReader` connect `Community 1` to `Community 0`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `JulesActionAdapter` connect `Community 3` to `Community 6`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `DispatchResult` connect `Community 6` to `Community 3`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `GraphReader` (e.g. with `DispatchOutcome` and `PlannedDispatch`) actually correct?**
  _`GraphReader` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Return (kind, text, start_line) segments where kind is operator|paste.`, `Return the git toplevel for path's directory, or None if not in a repo.`, `Return a short-circuit decision if the write is unsafe, else None to proceed.` to the rest of the system?**
  _197 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05261261261261261 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.08246753246753247 - nodes in this community are weakly interconnected._