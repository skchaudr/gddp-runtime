# 084 — What moved under you: trim surface for in-flight branches

Written for any branch cut before `faa6885` that now has to rebase onto `main`
— `feat/pi-rpc-adapter` first among them. This is a rebase aid, not a history.
The narrative lives in commit messages and `083`.

**Landed on `main`:** `fa988e5..faa6885` (11 commits). Suite `633 passed / 0 failed`.
Companion commit in gddp-config: `f442019`.

## The four things that will bite a rebase

### 1. Two modules were renamed (Phase 2A, `59c731e`)

| was | is |
|---|---|
| `scripts/runtime/gates.py` | `scripts/runtime/gate_tokens.py` |
| `scripts/runtime/heartbeat/provisional_gate.py` | `scripts/runtime/heartbeat/provisional_status.py` |
| `scripts/runtime/test_gates.py` | `scripts/runtime/test_gate_tokens.py` |
| `scripts/runtime/heartbeat/test_provisional_gate.py` | `scripts/runtime/heartbeat/test_provisional_status.py` |

Zero logic changed — pure name substitution, verified line by line. Git tracked
all four as renames, so a rebase usually carries your edits across. What it will
*not* fix for you: `monkeypatch.setattr("...gates...")` target strings and any
import you wrote against the old paths. Grep your branch for `runtime.gates`,
`from .gates`, and `provisional_gate` before you trust a clean rebase.

Why the rename: `gates.py` (dependency tokens) and `provisional_gate.py`
(heartbeat status) had nothing to do with each other and were being conflated in
conversation and in agent reads. The word "gate" was doing two jobs.

`gates.py` was hot — the two commits immediately before this branch both touched
it. If your branch also touched it, expect a content conflict inside the renamed
file. That is a normal resolution, not a sign the rename went wrong.

### 2. `jules_cli` is gone — but you probably already knew

`jules_cli_adapter.py` is archived to `scripts/_archive/`. Registration removed
from `dispatcher.ADAPTERS`, along with two unreachable cancellation branches
(`e137de9`).

**Both lanes reached this independently.** Mission work on `origin/main` had
already dropped `jules_cli` from `ADAPTERS` before this branch rebased onto it.
So for most branches this is a no-op. Measured basis: zero of 14 graphs in
gddp-config name `jules_cli`.

Behavior change worth knowing: a legacy `jules_cli` session row that gets
cancelled now resolves `cancel_failed` rather than `cancel_unsupported`.
`cancel_unsupported` is still a legal *stored* state for existing rows — only
the code that writes it is gone.

### 3. Prompt rendering moved to a module owned by no transport

`scripts/adapters/session_prompt.py` — `build_session_instructions()` and
`flatten()`, both module-level.

It used to be `JulesCliAdapter._build_session_instructions`, a pure string
builder with no subprocess, which the API adapter reached across transports to
borrow. If your adapter renders a `NodePacket` into a prompt, import it from
here. Do not re-derive it.

The move was byte-for-byte; `test_executor_contract.py` still asserts the Action
adapter and `session_prompt` render equivalent bodies, which is what proves it.

### 4. Files that no longer exist where you left them

Archived to `scripts/_archive/` (inert; `pytest.ini` excludes the directory):
`jules_cli_adapter.py`, `test_jules_cli_adapter.py`, `replay.py`,
`test_replay.py`, and the canary trio.

Deleted outright (zero importers): `scripts/runtime/decision_loop/` (12 files),
`scripts/node_status_history.py`, `patch.diff`.

If a rebase reintroduces any of these, that is your branch resurrecting them —
drop the hunk.

## Adapter registration, current shape

`dispatcher.py` now routes three ways. Getting this wrong is a canary-time
surprise, not a test-time one.

- `ADAPTERS` — direct adapters the runtime dispatches and polls itself
- `MEDIATED_ADAPTERS` — `jules` only; dispatch goes out through a GitHub issue
  and the executor is triggered by label, so there is no durable session to poll
- `_LOCAL_TRANSPORT_EXECUTORS` — the subset of `ADAPTERS` that runs inside a
  local checkout and therefore receives `repo_path` as cwd, via `_build_adapter`

On `main` that frozenset is `{"local_subprocess", "droid", "factory_mission"}`.
It is name-keyed rather than class-keyed so tests can substitute duck-typed
doubles.

A new transport adapter has to answer one question: does it execute inside a
checkout on this machine? If yes it belongs in the frozenset; if it dispatches
somewhere remote it does not. `feat/pi-rpc-adapter` resolved this correctly in
its own rebase — the supervisor creates a worktree from the local checkout and
spawns `pi --mode rpc` inside it, so `pi_rpc` is local transport and takes
`repo_path` as cwd.

## Two open items, deliberately not closed

**A test covers a path no live graph reaches.**
`test_dry_run_e2e.py::test_verify_e2e_clean_pass_returns_receipt_without_repo_writes`
is the only test asserting "deterministic lane resolves the node alone, semantic
never invoked." It only ever passed because its fixture borrowed an `aa-cli`
registry key. It is green now via a neutral monkeypatched fixture, but every
live node escalates to the semantic lane. Keeping or dropping it is Sab's call.

**The deterministic lane's real gap is the `command:` field.** Criterion
resolution in `evaluate_criterion` (`probes.py`) tries an explicit `command:`
first — subprocess, exit 0 is pass — before any probe lookup. Exactly **1 of 493**
live criteria across all 14 graphs uses it. Filling those in is worth more than
any registry work. No loader was built; build one when a project needs it.

## Phase 3 is deliberately not started

It would move `shape_profiles/` and `retry_budget.py` — more churn in
`scripts/runtime/` while in-flight branches are rebasing onto it. Held until
`feat/pi-rpc-adapter` lands. Phase 4 (`test_executor_sessions.py`, still the
largest test file) after that.

## Lesson recorded from this trim

"Zero importers" is the right test for a library module and the **wrong** test
for a CLI entrypoint. `replay.py` had no importers and was correctly identified
as an orphan — but README documented `python3 -m runtime.replay` in five places,
including its own section with copy-pasteable commands. Nothing caught that until
a post-rebase grep. Before archiving anything with a `__main__` block, grep the
docs, `deploy/`, and the runbook, not just the imports.
