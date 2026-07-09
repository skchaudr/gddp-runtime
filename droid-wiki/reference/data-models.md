# Data models

GDDP Runtime keeps all mutable state in a single SQLite database at `db/queue.db` under the runtime root. The schema is created by `scripts/init_db.py` and mirrors the YAML schemas in `gddp-config/schemas/v1/`. Verdicts and intermediate evaluator output are Pydantic models and dataclasses defined in `scripts/runtime/verification/schemas.py` and `scripts/runtime/heartbeat/graph_reader.py`. This page documents all six tables and every model the evaluator and graph reader exchange.

## SQLite tables

All tables use `schema_version` TEXT defaulting to `'1.0'`. Foreign keys are enforced via `PRAGMA foreign_keys=ON`. JSON-valued columns store serialized JSON strings; SQLite does not enforce their shape.

### events

Normalized intake objects. Raw webhook payloads are never stored in this table, only the normalized event row. Source: `scripts/intake_server.py`.

| Column | Type | Default | Notes |
|---|---|---|---|
| `event_id` | TEXT | — | Primary key. Format `evt_<timestamp>`. |
| `schema_version` | TEXT | `'1.0'` | |
| `received_at` | TEXT | — | ISO timestamp. Not null. |
| `source` | TEXT | — | `github`, `transcript`, or `manual`. Not null. |
| `event_type` | TEXT | — | `pull_request.opened`, `issue.opened`, etc. Not null. |
| `actor` | TEXT | — | GitHub login of the sender. |
| `branch` | TEXT | — | Head branch of the PR or pushed ref. |
| `base_branch` | TEXT | — | Base branch, defaults to `main` in normalization. |
| `pr_number` | INTEGER | — | PR number, if applicable. |
| `issue_number` | INTEGER | — | Issue number, if applicable. |
| `commit_sha` | TEXT | — | Head SHA or push `after` SHA. |
| `url` | TEXT | — | HTML URL of the PR or issue. |
| `repo` | TEXT | — | `owner/name` from the webhook payload. |
| `project_id` | TEXT | — | Stamped by heartbeat after adoption. Null on intake. |
| `project_node_candidates` | TEXT | — | JSON array of candidate node ids. |
| `scope_status` | TEXT | `'pending'` | `pending`, `in_scope`, `out_of_scope`. |
| `priority` | TEXT | `'pending'` | `pending`, `low`, `medium`, `high`, `critical`. |
| `risk_level` | TEXT | `'pending'` | `pending`, `low`, `medium`, `high`. |
| `raw_payload_path` | TEXT | — | Path to the saved raw webhook JSON on disk. |
| `normalized_payload_path` | TEXT | — | Path to the normalized event YAML on disk. |
| `classification` | TEXT | — | JSON object: category, intent, flags. |
| `routing` | TEXT | — | JSON object: selected_executor, selected_queue. |
| `status` | TEXT | `'received'` | `received`, `classified`, `mapped`, `ignored`. |
| `claimed_at` | TEXT | — | Timestamp when a worker claimed the event. Added by migration. |

### jobs

Bounded work packets. One event can produce zero, one, or many jobs. Source: heartbeat scoping and dispatch.

| Column | Type | Default | Notes |
|---|---|---|---|
| `job_id` | TEXT | — | Primary key. |
| `schema_version` | TEXT | `'1.0'` | |
| `created_at` | TEXT | — | Not null. |
| `event_id` | TEXT | — | Foreign key to `events(event_id)`. |
| `project_id` | TEXT | — | |
| `repo` | TEXT | — | |
| `node_id` | TEXT | — | Not null. The graph node this job targets. |
| `job_type` | TEXT | — | `implementation`, `review`, `reasoning`, `context_update`. Not null. |
| `executor` | TEXT | — | `jules`, `vertex`, `pi_worker`, `vm_worker`, `human`. Not null. |
| `queue_state` | TEXT | `'ready'` | Mirrors queue_record states. |
| `title` | TEXT | — | Not null. |
| `goal` | TEXT | — | Not null. |
| `why` | TEXT | — | |
| `source_context` | TEXT | — | JSON object. |
| `constraints` | TEXT | — | JSON array. |
| `acceptance_criteria` | TEXT | — | JSON array. |
| `dependencies` | TEXT | — | JSON array. |
| `priority` | TEXT | `'medium'` | |
| `risk_level` | TEXT | `'low'` | |
| `estimated_effort` | TEXT | `'medium'` | |
| `status` | TEXT | `'ready'` | `ready`, `running`, `awaiting_result`, `awaiting_review`, `complete`, `failed`. |
| `attempt` | INTEGER | `0` | Incremented on redispatch. |
| `max_attempts` | INTEGER | `3` | |
| `artifacts_dir` | TEXT | — | |
| `result_summary_path` | TEXT | — | |

### queue_records

Lifecycle tracking with leasing. Prevents two workers from picking up the same job.

