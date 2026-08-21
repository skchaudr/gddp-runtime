# Spec: Typed graph-recommendation channel (lane 2)

Status: DRAFT — needs Sab sign-off before any implementation.
Implements invariant §3.3 (Human Graph Authority and Evaluator Recommendations) and audit Second Pass §B.1 / §C.1: the evaluator may recommend graph changes; the contract currently cannot express them.

## Doctrine (verbatim intent)

  1. **Evaluator may recommend, never enact.** §3.3: the evaluator "may identify, reason about, and recommend changes to graph topology, nodes, dependencies, criteria, or planned work" whenever evaluation produces information that affects the project's intended trajectory. "It may not directly enact those changes or accept nodes; mutation of graph truth requires human authorization."
  2. **Continuation proposals stay human-materialized.** §2.3: work discovered beyond a node's declared scope is recorded as a continuation proposal (YAML in a proposals ledger), invisible to the frontier until a human materializes it. The evaluator may *draft*; the human *places*.
  3. **Horizon ≠ adjudication.** §3.2 already splits findings (affect this node's verdict) from graph_observations (trajectory, no verdict effect). Recommendations are a third channel: they propose a graph change. They do not affect the combined verdict and they do not trigger retry.
  4. **Evaluator stays evidence-only.** GDDP-rebuild provisional flow: the evaluator never writes graph state. The only system writer of graph-adjacent state is the reconcile-phase provisional writer, and it writes *status*, not nodes. A recommendation is evidence, like a verdict.

The problem this closes: `IntegrityOutput` today offers `findings` / `graph_observations` with `severity + summary + affected_node_ids`. That can describe "the graph looks stale." It cannot say *what should change*. Graph intelligence terminates as prose (audit D1, upgraded to a tier-1 collision).

## v1 design (lean)

One optional field on the existing integrity payload. No new lane, no new model call, no new writer.

### Contract

Add to `IntegrityOutput` (`scripts/runtime/verification/schemas.py`), optional, default `None` (legacy receipts stay valid):

```
graph_recommendations: list[GraphRecommendation] | None
```

`GraphRecommendation`:

| Field | Type | Required | Notes |
|---|---|---|---|
| `action` | enum, see below | yes | tight vocabulary, not free text |
| `affected_node_ids` | `list[str]` | yes | empty only for `create_node` when proposing a new id in the draft |
| `rationale` | `str` | yes | why the graph should change, given *this* evaluation |
| `evidence` | `list[str]` | yes | repo paths (`file:line`) and/or canonical node ids; empty list is invalid — drop the item |
| `draft_node_yaml` | `str \| None` | no | single node-YAML fragment; only meaningful for `create_node` / `insert_prerequisite` |

Action vocabulary (8, closed):

| Action | Means |
|---|---|
| `split` | named node should become two (or more) |
| `supersede` | named node should be replaced by another (existing or drafted) |
| `insert_prerequisite` | a missing prerequisite should sit before a named node |
| `revise_criteria` | named node's criteria encode a wrong or obsolete assumption |
| `rewire` | add/remove a specific `depends_on` / `unlocks` edge |
| `reorder` | serialize or parallelize a region (execution strategy, not a single edge) |
| `create_node` | missing work that has no node (continuation) |
| `retire_node` | named upcoming node is no longer necessary |

**Never affect the combined verdict.** Combiner (`integrity_combiner.py`) ignores `graph_recommendations` the same way it already ignores `graph_observations`. No new floor. A node can `pass` with recommendations attached.

**Never trigger retry.** `retry_budget.has_evidence_references` / `should_retry` inspect `findings` and `reasoning` only. Do not add recommendations to that scan. A graph-change proposal is the wrong remedy for a retry of the same node (audit: injecting "you broke node Y" into this node's fix-list).

### Prompt

`INTEGRITY_SYSTEM_PROMPT` gains a third bucket next to the existing findings / graph_observations block. Decision rules:

| Channel | When | Verdict? |
|---|---|---|
| `findings` | current work caused, contains, or violates the condition | yes |
| `graph_observations` | trajectory / convergence / strategy; **no** proposed graph change | no |
| `graph_recommendations` | evaluation produced **concrete evidence the graph should change** (named action + affected nodes + citations) | no |

Empty is the default. Emit a recommendation only when all three are present: a named `action`, at least one `affected_node_id` (or a drafted id for `create_node`), and at least one evidence citation. Missing any → observation or silence. Do not restate a finding as a recommendation. Do not recommend "look at this later."

`submit_integrity_verdict` argument list in the prompt grows one optional key: `graph_recommendations: [{action, affected_node_ids, rationale, evidence, draft_node_yaml?}]`.

### Extension

`gddp_integrity.ts` — add `GraphRecommendationSchema` and an optional `graph_recommendations` array on `SubmitIntegrityVerdictParams`, mirroring the Phase-3 `graph_observations` pattern: include in the written payload only when the model provides it. Guard unchanged. Tool remains terminal, once-per-run.

### Persistence + routing

Same pipe graph_observations already uses:

1. Receipt field on `IntegrityOutput` (full `VerdictReceipt` JSON under `gddp-config/verification/<project>/<node>/`).
2. CLI summary (`cli.py:main`): if present, `summary["integrity"]["graph_recommendations"] = [r.model_dump() for r in …]`. Flows through bridge → `results.acceptance_check`.
3. `jobs_status.py:print_evaluation`: one line per item, e.g. `graph recommendation: [create_node] node-13 — rationale`.
4. Browse TUI: a dedicated **RECOMMENDATIONS** block in `_print_evaluation_payload` (`gddp-config/scripts/node_cli.py`), after FOLLOWUPS & QUESTIONS (~L1406), shown only when at least one item is present. Do **not** fold into OBSERVATIONS — that block already mixes verdict-affecting findings with trajectory notes. Recommendations are operator *decisions about graph surgery*; they need their own scan block the way criteria already have a table.

**Ledger writes: not in v1. Receipt-only.**

Authority-boundary argument:

- The integrity subprocess is read-only (`gddp_verifier_guard.ts`). Its cwd is a worktree of the *target* repo, not `gddp-config`. Writing `gddp-config/proposals/` would require a second write path the guard currently forbids, and a second repo the evaluator is not running in.
- GDDP-rebuild: the evaluator never writes graph state. The only system writer of graph-adjacent state is the provisional writer, and it writes status. A new writer that drops YAML into a ledger makes the evaluator an author, not an observer.
- §2.3 already says the human materializes continuation proposals. A `draft_node_yaml` string on the receipt is enough for the operator to copy into the ledger (which, today, is doctrine without a live directory — there is no `gddp-config/proposals/` tree). Inventing that directory as a side effect of this channel is extra machinery.

v2, if demand appears: a human keypress in browse ("promote this draft to the ledger") is the right writer, not the evaluator.

## Constraints

- `decision_engine.py` 12-row matrix **untouched**.
- `integrity_combiner.combine` **untouched** except a one-line comment that `graph_recommendations` are ignored (same as `graph_observations`). No new floor, no upgrade, no halt.
- `retry_budget.py` **untouched**. Recommendations are not findings.
- Guard (`gddp_verifier_guard.ts`) **unchanged**. Evaluator remains read-only.
- Legacy receipts without the field stay valid (`None`-optional, same pattern as `graph_observations`).
- No new lane, no extra model call, no heartbeat writer, no ledger directory, no browse keypress in v1.
- Frozen surfaces (`intake_server.py`, jules adapters, etc.) not in scope.

## Acceptance sketch (for node YAML, Sab authors final)

- Fixture: criteria pass + integrity pass + one `create_node` recommendation with `draft_node_yaml` → combined verdict still `pass`; recommendation present on receipt, CLI summary, `jobs_status show`, and browse RECOMMENDATIONS block.
- Fixture: recommendation with evidence citations does **not** make `should_retry` true.
- Legacy receipt without `graph_recommendations` still parses.
- `python3 -m pytest -q scripts/runtime/verification scripts/test_jobs_status_evaluator.py` green; gddp-config `scripts/test_node_cli.py` green after the TUI block.

## Cost note

No extra semantic call. Same integrity run (~1–2 min deepseek today). Added cost is tool-schema tokens for the optional array plus whatever recommendation bodies the model emits. Empty default keeps the common path cheap.

## Open for Sab

- [ ] Action vocabulary of 8 — keep, or cut `reorder` (overlaps `rewire`)?
- [ ] Receipt-only drafts (recommended) vs also write YAML into a proposals ledger (would need a new write path and a directory that does not exist)
- [ ] Should a recommendation ever set `required_human_review` on its own? Spec says **no** — attention is the browse/jobs_status block, not a verdict floor. A pass-with-recommendations node still provisionally unblocks dependents.
- [ ] Field name: `graph_recommendations` (this spec) vs `graph_amendments`
