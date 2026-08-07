# PROBE-2A: exact eight-node GDDP projection with per-node receipts

## Plan Overview

Execute the externally-dictated GDDP projection literally: build up a tiny Python calculator (`calc.py`) through **exactly eight** dependency-ordered nodes, one commit and one receipt per node.

The external GDDP control plane owns decomposition and identity. My role here is **not** to design a decomposition — it is to project the dictated graph faithfully into mission artifacts and enforce the per-node protocol with zero drift.

**Requirements I have captured (echoed back for confirmation):**

- Exactly 8 features — no more, no fewer.
- Feature ids exactly, in exactly this array order: `n1-base`, `n2-left`, `n3-right`, `n4-merge`, `n5-chain`, `n6-chain`, `n7-chain`, `n8-final`.
- Exactly one milestone, id/name exactly `probe2a`.
- No setup, scaffolding, validation, scrutiny, user-testing, cleanup, documentation, integration, refactor, or final-verification features.
- No renaming, merging, splitting, re-decomposing, or synthesizing features.
- Preserve the topological array order exactly, even where the diamond siblings (`n2-left`, `n3-right`) could theoretically be exchanged.
- Per feature: only that node's tiny `calc.py` change + its matching `test_calc.py` test. No README edits, no unrelated files.
- Per feature: capture `BASE` before the change → tests pass → **exactly one** commit carrying the exact trailer `GDDP-Node-Id: <feature-id>` → capture `RESULT` → run `gddp-node-receipt --node-id <feature-id> --base "$BASE" --result "$RESULT"`.
- A feature is not complete until its receipt command succeeds and appends its record. Never defer, never batch.
- Never combine two nodes in one commit. Never create an untrailed setup/integration commit. Never call the receipt before committing. Never call a receipt more than once for a successful feature.
- Do not push. Do not create remotes or tags.
- Completion = exactly eight linear trailer-bearing commits above the baseline, and exactly eight successful receipt lines forming a contiguous base→result SHA chain in the dictated order.

## Expected Functionality

### Milestone: `probe2a` (the only milestone)

| # | Feature id | Depends on | Adds to `calc.py` |
|---|-----------|-----------|-------------------|
| 1 | `n1-base` | — | `inc(x)` → `x + 1` |
| 2 | `n2-left` | `n1-base` | `double_after_inc(x)` → `2 * inc(x)` |
| 3 | `n3-right` | `n1-base` | `square_after_inc(x)` → `inc(x) ** 2` |
| 4 | `n4-merge` | `n2-left` + `n3-right` | `sum_paths(x)` → sum of both siblings |
| 5 | `n5-chain` | `n4-merge` | `negate_merge(x)` via `sum_paths` |
| 6 | `n6-chain` | `n5-chain` | `absolute_chain(x)` via `negate_merge` + `abs` |
| 7 | `n7-chain` | `n6-chain` | `label_chain(x)` via `absolute_chain`, deterministic string |
| 8 | `n8-final` | `n7-chain` | `final_summary(x)` via `label_chain`, deterministic final string |

Each row is one worker session, one commit, one receipt.

## Architecture

**Dependency graph (persisted verbatim in `architecture.md`):**

```text
n1-base -> n2-left
n1-base -> n3-right
n2-left + n3-right -> n4-merge
n4-merge -> n5-chain -> n6-chain -> n7-chain -> n8-final
```

`n2-left` and `n3-right` are the diamond siblings. Although the graph does not order them relative to each other, the features array and execution order are pinned to the dictated sequence.

**Code shape.** `calc.py` is a flat module of pure functions. Every node after `n1-base` is implemented strictly *by calling* its declared parent(s) — never by re-deriving the arithmetic inline. This makes the dependency graph structurally visible in the source: the call graph of `calc.py` is the GDDP graph. `test_calc.py` grows one test per node alongside.

**Two parallel append-only chains.** The mission produces two artifacts that must stay in lockstep:

1. **Git chain** — eight linear commits above baseline `a96356a`, each carrying exactly one `GDDP-Node-Id` trailer.
2. **Receipt chain** — eight JSON lines in `/Users/sab-mini/probe2-gddp/receiptsA.jsonl`, where receipt *k*'s `base` equals receipt *k−1*'s `result`, and receipt 1's `base` is the baseline.

The per-feature protocol is the mechanism that keeps them in lockstep, so it is enforced in three redundant places: the worker skill procedure, `AGENTS.md` mission directives, and each feature's own `expectedBehavior`.

