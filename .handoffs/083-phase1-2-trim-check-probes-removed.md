# 068 — Phase 1 trim landed; CHECK_PROBES removed; deterministic lane's coverage gap now visible

## What we are merging, and why

**Merging:** `chore/phase1-trim` → `main`. Two commits — `53b1ffb` (the trim) and this handoff. Plus `764b8e3` in `gddp-config` (the archive file the trim's commit message points at).

**Net:** ≈2,370 LOC out of 29,779 (~8%). Suite 517 → 493 passed, 0 failed. The 24-test delta is the deleted `decision_loop` tests (20) and archived `test_replay.py` (4) — no surviving code lost coverage.

**Why:** every item in Phase 1 is code with **zero live importers** that nonetheless greps as live. That is the precondition for `AGENTS.md:5` — agent assumes behavior → designs around it unverified → system fails → workaround becomes architecture. The 423-line `CHECK_PROBES` dict was the sharpest case: another project's Facebook-Marketplace acceptance criteria, reachable on every `orchestrator.verify()`, resolving zero times for `gddp-runtime`'s own 22 nodes.

**Why now, with a mission in flight:** this does not make mission 1 more likely to *succeed*. It makes mission 1's failures easier to *read*. Nothing here can affect a running node — the deletions had no importers and the semantic lane is untouched.

**Why it is not pushed:** mission 1 is live on the VM. The risk was never the trim, it was landing a push into a running mission. Merge and pull on mini + VM once it clears.

------------------------------------------------ Agent Section START

Date: 2026-08-09
Worktree: /Users/sab-mini/repos/gddp-runtime (branch `chore/phase1-trim`); ~/repos/gddp-config (main)
Branch: `chore/phase1-trim` — **NOT merged, NOT pushed.** `main` untouched.

## Empirical Reality

Phase 1 of `docs/simplification-proposal.md` is committed locally as `53b1ffb`. Suite is **493 passed / 0 failed in 6.55s**, down from a 517-pass baseline — the 24-test delta is entirely the deleted `decision_loop` tests (20) and archived `test_replay.py` (4), not lost coverage.

Nothing is pushed because mission 1 is in flight on the VM. Sab's ruling: "once all is settled we can pull on mini and VM."

### Scope touched (gddp-runtime, all in `53b1ffb`)

- **Deleted** `scripts/runtime/decision_loop/` (12 files, 1,446 LOC incl. 4 test files), `scripts/node_status_history.py` (193), `patch.diff` (81) — zero importers, verified by grep before cut
  - **CORRECTION (2026-08-09):** `node_status_history.py` was **not** an orphan and has been restored. Its caller is cross-repo and dynamic — `gddp-config/scripts/node_cli.py:104` loads it by file path via `spec_from_file_location`, so it has zero *importers* while having a live caller. Grepping this repo could not have found it. See `084` for the corrected lesson.
- **Archived** to `scripts/_archive/`: canary trio (`canary_local_executor.py`, `canary_local_executor_slow.py`, `canary_stabilization_reset.py`, 160 LOC), `replay.py` (137), `test_replay.py` (107)
- **`probes.py`** −431: `CHECK_PROBES` data removed, binding kept as `CHECK_PROBES: dict[str, dict] = {}`, `probe_for` body unchanged
- **`pytest.ini`** NEW: `norecursedirs = *.egg .* _darcs build CVS dist node_modules venv {arch} scripts/_archive`
- **`AGENTS.md:39`**: dropped the false "No requirements.txt" claim
- **`test_deterministic.py` +188/−?**, **`test_dry_run_e2e.py` +25/−?**: 12 tests recoupled via `monkeypatch.setitem` on neutral invented fixture keys

### Scope touched (gddp-config)

- `graphs/sell-valuables/CHECK_PROBES_archive.py` — 59 preserved entries, inert reference data (`764b8e3`)

## What Phase 1 actually proved

`CHECK_PROBES` was 423 lines of another project's data sitting in the runtime. 59 entries, all resolving to `sell-valuables` (50, all 10 nodes `pending` — dormant) and `aa-cli` (9, 11/12 nodes `complete`). `gddp-runtime`'s own 22 nodes / 130 criteria hit it **zero** times.

Deleting it did not close the deterministic lane's coverage gap. It made the gap **visible** — which is the point. Dead code that greps as live is exactly the `AGENTS.md:5` failure pattern: agent assumes behavior → designs around it unverified → workaround becomes architecture.

## Open finding for Sab — do not let this get quietly resolved

`test_dry_run_e2e.py::test_verify_e2e_clean_pass_returns_receipt_without_repo_writes` is the **only** test in the repo covering "deterministic lane resolves the node alone, semantic never invoked" (passes no `semantic_harness`, asserts `receipt.semantic is None`).

It only ever passed because its fixture used criterion id `aa-root-and-state-paths` — an **aa-cli registry key**. With the registry empty, that criterion falls to keyword-scan → indeterminate → escalates → `orchestrator.py:50` raises `RuntimeError: semantic_harness (pi) is required`.

It is now green again via a neutral monkeypatched fixture key. So:

> **We are knowingly keeping a test for a code path that no live graph reaches.**

This is §7.2 of the proposal confirmed by execution rather than by counting. Mission 1 will escalate every node to the semantic lane — and would have done so before this trim too. Keeping or dropping that test is Sab's call.

## The higher-value move, unaddressed

Criterion resolution order in `evaluate_criterion` (`probes.py:633+`) is: (1) explicit `command:` field → `subprocess.run`, exit 0 = pass; (2) `probe_for` typed probe; (3) keyword-scan fallback.

**Path 1 runs before any probe lookup, needs no new machinery, and is used by exactly 1 of 493 live criteria across all 14 graphs.** Filling in `command:` fields is worth more than any registry work. No loader was built — build one when a project has real requirements for it.

## Process note

The chain-of-command review Sab asked for **never ran**. Both reviewer dispatches died on `zai/glm-5-turbo:high` → `429 code 1310, Weekly/Monthly Limit Exhausted, resets 2026-08-10 17:46:52`. Pi's first worker chain also 404'd on a retired default (`claude-3-7-sonnet`), and Pi's own session 429'd off Gemini mid-run and auto-switched to Grok 4.5 high.

Every defect in this commit was caught by Claude running the suite, not by review:

1. Worker deleted the `CHECK_PROBES` binding and hardcoded `return None` — broke `test_deterministic.py:14` on import, made `test_probe_any_of` unpassable. Restored empty-dict seam.
2. Archived `test_replay.py` still on pytest's path, died importing `scripts.runtime.replay`. Fixed with `norecursedirs`, not deletion (`_archive` is the pattern for Phases 2–4).
3. `norecursedirs` **replaces** pytest's defaults rather than extending them — collection went 493 → 502, the 9 extras being `.agents/hooks/test_ag_natural_guard.py`, with `.git` and any venv back on the walk.
4. Pi's commit trailer credited `gemini-3.1-pro`. No Gemini touched the work. Amended to `pi + grok-4.5`.

Sab's ruling: reviewer step dropped as redundant while Claude is already the verification gate. Pi-subagent reliability is what the active droid mission audits.

## Next

- Phases 2–3 between missions; Phase 4 after (the suite is the regression net during live runs)
- Merge `chore/phase1-trim` → `main`, push, then pull on mini and VM — **only on Sab's go, after mission 1 clears**

------------------------------------------------ Agent Section END
