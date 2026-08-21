# Decision memo — heuristic-fail finality in the evaluator

Decision needed by operator. One question, three options, a recommendation.

## The question

When a deterministic probe **fails** a criterion, `decision_engine.py` matrix row 3 returns `Verdict.FAIL` immediately. Semantic lane 1 never runs (`orchestrator.py:_should_run_semantic` requires `has_indeterminate and ... not criterion_failed`), and integrity lane 2 is instructed that criteria adjudication "is lane 1's job" (`integrity_runner.py:43`, `:308`). So a heuristic probe's failure is **final and unreviewable**.

But not all deterministic fails are equal. `probes.py` distinguishes two evidence classes:

- **`command_proof`** — the criterion declares a command; the harness runs it and reads the exit code. This is hard, executed evidence. A fail here is a real signal (`probes.py:292`).
- **Heuristic probes** — `probe_for(node_id, cid)` hardcoded per-node probes plus `_path_content_check`. These grep for patterns/symbols, check file existence, or compare a quoted literal against file content, and return `status="fail"` on *absence* (policy file missing, marker missing, symbol not found, `tier_distinct` absent). Absence-based inference, not executed behavior. A "fail" here can equally mean "criterion is stale," "implementation reworded," or "files reorganized" — the probe even emits `human_question="Is the expected content stale, or is the file wrong?"` (`probes.py:117`).

The one fallback that *avoids* this trap is the keyword scan, which deliberately returns `indeterminate` so semantic gets a look (`probes.py:357`). The hardcoded/probe paths have no such safeguard.

## Options

**A — Status quo.** Heuristic fail is final; lane 2 may only note a suspected misfire as an advisory observation under §3.2. *Cost:* none. *Risk:* an unreviewable pattern-match can FAIL a node that is actually correct; the human can reject/retry, but the evaluator never renders a second judgment, and the only model that saw the evidence (lane 2) is barred from criteria work.

**B — Semantic adjudication of heuristic fails.** `_should_run_semantic` also fires when any failing criterion's `method != "command_proof"`; command_proof fails stay final. Matrix gains a row before row 3 so a `judged_pass` can overturn a heuristic fail. *Cost:* one more semantic lane run on heuristic-fail paths; matrix/row addition + tests. *Risk:* semantic can now override deterministic *absence* evidence, which is exactly when a second look is warranted; the guardrail is that command_proof and constraint/dependency violations remain final.

**C — Middle: keep the verdict, make the contest visible.** Heuristic fail stays final, but the receipt gains an explicit marker `criteria_lane_skipped: deterministic fail (method=<ptype>)`, and the integrity prompt is permitted to flag suspected heuristic misfires as findings-with-citations so the human sees the contest at review. *Cost:* small — a marker field + one prompt sentence + tests. *Risk:* the FAIL still propagates to retry/provisional-blocking before any human looks; the contest is informational only.

## Recommendation: **B**

Heuristic probes produce absence-based inference, not evidence; when that inference is the sole basis for a FAIL, semantic should be allowed to adjudicate. This preserves command_proof finality (real executed evidence) while removing the one unreviewable judgment in the system.

## What §3.2 does and does not settle

§3.2 ("Distinct Evaluation Horizon and Adjudication Scope") legitimizes lane 2 reporting findings *beyond* the node without affecting the verdict. It does **not** answer whether advisory-only correction is enough for a heuristic fail: it says a graph-level observation need not be treated as a defect, but a wrongly-failed criterion is a defect *in the verdict itself*, not a graph-level observation. The determinism doctrine (`integrity-lane-spec.md:8`, "Deterministic evidence CAN be sufficient") endorses deterministic-first but was written before the command_proof-vs-heuristic distinction was a live boundary. This memo asks you to draw that line.

## Decision

- [ ] Heuristic-fail handling: **A / B / C** (recommended: B)