**Receipt tool contract (verified by reading the source).** `gddp-node-receipt` appends one JSON line to the file named by the `GDDP_RECEIPTS_PATH` environment variable and hard-fails if that variable is unset. It records `node_id`, `base`, `result`, plus live `git_head` / `git_branch` / `git_toplevel` read from the current working directory. Two consequences drive the design: the receipt **must** be invoked from the worktree root (so `git_toplevel` is correct), and it **must** be invoked after the commit (so `git_head` equals `result`).

## Environment Setup

Nothing to install — the environment is already complete and verified.

- Worktree: `/Users/sab-mini/probe2-gddp/repoA-wt-probe2a`, branch `probe2a`, HEAD `a96356a` (matches `baseA.sha`).
- `init.sh` is a no-op idempotent guard that only asserts preconditions: `GDDP_RECEIPTS_PATH` is set, `gddp-node-receipt` is on `PATH`, and `python3`/`pytest` are runnable. It creates nothing and commits nothing.

## Infrastructure

**Services:** none. No databases, no servers, no ports, no network.

**Boundaries:**
- Only two files may ever be modified: `calc.py` and `test_calc.py`.
- Off-limits: `README`/any docs, `/Users/sab-mini/probe2-gddp/repoA` (the sibling checkout on `main`), `/Users/sab-mini/probe2-gddp/repoB`, `baseA.sha`, `baseB.sha`.
- `receiptsA.jsonl` is append-only and may only be written by `gddp-node-receipt` — never hand-edited, never rewritten.
- No `git push`, no remotes, no tags, no history rewriting, no branch creation.

## Testing Strategy

**Unit tests only** — that is the entirety of the appropriate surface here. There is no UI, CLI, or API.

- Per node: one focused pytest test in `test_calc.py`, written before the implementation (red → green).
- Milestone gate command: `python3 -m pytest -q` (full suite; it runs in well under a second, so no scoping needed).
- No typecheck or lint tooling exists in this repo, and adding one would require an untrailed setup commit, which the protocol forbids. So the programmatic gate is the test command alone.

## User Testing Strategy

There is no interactive surface to drive, so `agent-browser`/`tuistory` do not apply. "User testing" here means inspecting the two chains the mission exists to produce, entirely read-only:

- `python3 -m pytest -q` → all tests pass.
- `git log` → exactly eight commits above `a96356a`, linear, each with exactly one correct `GDDP-Node-Id` trailer in the dictated order.
- `receiptsA.jsonl` → exactly eight lines, node ids in the dictated order, `base`/`result` forming a contiguous chain, each `result` matching the corresponding commit SHA.

**Important constraint on validation.** The mission runner auto-injects a scrutiny validator and a user-testing validator when the `probe2a` milestone completes. That injection is system-owned and I cannot suppress it — but I can constrain its behavior, and I will, via a binding `Testing & Validation Guidance` section in `AGENTS.md`: validators run **strictly read-only**. No fixtures, no seed data, no file edits, no commits, no receipt invocations. Any defect they find is reported back to me, and I schedule a fix node rather than letting a validator touch the repo. This keeps the eight-commit / eight-receipt invariant intact.

## Mission Readiness

All checks executed and passing:

| Dependency | Status | How verified |
|---|---|---|
| `python3` | ✅ 3.14.6 | `python3 --version` |
| `pytest` | ✅ 9.1.1 | `python3 -m pytest --version` |
| Baseline suite | ✅ 1 passed | `python3 -m pytest -q` |
| `gddp-node-receipt` | ✅ functional | Executed against a **throwaway temp ledger**, produced a well-formed record, temp file removed. The real `receiptsA.jsonl` was deliberately **not** touched, so the eight-line chain starts clean. |
| `GDDP_RECEIPTS_PATH` | ✅ `/Users/sab-mini/probe2-gddp/receiptsA.jsonl` | `env` — set and inherited |
| Git worktree state | ✅ clean, `probe2a` @ `a96356a` | `git status`, `git worktree list` |

`receiptsA.jsonl` does not yet exist; the tool creates it on first append. No allowlisting, credentials, or network access are required.

## Non-Functional Requirements

- **Fidelity over judgment.** Where my instincts as an architect conflict with the dictated shape, the dictated shape wins. I will not "improve" the decomposition.
- **Atomicity.** One node = one commit = one receipt. A worker that cannot achieve this returns to me rather than improvising.
- **No retroactive repair.** A receipt is never re-run for an already-successful node. If a node's commit is wrong, I stop and surface it rather than layering a corrective commit that would break the eight-commit invariant.
- **Determinism.** `label_chain` and `final_summary` return fixed-format strings pinned by their tests, so the final state is reproducible.