| Column | Type | Default | Notes |
|---|---|---|---|
| `queue_item_id` | TEXT | — | Primary key. |
| `schema_version` | TEXT | `'1.0'` | |
| `job_id` | TEXT | — | Foreign key to `jobs(job_id)`. Not null. |
| `queue` | TEXT | — | Queue name; state values follow `queue_record.yaml`. Not null. |
| `available_at` | TEXT | — | Not null. |
| `lease_owner` | TEXT | — | `null` or worker id. |
| `lease_expires_at` | TEXT | — | `null` or ISO timestamp. |
| `retry_count` | INTEGER | `0` | |
| `last_error` | TEXT | — | |

### results

Unified executor return contract. Downstream stages do not care which executor produced the result. Written by `scripts/runtime/return_router.py` via `scripts/runtime/results_store.py`.

| Column | Type | Default | Notes |
|---|---|---|---|
| `result_id` | TEXT | — | Primary key. |
| `schema_version` | TEXT | `'1.0'` | |
| `job_id` | TEXT | — | Foreign key to `jobs(job_id)`. Not null. |
| `executor` | TEXT | — | Not null. |
| `received_at` | TEXT | — | Not null. |
| `execution_duration_seconds` | INTEGER | — | |
| `outcome` | TEXT | — | `success`, `failure`, `partial`, `error`. Not null. |
| `status` | TEXT | — | `completed`, `failed`, `needs_review`. Not null. |
| `changed_files` | TEXT | — | JSON array. |
| `patch_path` | TEXT | — | |
| `summary_path` | TEXT | — | |
| `logs_path` | TEXT | — | |
| `acceptance_check` | TEXT | — | JSON object: criterion to `pass`, `fail`, or `untested`. Holds the verification dict on the return path. |
| `risks` | TEXT | — | JSON array. |
| `followup_candidates` | TEXT | — | JSON array of node ids. |
| `github_action` | TEXT | — | JSON object describing the source PR action. |

### artifact_verifications

Gate records checked before node advancement. Every `required_artifact` in a node must verify before a node moves to complete.

| Column | Type | Default | Notes |
|---|---|---|---|
| `verification_id` | TEXT | — | Primary key. |
| `schema_version` | TEXT | `'1.0'` | |
| `job_id` | TEXT | — | Foreign key to `jobs(job_id)`. Not null. |
| `node_id` | TEXT | — | Not null. |
| `artifact_type` | TEXT | — | `decision.md`, `result-summary.md`, `patch.diff`, `merged_pr`, etc. Not null. |
| `validation_method` | TEXT | — | `file_exists`, `content_check`, `github_api_check`, `human_audit`. Not null. |
| `verified` | INTEGER | `0` | `0` or `1`. Not null. |
| `verified_at` | TEXT | — | |
| `verified_by` | TEXT | — | `runtime_validator`, `human`, `codex_reviewer`. |
| `notes` | TEXT | — | |

### decision_results

Records from the runtime decision loop. Distinct from `results`, which holds merged-PR receipts and foreign keys to jobs. A decision can be a `no_op` or stale-state clean with no associated job, so this table intentionally has no foreign key to `jobs`.

| Column | Type | Default | Notes |
|---|---|---|---|
| `result_id` | TEXT | — | Primary key. |
| `schema_version` | TEXT | `'1.0'` | |
| `action` | TEXT | — | `dispatch_next`, `escalate`, `review_pr`, `accept_node`, `no_op`. Not null. |
| `node_id` | TEXT | — | Nullable: `no_op` and `escalate` may have no node. |
| `project_id` | TEXT | — | |
| `reason` | TEXT | — | |
| `created_at` | TEXT | — | Not null. |

## Pydantic models

Defined in `scripts/runtime/verification/schemas.py`. These serialize to JSON receipts written by `scripts/runtime/verification/receipt_sink.py`.

### VerdictReceipt

The top-level evaluator output. Combines the deterministic and semantic lanes plus the integrity lane into one verdict.

| Field | Type | Notes |
|---|---|---|
| `project_id` | `str` | |
| `node_id` | `str` | |
| `verdict` | `Verdict` | Combined worst-of verdict. See enum below. |
| `criteria_verdict` | `Verdict \| None` | The criteria lane's own verdict, preserved separately. Optional for legacy receipts. |
| `integrity` | `IntegrityOutput \| None` | Lane 2 output. Optional. |
| `criteria_confidence` | `float` | `0.0` to `1.0`. Legacy receipts carrying `confidence` are mapped forward by a model validator. |
| `completeness_status` | `Literal["complete", "partial", "not-run"]` | Inferred from the semantic output if absent. |
| `deterministic` | `DeterministicResult` | Lane 1 dataclass result. |
| `semantic` | `SemanticOutput \| None` | Lane 1 semantic result. |
| `decision_reasoning` | `str` | |
| `required_next_action` | `str` | |
| `generated_at` | `str` | |

`Verdict` is a `str, Enum` with values: `pass`, `fail`, `blocked`, `needs-human-review`, `needs-more-evidence`, `out-of-scope-change-detected`.

### SemanticOutput

The semantic agent's adjudication of criteria the deterministic lane could not resolve.

