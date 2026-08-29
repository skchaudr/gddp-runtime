# 106 — Orchestrator context-contract gap (diagnosis only, no code changed)

------------------------------------------------ Agent Section START

Date: 2026-08-27
Worktree: /Users/sab-mini/repos/gddp-runtime (read-only this session; analysis ran from ~/.pi)
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

The persistent orchestrator's context blowup (p50 177K, max 246K) is caused upstream of compaction: it receives `_PACKET_PREAMBLE` plus a NodePacket and nothing describing the project, so it reconstructs "what is GDDP" from the filesystem every run — 29 `read` calls and 120 `bash` calls against only 16 `subagent` dispatches in the 2026-08-20 session. The evaluator already solved this exact problem (bounded canonical pointers, coverage measurement, four-zone prefix-cache-ordered prompt) and none of it was carried across to `pi_rpc_adapter.py`. No code was changed this session; this is diagnosis with file-level pointers to the fixes.

### Scope touched (One file per line, +/- for only what was changed)

+ .handoffs/106-orchestrator-context-contract-gap.md (this file — only file written; all source read-only)

### Constrained areas touched (none / list + justification)

none — no runtime, db, graph-truth, deploy, or scripts mutation. Session logs read from `~/.pi/agent/sessions/`.

## Concern 1 — the evaluator has a context contract; the orchestrator has none

Evaluator, `scripts/runtime/verification/semantic/`:
- `context_builder.py::build_canonical_pointers()` — bounded set of file *paths*: readme, project_brief, invariants (optional), foundational node, direct `depends_on`/`unlocks` neighbors. Docstring states the rule: "a read call is evidence, an embedded blob is not." Target-repo `AGENTS.md` explicitly never included; missing files marked `UNAVAILABLE` rather than dropped.
- `prompt.py` — four zones ordered least-to-most volatile (protocol / project / node / attempt), each internally `sort_keys=True`. The comment names the failure mode: one merged `json.dumps(sort_keys=True)` hoists `deterministic_result` ahead of `graph` and busts the cached prefix on every evaluation.
- `orchestrator.py::_compute_context_coverage()` / `_extract_accessed_paths()` — records which pointers were actually opened; asserted on the receipt in `test_orchestrator.py`.

Orchestrator, `scripts/adapters/pi_rpc_adapter.py`:
- `_PACKET_PREAMBLE` (L72–112) — ~40 lines of behavioral prose. Tells it how to act; says nothing about what the project is.
- No pointer list, no zone ordering, no cache topology, no coverage record.
- `_DEFAULT_MODEL = "xai/grok-4.5"` (L62) — hardcoded fallback; prime suspect for a chosen cheap orchestrator model not taking effect.
- `_DEFAULT_IDLE_TIMEOUT_S = 43200.0` (L70, 12h) — deliberate and correct for cross-packet continuity, but it means nothing excavated is ever released.

Neither agent is *briefed* — the evaluator also opens its own pointer files. The difference is that the evaluator's excavation is fenced to ~5-8 named paths and measured afterwards, while the orchestrator's is unbounded and unobserved.

## Concern 2 — unowned orchestration efficiency shifts the bill to the harness

Pi's native compaction triggers at `contextWindow - reserveTokens` (default 16384), i.e. ~184K on a 200K model, so the orchestrator carried near-ceiling context on every tool call for the life of each run. Measured from `~/.pi/agent/sessions/--Users-sab-mini-repos-gddp-runtime--/`:

| session | reqs >1K ctx | p50 ctx | p90 ctx | max | total input |
|---|---|---|---|---|---|
| 2026-08-20 | 205 | 176,894 | 233,371 | 245,760 | 34,365,343 |
| 2026-08-23 | 147 | 120,144 | 174,590 | 185,471 | 16,172,338 |
| 2026-08-24 | 81 | 116,216 | 159,252 | 160,964 | 8,906,047 |

These are floors. The 08-20 run had 14 failed calls (6 request timeouts, 6 fetch failures, 1 connection error, 1 429) plus 3 aborts; a failed request records no usage, so each sent a full context that appears nowhere in the totals. Timeout probability rises with context size, so the blowup manufactures its own retries at the largest size the session reached.

Compaction cannot fix Concern 1 — summarizing away docs the orchestrator just read guarantees it reads them again. The harness should not be rebuilt to bail out the runtime.

## Immediately fixable, ordered by payoff-to-effort

1. `pi_rpc_adapter.py` — call `build_canonical_pointers()` when assembling the orchestrator preamble. The function exists and is tested; the orchestrator simply never calls it. Smallest diff, largest effect.
2. `pi_rpc_adapter.py` L62 — make the model explicit at the call site; delete or loudly warn on the `_DEFAULT_MODEL` fallback.
3. `pi_rpc_adapter.py` L72–112 — reorder the preamble stable-first, porting the zone pattern from `semantic/prompt.py`.
4. Add `<repo>/.pi/settings.json` with `compaction.reserveTokens` sized against the pinned orchestrator model's window. Gives an absolute ceiling with zero code; note Pi's `ExtensionContext` exposes no `settingsManager`, so static config is the only route.
5. Borrow `_compute_context_coverage()` for the orchestrator so context growth is observable live rather than forensically from session logs.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

`main` clean and tracking `origin/main`; this handoff is the only change and is uncommitted pending Sab's review. An earlier copy of this analysis was mistakenly committed to the `~/.pi` harness repo as `2d3a197` and needs reverting there — wrong repo, since every fix listed above is in this one.

### Artifacts (Filepath - Description, 1 line max per artifact)

`~/.pi/agent/sessions/--Users-sab-mini-repos-gddp-runtime--/*.jsonl` - source sessions behind every number above (08-20 / 08-23 / 08-24)
`docs/proposals/pure-orchestration-not-execution.md` - pre-existing proposal, NOT read this session; likely overlaps this diagnosis
`.handoffs/097-prefix-cache-prompt-templates.md` - prior prefix-cache work; the pattern Concern 1 says to port to the orchestrator

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Read `docs/proposals/pure-orchestration-not-execution.md` first to check how much of this was already specified, then do fixes 1 and 2 in `scripts/adapters/pi_rpc_adapter.py`. Harness-side compaction work is optional and explicitly deprioritized.

------------------------------------------------ Agent Section END

------------------------ Do NOT edit this file past this point

## Narrative / Trajectory (SAB ONLY)

### Intent going into/at start of session

### Interpretation of how the session went

### Friction experienced or anticipated

### What's Next (Momentum or Lack Thereof)
