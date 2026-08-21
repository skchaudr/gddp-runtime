# Decision memo — Evaluation Precedes Admission (§3.5)

Decision needed by operator. Two tensions, each with options and a recommendation.

## 1. The invariant

> "No admission gate, verification mechanism, policy layer, intermediate check, or other governance mechanism may suppress or preempt evaluation. … [They] may not substitute for, prevent, or terminate the evaluator's judgment." (docs/invariants/invariants.md §3.5)

## 2. Tension 1: the merge-commit gate

**Current behavior (verified):** `bridge._verify_once` returns `subject_mismatch` with **no verdict** when a return has no `merge_commit_sha` (line 156–158, "merge_commit_sha is required to pin the evaluation subject") or the worktree won't materialize at that SHA (line 164–166). The error record is routed to review, but the evaluator renders no judgment on that work at all.

**Option A — Degraded evaluation.** When a commit ref is missing, evaluate whatever evidence exists (worktree state, artifacts) with the pinning gap recorded as a receipt finding; verdict floors at needs-human-review. *Cost:* adds a partial-evaluation path (more code, weaker subject binding). *Risk:* a verdict on unpinned state could be misread as authoritative; mitigated by the needs-human-review floor.

**Option B — Keep the gate, codify the exemption.** A commit ref is what makes work evaluable; a missing ref means the executor produced no durable work, and that is itself the judgment. Record it as a receipt-shaped note so "nothing evaluable returned" is still a rendered judgment. *Cost:* minimal — a small receipt-shaped note, no new evaluation path. *Risk:* none materially new; keeps the pinning invariant honest.

**Option C — Receipt-only.** No code evaluation, but always mint a verdict receipt (needs-more-evidence + harness note) so the "evaluator renders a judgment" promise holds mechanically. *Cost:* receipt plumbing change only. *Risk:* a mechanically-minted receipt may look like real evaluation to downstream consumers.

**Recommendation: B.** It is the cheapest, keeps subject-pinning honest, and converts the current silent no-judgment into an explicit rendered judgment ("no evaluable work returned") without pretending to evaluate unpinned state.

## 3. Tension 2: the unevidenced sweep

**Current behavior (verified):** evaluation fires only via `reconcile_sessions` over active executor sessions (`reconciler.py`). Work that never reaches reconcile — session lost, executor died pre-collect — is never evaluated. LOOP.md: "the state-driven sweep (evaluate anything sitting unevidenced) is the known missing half." §3.5's "may not prevent or terminate evaluation" reads as making this sweep doctrinally required, not optional.

**Option A — Heartbeat-native sweep.** A runner tick checks for landed-evidence-without-verdict and evaluates each gap through the sanctioned path, one at a time. *Cost:* new reconcile branch + capacity guard. *Risk:* doubles evaluation load if not capped; needs the same concurrency discipline as reconcile.

**Option B — Keep it operator-launched.** A `sweep` agent already exists (`.pi/agents/sweep.md`, model xai/grok-4.6, capped at 3 evals per shift) for exactly this: find evidence-without-verdict gaps and evaluate them via the sanctioned path. *Cost:* zero new machinery — the agent is the sweep. *Risk:* coverage depends on an operator (or a scheduled call) invoking it; gaps sit unevidenced until then.

**Recommendation: A, but only once B is proven insufficient.** Start by operationalizing the existing `sweep` agent (schedule it, wire it into the heartbeat cadence) before building a heartbeat-native branch. This honors the invariant with the least new machinery and confirms real demand before adding the reconcile path.

## 4. Decision lines

- [ ] Merge-gate option: **A / B / C** (recommended: B)
- [ ] Sweep option: **A (heartbeat-native) / B (operator-launched sweep agent)** (recommended: B-first, then A if gaps persist)
