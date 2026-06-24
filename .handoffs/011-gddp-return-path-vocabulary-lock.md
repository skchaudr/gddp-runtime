# 002 — Return-path model + vocabulary lock (conductor → verification loop)

Date: 2026-06-17
Repos: `gddp-runtime`, `gddp-config` (no code changed this session — conversation + read-only grounding only)
Purpose: Created at Sab's request to preserve state before clearing the context window. This was a conceptual / altitude-setting session, not implementation.

---

## Empirical Reality (AGENT ONLY) — confirmed against code this session

**Return-path code that exists:**
- `scripts/runtime/return_router.py` — complete (merged-PR → review receipt; `ALLOWED_REPOS = ["skchaudr/vault-doctor"]`).
- `scripts/runtime/results_store.py` — writes receipts to the `results` table.
- `scripts/runtime/graph_updater.py` — **disabled stub**, returns `graph_mutation_disabled_review_required` (no longer mutates graph truth; CHANGELOG 1.1.2).
- `scripts/runtime/replay.py`, `heartbeat/`, `scripts/init_db.py`, `scripts/dry_run.py` — the machinery the operator-run checklist actually drives.

**`decision_loop/` is forward-path and known-buggy (NOT the Task 3 surface):**
- Contents: `__init__.py, context_reader.py, engine.py, powers/, schema.py, test_decision_loop.py`.
- **Bug confirmed:** `decision_loop/context_reader.py:83` runs `SELECT * FROM return_results ORDER BY created_at DESC LIMIT 20`. The `return_results` table is created **only** in `test_decision_loop.py:85` — it is not in the live `db/queue.db` schema. So `decision_loop` queries a nonexistent table against the real DB.
- **Fenced off:** Task 3 must not touch `decision_loop/`. It is the older forward-path **decision loop** module (see drift note).

**The entire Task 3/4 return-path architecture is NOTES-ONLY (not in the repo):**
- `rg` across `scripts/` found ZERO occurrences of: `verification_loop`, `conductor`, `review_queue`, `run_structural_validator`, `decision_engine`, `semantic_evaluator`, `open_evidence_pr`.
- → The return-path machine in Sab's vault notes is **design-stage**. Nothing of Task 3 (review_queue + verification loop) or Task 4 (semantic_evaluator) is built yet.

