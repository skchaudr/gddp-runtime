# 090 — Stage 0 keep/strip map (work order 089)

**Executor:** Kimi. **Date:** 2026-08-10. **Status:** awaiting Sab's signature.
No code moved. Line counts measured on `main` @ `e4d4bbc` (post-drift-gate
removal). §2.3 test applied per row: *if this returned "no", would a
retrievable commit fail to be judged?* Yes → governance → strip/demote.

Legend: **KEEP** transport · **STRIP** deleted · **DEMOTE** survives as
recorded observation, loses the power to stop evaluation (the written Stage 2/3
dispositions, not a lighter gate) · **FIX** the one permitted add (§4).

## mission_adapter.py — 851 lines (transport shell)

| Function | Lines | Verdict | BM | Tests that die | Justification |
|---|---|---|---|---|---|
| `__init__` | 49 | KEEP | — | none | Env/model wiring; no verdict power. |
| `dispatch` | 7 | KEEP | — | none | Single-node launch. |
| `supports_engagement` | 2 | KEEP | — | none | Capability flag. |
| `dispatch_engagement` | 215 | KEEP+surgery | 019, 020 | `test_dispatch_rejects_packets_with_different_expected_bases` (rewritten per SOFTEN) | Launch machinery is transport; the two base gates decide "no" on retrievable work. BM-020's exact-checkout check dies outright; BM-019 softens (f53baae already normalizes bases upstream). |
| `status` | 42 | KEEP | — | none | Poll transport. |
| `collect` / `collect_engagement` | 21 | KEEP | — | none | Collection entry. |
| `completed_feature_ids` | 29 | KEEP | — | none | Progress→id mapping. |
| `collect_completed_engagement` / `collect_engagement_features` | 21 | KEEP | — | none | Collection plumbing. |
| `_collect_engagement_results` | 85 | KEEP+surgery | 035 | `test_missing_channels_write_partial_manifest_and_route_to_review` (rewritten) | Result mapping keeps; provenance-weakness review-routing dies (WARN/REVIEW). |
| `cancel` | 23 | KEEP | — | none | Process control. |
| `_record` | 15 | KEEP | — | none | Session ledger. |
| `_packet_node` | 15 | KEEP+FIX | §4 | none (one test added asserting finding text in mission.md) | The previous_findings transport bug — the one permitted add. |
| 15 module helpers (`_git_head`, `_pid_is_running`, `_process_identity`, `_format_process_failure`, `_git_worktree_evidence`, `_find_branch_worktree`, etc.) | 232 | KEEP | — | none | Launch/poll/record plumbing; none can say "no" to the evaluator. |

## mission_projection.py — 215 lines — KEEP entire file

| Function | Lines | Verdict | Justification |
|---|---|---|---|
| `project_mission` | 102 | KEEP | Nodes→mission plan; pure projection. |
| `_topological_nodes` | 32 | KEEP | Ordering. |
| `_default_mission_readiness` | 22 | KEEP | Validation-path selection for the plan. |
| `_item_lines` / `_render_item` | 13 | KEEP | Rendering. |

## mission_evidence.py — 900 lines (densest governance)

| Function | Lines | Verdict | BM | Tests that die | Justification |
|---|---|---|---|---|---|
| `collect_mission_evidence` | 295 | KEEP+surgery | 035, 036 | several rewritten (below) | Per-node manifests are keep (work order §5 Stage 3); the verdict join dies. |
| Readers: `_read_feature_ids`, `_read_handoffs`, `_read_progress`, `_read_receipts`, `_read_jsonl`, `_read_json_object` | 60 | KEEP | — | none | Artifact readers. |
| `_push_verification` | 43 | STRIP | 035 | `test_collect_requires_an_individual_successful_push_for_each_feature`, `test_collect_rejects_push_recorded_after_feature_reported_success` | Push-timing verdict gates evaluation; push_audit records remain as evidence. |
| `_timestamp_at_or_before` | 12 | STRIP | — | (with above) | Helper of `_push_verification`. |
| `_progress_evidence`, `_select_handoff*`, `_worker_session_id`, `_node_complete` | 96 | KEEP | — | none | Evidence extraction. |
| `_receipts_conflict`, `_receipt_identity_conflicts` | 10 | DEMOTE | 035 | `test_conflicting_receipts_are_preserved_but_route_only_that_node_to_review` (rewritten: observation, not review) | Conflict is identity evidence; it must not silence evaluation. |
| `_same_git_repository`, `_receipt_git_context_reasons` | 95 | DEMOTE | 035 | `test_existing_different_receipt_repository_is_rejected` dies; `test_deleted_receipt_worktree_relies_on_commit_and_branch_identity` rewritten | Receipt repo-mismatch becomes a recorded fact, not a rejection. |
| `_protected_branch_push_reasons` | 78 | KEEP detection, kill suppression | 036 | `test_mission_evidence.py` quarantine assertions rewritten | BM-036 is INCIDENT+EVALUATE: detection survives and gets louder; the quarantine power dies. |
| `_cross_check` | 22 | DEMOTE | 035 | — | The dict is evidence; its verdict use dies. |
| `_missing_channels` | 29 | DEMOTE | 035 | `test_missing_channels_..._route_to_review` rewritten | Missing channels recorded as partial evidence, not review routing. |
| `_disagreement_reasons`, `_quarantine_reasons` | 22 | STRIP | 035 | quarantine assertions in `test_mission_evidence.py` | Pure verdict machinery. |
| `_completion_id`, `_completion_digest` | 38 | KEEP | 037/038 | none | Feed the genuine KEEP guard. |
| `_manifest_name`, `_string`, `_write_json` | 13 | KEEP | — | none | Manifest writers. |

