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

**`requires_capabilities` is deliberately NOT built.** The operator's four brand rationales were: droid = long-horizon mission mode with robust validation (node-to-node "kills missions"); jules = async/remote/will-drop; pi = subagents + chained runs + multi-model; cursor = harness/observability/grok-composer roster. Evidence says do not encode these as node requirements yet:
1. Only 4 of 11 capability fields are load-bearing (`engagement`, `resume`, `cancellation`, `midturn_steering`). `native_subagents`, `streaming_events`, `structured_tool_calls`, `usage_reporting`, `partial_text`, `reply` are written to `capabilities.json` and never read back for a decision — so three of the four rationales map to fields that gate nothing.
2. The one rationale that maps to a load-bearing field (droid → `engagement`) names the wrong transport: `droid` is a `LocalSubprocessAdapter` subclass with `engagement=False`; mission mode is `factory_mission`. 13 node files across 5 projects declare `droid`; only `pi-harness-execution` declares `factory_mission` (7 nodes).
3. `factory_mission`'s record is 29 jobs / 17 failures, but those are retry storms on five "execute" nodes plus a `mappingproxy is not JSON serializable` dispatch bug and one operator cancellation — unfinished, not unsound. It has never completed a clean multi-node run. `droid` (per-node) has the cleanest record in the dataset: 8 jobs, 8/8 `awaiting_review`. A node requiring `engagement` would demand the least-proven path.

**Next, in order:** (a) fix the `factory_mission` `mappingproxy` dispatch bug and get one clean multi-node mission run before any node declares `engagement`; (b) converge the two `engagement` read sites — `dispatcher.py:179` reads `capabilities.engagement`, `reconciler.py:284` reads `supports_engagement()`; (c) decide whether the 7 decoration fields become explicitly descriptive-only or get deleted; (d) `docs/proposals/executor-capability-contract.md` §4 has 8 stale claims (cursor_cli listed "proposed", matrix missing 5 executors, resume listed unreachable).

**Run-history caveat for the adapter-list run-count idea:** the executor label does not identify what ran. 37 attempts recorded as `local_subprocess` actually executed `/opt/homebrew/bin/pi` via the argv wrapper; disk classification of 120 spool dirs is 111 pi_rpc / 9 droid / 0 cursor. Counts must key on the resolved binary from `command.json`, not the executor name.

**Also still open:** `cursor_cli` has zero production dispatch evidence (0 rows in `jobs`/`executor_sessions`/`results`) and zero declarations in any graph; run it via `GDDP_EXECUTOR_OVERRIDE=cursor_cli` (no graph edit needed) and read `context_coverage.json` / `prompt_cache_report.json` / `exit.json`. Handoff 115's open list is otherwise unchanged.

------------------------------------------------ Agent Section END

------------------------ Do NOT edit this file past this point

## Narrative / Trajectory (SAB ONLY)

### Intent going into/at start of session

### Interpretation of how the session went

### Friction experienced or anticipated

### What's Next (Momentum or Lack Thereof)