**Drift to reconcile (important):**
- `gddp-config/graphs/gddp-runtime/` nodes: `return-router` (complete), `decision-loop-spec` (complete), `decision-loop-runtime` (pending), `decision-loop-review-gate` (pending).
- `docs/decision-loop-spec.md` (v0) specs a **forward-path decision loop** with 4 powers: `dispatch_next, review_pr, accept_node, escalate`. (Its term is "decision loop"; "brain" appears once as a role analogy — hands/nervous system/brain — not as Sab's working vocabulary.)
- The real drift was **Claude's**: it promoted that one-off "brain" analogy into a recurring noun ("the brain," "the brain's senses") and stretched it onto the *return-path* verification loop — conflating two distinct surfaces. Sab's own docs and notes did not drift. Open task: keep "decision loop" (forward path) and "verification loop" (return path) strictly separate; do not reintroduce "brain" as a name.

**Context:** Last ~5 weeks of commits in both repos were `docs/gdd-explained.html` + README/portfolio polish (see handoff 001, 2026-05-09/10), not engine work. These operator runs are the first return to operating the engine since early May.

---

## Canonical Model & Vocabulary (from Sab's vault notes — AUTHORITATIVE)

Sab's source of truth is 3 Obsidian vault notes (the "Index Map" + "Task 3 & 4 note"), held by a separate Obsidian ACP Claude. Terminal Claude cannot see them — defer to them; ask Sab to paste when unsure. Use ONLY this vocabulary.

**The two paths (the spine):**
- Forward path: `graph truth → heartbeat → job → dispatch`
- Return path: `merged PR → receipt → awaiting_review → human decision`
- Rule: gddp-config is human-owned graph truth. Runtime reads truth, dispatches, writes receipts, stops at `awaiting_review`. **Only human review changes graph truth. Never silent mutation.**

**The two loops (do NOT conflate — this was the drift):**
- decision loop — FORWARD path. Sab's term (`decision-loop-spec.md`). Decides what to dispatch next. "brain" is only a role analogy, never a name.
- verification loop — RETURN path. Gathers evidence on a merged PR (`run_verification()`). Task 3.
- They name different surfaces. Never call either "the brain"; never let "decision loop" leak into return-path discussion.

**Roles:**
- graph truth — gddp-config (human-owned; nothing else mutates it)
- runtime — gddp-runtime (reads truth, dispatches, writes receipts, stops at awaiting_review)
- executor — the agent that does the work (Jules, Cline, Pi); "the hands"
- operator — Sab, by hand: select node, dispatch, read receipt, decide at the truth boundary

**Return-path machine (in order):**
1. `return_router` writes review receipt, marks job `awaiting_review` *(exists)*
2. `review_queue` exposes the work item *(Task 3 builds it — does not exist)*
3. **verification loop** (`verification_loop.py`) gathers evidence: changed_files, present_paths, acceptance_before, acceptance_after, PR number, node ID. Entry action: `run_verification()`. *(Task 3 — does not exist)*
4. `run_structural_validator(…)` → `StructuralOutput` *(T1)*
5. optionally `semantic_evaluator.evaluate(…)` → `SemanticOutput` *(T4 — does not exist)*
6. `decision_engine.decide(…)` — pure reducer, NO I/O — emits `DecisionOutput` with a verdict *(T2)*
7. on ACCEPT → `open_evidence_pr(…)` proposes graph advancement via a reviewable PR. Never silent mutation.

- Verdicts: `ACCEPT, FAIL, NEEDS_REVIEW, INVALID, INCOMPLETE`.
- **Task 3 = deterministic verification loop** (return path).
- **Task 4 = semantic evaluator** (judges meaning/drift; returns a *bounded* `SemanticOutput`; does NOT decide graph state).

**TERMINOLOGY DECISION made this session — "conductor" is abolished:**
- `conductor` → **verification loop**; `conductor.py → verification_loop.py`; `test_conductor.py → test_verification_loop.py`; "deterministic conductor" → "deterministic verification loop" (Task 3 & 4 note, mermaid node, run index).
- Entry function: `run_verification()` (parallels `run_structural_validator()`).
- NOT "verification engine" — collides with `decision_engine` (the pure reducer). The verification loop does I/O (gathers evidence); the engine must stay pure.
- This rename is pending in the **notes**; `conductor.py` is not in the repo today, so there is nothing to rename in code yet.

**Banned invented terms (Claude introduced these — do NOT reuse):**
- "A/B", "phase 0", "slices" → use **the run ladder / build-up order**
- "the brain's senses" → the **verification loop gathering evidence** (return path) — not decision_loop
- "build the decision loop now" → that's a separate forward-path module, fenced off from Task 3
- "dispatch to Jules" → **the forward path (dispatch)**

---

## Where Sab is now + the goal

- **Task 3 operator runs** — Sab is the operator, being the verification loop + human judge by hand. Run ladder: Run 1 baby real task (`--version`), Run 2 `/health`, Run 3 intentional reject, Run 4 scope violation, Run 5 accept-or-defer drill.
- The **gap log** is the point of each run: what *deterministic structural verification* caught vs. what *human semantic review* caught → **that delta is the spec for Task 4 (`semantic_evaluator`).**
- Operator-run mechanics + inspection commands: `docs/operator-practice/run-checklist.md` (queries on `db/queue.db`: events/jobs/results/queue_records; job artifacts under `jobs/`; graph truth in gddp-config). Practice Log template at the bottom.
- **Goal:** move from **deterministic evaluation → semantic evaluation** (introduce the LLM = Task 4). Safety property: Task 4 returns a bounded `SemanticOutput`, `decision_engine` reduces, `open_evidence_pr` only proposes — **the LLM never touches the truth boundary** (advisory by design; human still decides).
- Overnight runs (`first-overnight-run`) are **downstream** — the payoff once the loop is complete + semantic eval exists. NOT the immediate target.

---

## How to work with Sab next session (guardrails — earned the hard way this session)

- **Stay at the questions altitude.** Do NOT propose builds or "say go and I'll start" until Sab explicitly asks for code. He steers back to questions on purpose; respect it.
- **Do NOT create "A/B — pick a path" forks.** They quietly put the build-push back in his lap, the opposite of what he's doing.
- **Use his vocabulary only.** Never invent parallel terms. When unsure, defer to the vault notes / ask him to paste.
- **Be concise.** He's overwhelmed by detail/jargon and values brevity (see his CLAUDE.md lean rules).
- **Terminal Claude's lane:** the Obsidian notes-Claude owns the model/vocabulary; this terminal session **ground-truths the model against the code** and executes surgical work when asked. Lead with that value.
- **Hand-pain history:** when building resumes, drive the generation; keep Sab in the read/steer seat (he handles his own Zed/Neovim editor setup).

---

## Narrative / Trajectory (SAB ONLY)

Intent: Lock the return path and complete the loop with semantic evaluation (the LLM as Task 4), so the system can eventually do unattended overnight runs while the human stays at the truth boundary. Operator runs now are the deliberate way to harvest the semantic-eval spec from reality instead of guessing it.

Interpretation: The "overwhelm / keep delaying gddp" pattern is real but is being dissolved correctly — by operating the engine and answering from rows/receipts instead of a fuzzy mental model. The 5-week drift into portfolio-doc polish was avoidance of the hard return-path work; these operator runs are the return to it. The biggest live risk is not technical — it's terminology drift and altitude (jumping to build), which derailed most of this session until the vault-notes model was pasted in. Keep the model tight and let Sab set the pace.
