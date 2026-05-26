# decision_loop runtime — audit findings (UNVERIFIED, off-scope when found)

**Status:** Captured knowledge, NOT applied. Belongs to the `decision-loop-runtime`
graph node, which is not yet being built.

**Provenance:** These findings surfaced on 2026-05-26 during what was supposed to be
*pre-work for the verification parallel build* (`verification-parallel-build-revised.md`).
That session went off-scope and "fixed" the existing `scripts/runtime/decision_loop/`
runtime instead of doing pre-work. The fixes were committed in `d637607`, then reset
out of `main`. The raw changes are preserved in `off-scope-audit-d637607.patch` (re-appliable
with `git apply`) and the commit remains recoverable via `git show d637607`.

**Do not treat these as fixed.** They are diagnoses, each verified against the schema/spec
as noted, but the *fixes* were never reviewed or test-validated as in-scope work. Re-evaluate
when the `decision-loop-runtime` node is actually built.

---

## Verified findings

1. **`context_reader` queried a non-existent table.** The pre-`d637607` code ran
   `SELECT * FROM return_results ...`. `return_results` exists nowhere in the schema
   (`results_store.py`, gddp-config `schemas/v1/`). At runtime this throws `no such table`.
   The real table is `results` (`results_store.py:38`, has `received_at`).
   - ✅ Diagnosis correct. ⚠️ The attempted fix wrapped the query in
     `except Exception: recent_results = []`, which silently swallows *all* errors — a bad
     fix of a real bug. A real fix should query `results` without hiding failures.

2. **Decision priority order contradicted the spec.** `decision-loop-spec.md:74–80` orders
   dispatch (#3) *before* the "in-progress too long → escalate" check (#4). The pre-`d637607`
   `engine.py` had the stuck/escalate check before dispatch.
   - ✅ Reorder is spec-correct.

3. **`_write_decision_result` raised TypeError.** It called
   `write_result(repo_name=, node_id=, status=, reason=)`, but `results_store.write_result`'s
   signature has no `repo_name`/`node_id`/`reason` params (it takes `job_id, executor,
   received_at, outcome, status, ...`). Guaranteed runtime TypeError on every decision write.
   - ✅ Real bug. ⚠️ The attempted fix narrowed writes to dispatch-only (with `job_id`) and
     dropped persistence for non-dispatch decisions — a behavior change to weigh, not adopt blindly.

4. **`dispatch_next` never wrote the job row.** `decision-loop-spec.md:101` requires "write a
   job row to SQLite with `status=dispatched`." The pre-`d637607` code didn't, so the active-job
   guard and return_router had nothing to find.
   - ✅ Real gap. ⚠️ The attempted fix introduced two things to scrutinize: a **breaking**
     signature change `run(ctx)` → `run(ctx, con)`, and a cross-module import from
     `heartbeat.state_recorder` (crosses the boundary the node spec preferred to keep clean).

---

## If/when adopting

Treat the patch as a starting sketch, not a merge candidate. At minimum: drop the silent
`except`, decide deliberately on the `run()` signature and the heartbeat import boundary,
and add tests that fail before each fix.
