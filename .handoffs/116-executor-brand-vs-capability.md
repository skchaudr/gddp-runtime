# 116 — Executor brand vs capability in mode validation

------------------------------------------------ Agent Section START

Date: 2026-09-03
Worktree: /Users/sab-mini/repos/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

`allowed_execution_modes` was found to conflate executor *capability* (`human` vs `agent` — real graph truth) with executor *brand* (`droid`, `jules` — evidence, not intent), a day-one 2026-03-12 schema field with no design discussion, already flagged as "Known-contradictory" in `docs/learning/reckoning-2026-07-31.md` open question 4 and never ruled on. Two commits landed: mode-validation fixes (phantom removal + drift test, neutral default, auto-advance dead-brand fallback), then three false capability declarations corrected after an audit. HEAD `314777e`, 888 passed (was 870), main == origin/main.

## Scope touched (One file per line, +/- for only what was changed)

~ `scripts/runtime/heartbeat/graph_reader.py` — `DEFAULT_EXECUTION_MODE_ALLOWLIST` → `EXECUTION_MODE_ADAPTERS`; new `ABSTRACT_EXECUTION_MODES`; dropped 4 phantom modes; omitted-field default `["jules"]` → `["agent"]`; kwarg/attr `execution_mode_allowlist` → `execution_mode_adapters`
~ `scripts/runtime/heartbeat/frontier.py` — new `_auto_dispatch_routing()`; removed `default_executor or "jules"` fallback
~ `scripts/runtime/heartbeat/classifier.py` — `_ABSTRACT_EXECUTION_MODES` now imported from graph_reader, not redeclared
+ `scripts/runtime/heartbeat/test_execution_modes.py` — 9 tests (registry drift, abstract modes, phantom pin, neutral default, auto-advance routing)
~ `scripts/runtime/heartbeat/test_mission_config.py` — kwarg rename
~ `scripts/adapters/test_cursor_cli_adapter.py` — constant rename
~ `scripts/adapters/local_subprocess_adapter.py` — new `capabilities()`: `cancellation="preemptive"` (was synthesized `"none"` while `cancel()` SIGTERMs); droid inherits
~ `scripts/adapters/mission_adapter.py` — new `capabilities()`: `cancellation="preemptive"`, `engagement=True`
~ `scripts/adapters/jules_api_adapter.py` — new `capabilities()`: `reply=True` (implements `reply()`); `cancellation` stays `"none"` and is correct
+ `scripts/adapters/test_capability_truthfulness.py` — 9 tests pinning declarations against the implementing code

## Constrained areas touched (none / list + justification)

None. Zero gddp-config changes: all 216 node YAMLs declare `allowed_execution_modes` explicitly, so the default flip is inert against current graphs. Node YAML is human-owned graph truth; only the runtime's *interpretation* was changed.

## Current Git state (2-3 sentences max, anything more must be critically justifiable)

main = origin/main = `e448467`, clean tracked tree. Untracked locals unchanged (`.atuin/`, `.factory/`, `.local/`, `node_status_history/aa-cli-tui-pass/`). gddp-config has inherited uncommitted state, untouched and unclassified: `M verification/vault-doctor/auth-node.json`, `?? verification/aa-cli-tui-pass/evaluations.yaml`.

## Artifacts (Filepath - Description, 1 line max per artifact)

- `scripts/runtime/heartbeat/test_execution_modes.py` — the drift test is the only thing keeping the mode registry honest; graph_reader cannot import dispatcher (cycle)
- `docs/proposals/executor-capability-contract.md` — pre-existing 1003-line capability analysis; §1.10 P6 "four surfaces must agree" and its line refs now name the renamed constant (doc is a dated snapshot, deliberately not rewritten)

## Resume point (2-3 sentences max, anything more must be critically justifiable)

**Landed:** brand/capability separation in mode validation; three false capability declarations corrected.

**Operator ruling 2026-09-03: capability checks are for clarity, never to gate or deny a run.** `requires_capabilities` stays unbuilt. Do not add a node field or a preflight branch that refuses dispatch because an adapter's declaration is missing a property. `capabilities.json` on the attempt is the clarity surface. Per-adapter `capabilities()` must stay honest so that file is readable.

**Do not reopen the factory/droid mission as a capability prerequisite.** That mission already ran on this repo, expanded far past an executor adapter (handoff 089: +19,639 / 123 files, twelve new stop points), and nearly all of it was reverted. Demolition rule still holds: no new production surface that makes GDDP stop.

**`requires_capabilities` was considered and rejected for a stronger reason than the audit.** The audit said "don't encode brand rationales as node requirements yet." The operator said: do not encode them as requirements at all. A declaration that cannot refuse a run is a label. A declaration that can refuse a run is the mission-scope failure again.

**Still useful, still non-gating:** finish remaining adapter declarations so every registered transport writes a complete `capabilities.json` (Jules action adapter still synthesizes the least-capable default). `dispatcher.py:179` refusing `dispatch_engagement` on a non-engagement adapter is "wrong API for this transport," not "this node may not run." Leave that. Do not grow it into node-level denial.

**Run-history caveat for the adapter-list run-count idea:** the executor label does not identify what ran. 37 attempts recorded as `local_subprocess` actually executed `/opt/homebrew/bin/pi` via the argv wrapper; disk classification of 120 spool dirs is 111 pi_rpc / 9 droid / 0 cursor. Counts must key on the resolved binary from `command.json`, not the executor name.

**Also still open:** `cursor_cli` has zero production dispatch evidence (0 rows in `jobs`/`executor_sessions`/`results`) and zero declarations in any graph; run it via `GDDP_EXECUTOR_OVERRIDE=cursor_cli` (no graph edit needed) and read `context_coverage.json` / `prompt_cache_report.json` / `exit.json`. Handoff 115's open list is otherwise unchanged.

------------------------------------------------ Agent Section END

------------------------ Do NOT edit this file past this point

## Narrative / Trajectory (SAB ONLY)

### Intent going into/at start of session

### Interpretation of how the session went

### Friction experienced or anticipated

### What's Next (Momentum or Lack Thereof)