| Field | Type | Notes |
|---|---|---|
| `judgments` | `list[CriterionJudgment]` | One per criterion the agent judged. |
| `overall_reasoning` | `str` | |
| `risks` | `str \| None` | |
| `followup_candidates` | `str \| None` | |
| `budget_exhausted` | `bool` | True when the agent hit a turn, tool-call, or token limit. |
| `budget_trace` | `dict[str, Any] \| None` | Optional budget accounting. |

### IntegrityOutput

Lane 2 fresh-eyes drift review. Vocabulary comes from the evaluator-intent-integrity-verdict node YAML in gddp-config, not from this repo.

| Field | Type | Notes |
|---|---|---|
| `verdict` | `Literal["pass", "block", "drift", "insufficient", "contradicted", "unknown"]` | |
| `intent_preserved` | `bool` | |
| `graph_integrity_preserved` | `bool` | |
| `required_human_review` | `bool` | |
| `confidence` | `float` | `0.0` to `1.0`. |
| `findings` | `list[IntegrityFinding]` | |
| `reasoning` | `str` | |

### CriterionJudgment

A single criterion adjudication from the semantic agent.

| Field | Type | Notes |
|---|---|---|
| `criterion_id` | `str` | |
| `judgment` | `Literal["judged_pass", "judged_fail", "indeterminate"]` | |
| `confidence` | `float` | `0.0` to `1.0`. |
| `evidence` | `list[str]` | |
| `reasoning` | `str` | |

### IntegrityFinding

One finding from the integrity lane.

| Field | Type | Notes |
|---|---|---|
| `severity` | `Literal["low", "medium", "high"]` | |
| `summary` | `str` | |
| `affected_node_ids` | `list[str]` | |

## Dataclasses

Also defined in `scripts/runtime/verification/schemas.py`, except `NodeData` and `ProjectGraph` which live in `scripts/runtime/heartbeat/graph_reader.py`.

### NodeData

A single graph node loaded from `gddp-config/graphs/<project_id>/nodes/<node_id>.yaml`.

| Field | Type | Default in loader | Notes |
|---|---|---|---|
| `node_id` | `str` | — | From YAML `node_id`. |
| `title` | `str` | — | From YAML `title`. |
| `status` | `str` | `'pending'` | From YAML `status`. |
| `type` | `str` | `'capability'` | From YAML `type`. |
| `why` | `str` | `''` | From YAML `why`. |
| `depends_on` | `list[str]` | `[]` | From YAML `depends_on`. |
| `acceptance_criteria` | `list[str]` | `[]` | From YAML `acceptance_criteria`. |
| `constraints` | `list[str]` | `[]` | From YAML `constraints`. |
| `allowed_execution_modes` | `list[str]` | `['jules']` | From YAML `allowed_execution_modes`. |
| `required_artifacts` | `list[str]` | `[]` | From YAML `required_artifacts`. |
| `priority` | `str` | `'normal'` | From YAML `priority`. |
| `unlocks` | `list[str]` | `[]` | From YAML `unlocks`. |

### ProjectGraph

A loaded project graph summary from `gddp-config/graphs/<project_id>/project.yaml`.

| Field | Type | Notes |
|---|---|---|
| `project_id` | `str` | |
| `project_name` | `str` | |
| `repo` | `str` | |
| `nodes` | `list[dict]` | Summary rows from `project.yaml`. Each row has at least `id` and `status`. |
| `execution_policy` | `dict` | From `project.yaml` `execution_policy`. |

### DeterministicResult

Lane 1 deterministic output, embedded in `VerdictReceipt.deterministic`.

| Field | Type | Notes |
|---|---|---|
| `criteria` | `list[CriterionCheck]` | One per acceptance criterion. |
| `constraints` | `list[ConstraintCheck]` | One per constraint. |
| `artifacts_present` | `dict[str, bool]` | Required artifact name to presence. |
| `deps_status` | `dict[str, str]` | Dependency node id to status. |
| `criteria_mismatches` | `list[CriterionMismatch]` | Structured mismatches for the semantic lane. |
| `missing_evidence` | `list[MissingEvidence]` | Evidence gaps for the semantic lane. |
| `human_review_questions` | `list[HumanReviewQuestion]` | Questions to surface in the receipt. |

### CriterionCheck

One deterministic criterion probe result.

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | Criterion id. |
| `criterion` | `str` | Human-readable criterion text. |
| `status` | `str` | `pass`, `fail`, `indeterminate`, etc. |
| `confidence` | `float` | |
| `method` | `str` | Probe method name. |
| `evidence` | `list[str]` | |
| `reasoning` | `str` | |
| `mismatch_kind` | `str` | |
| `mismatch_detail` | `str` | |
| `needs_evidence` | `bool` | |
| `human_question` | `str` | |

### ConstraintCheck

One deterministic constraint probe result.

| Field | Type | Notes |
|---|---|---|
| `constraint` | `str` | |
| `status` | `str` | |
| `confidence` | `float` | |
| `method` | `str` | |
| `evidence` | `list[str]` | |
| `reasoning` | `str` | |

For the environment variables that point the runtime at this database, see [configuration](configuration.md). For the libraries that define these models, see [dependencies](dependencies.md).