## mission_git_verify.py — 340 lines (Stage 2: demoted to evidence)

| Function | Lines | Verdict | BM | Tests that die | Justification |
|---|---|---|---|---|---|
| `verify_git_result` | 102 | DEMOTE→slim | 030, 031, 032 | `test_result_must_be_reachable_from_exact_engagement_branch`, `test_result_must_be_reachable_from_origin_engagement_ref`, `test_result_commit_must_have_exact_node_trailer`, `test_base_must_be_ancestor_of_result` (all rewritten as observation assertions); `test_collect_quarantines_real_ancestry_mismatch`, `test_collect_quarantines_handoff_result_disagreement`, `test_collect_rejects_feature_commit_that_is_local_only` die | Remainder: resolve ref, confirm commit (HC-07 survives), report ancestry/reachability/trailer as recorded facts. |
| `verify_engagement_history` | 58 | DEMOTE | 033 | `test_engagement_history_is_one_topological_commit_per_node` rewritten | Commit-shape ceremony becomes an observation; only genuinely inseparable outputs review. |
| `_object_type`, `_is_ancestor`, `_resolve_local_branch`, `_remote_branches_containing`, `_remote_branch_tip`, `_commits_in_range`, `_commit_node_trailers`, `_run_git` | 104 | KEEP | — | none | Observation tools the slimmed verifier still uses. |

## mission_push_guard.py — 352 lines — STRIP entire file (Stage 1)

All 12 functions (`install_git_push_guard`, `run_guarded_git`, `run_pre_push_hook`, helpers). Prevention machinery with a documented bypass (absolute git + `-c core.hooksPath=/dev/null`); post-hoc detection already lives in `mission_evidence._protected_branch_push_reasons`. No function here can pass the §2.3 test — they exist to say "no" before the fact.
Tests that die: all of `test_mission_push_guard.py` (204 lines, 5 tests). One integration point: `mission_adapter.py:185` (install call) + import at `:29`.

## completion_discipline.py — 245 lines — KEEP (BM-037/038, genuine)

`submit_completion` (187L) + helpers. **Minimal-guard measurement (§3, report only):** a minimal HC-06 digest-conflict guard — normalize id+digest, one indexed SELECT by completion_id, replay/conflict branch, one write — costs **~45–55 lines**. Current file: 245. Finding for the operator: **~190 lines** of transaction ceremony and dual-envelope preservation above the minimum. No action taken; out of scope per decision 8.2.

## reconciler.py — engagement block only

| Function | Lines | Verdict | BM | Tests that die | Justification |
|---|---|---|---|---|---|
| `_reconcile_engagement_group` | 267 | KEEP+surgery | 034 | `test_mission_reconciler.py` quarantine-fanout assertions rewritten | BM-034 SOFTEN: exact matches reconcile independently; only missing/duplicate/unknown mappings route. |
| `_route_engagement_result_to_review` | 34 | KEEP | — | none | The routing mechanism itself stays; it just stops being fed by ceremony. |

## Projected net line delta (production)

| Stage | Delta |
|---|---|
| 1 — push_guard (−352) + BM-020/019 surgery (−~25) | **≈ −375** |
| 2 — git_verify demote (340 → ~130) | **≈ −210** |
| 3 — evidence surgery (−~160) + reconciler surgery (−~60) + §4 fix (+~15) | **≈ −205** |
| **Combined Stages 1–3** | **≈ −790 production** |

Test side: −204 (push_guard file) plus rewrite-not-delete for demoted
observation assertions; net test delta negative but smaller. Suite green at
every stage boundary. Stage 4 ends with the live local-executor proof
(criterion 6).

**Awaiting Sab's signature. No demolition branch exists yet; Stage 1 creates it.**
