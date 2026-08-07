# AGENTS.md — PROBE-2A

Operational guidance for workers. Read this before starting any feature.

## Mission Boundaries (NEVER VIOLATE)

**Files:** Only `calc.py` and `test_calc.py` may ever be modified. No README, no docs, no
`.gitignore`, no config files, no new files of any kind.

**Git:**
- Never `git push`. Never create remotes. Never create tags.
- Never `git rebase`, `git amend`, `git reset --hard`, `git cherry-pick`, or rewrite history.
- Never create a new branch. You work on `probe2a` only.
- Never touch `/Users/sab-mini/probe2-gddp/repoA` (the sibling checkout on `main`).
- Never touch `/Users/sab-mini/probe2-gddp/repoB`.
- Never touch `baseA.sha` or `baseB.sha`.

**Receipts:**
- `receiptsA.jsonl` is append-only and may ONLY be written by `gddp-node-receipt`.
- Never hand-edit, rewrite, reorder, or delete lines in the ledger.
- Never run `gddp-node-receipt` more than once for a node that already succeeded.
- Never run `gddp-node-receipt` before the commit exists.
- Never defer or batch receipts — each receipt is taken immediately after its commit.

**Commits:**
- Exactly one commit per node. Never combine two nodes in one commit.
- Never split one node across two commits.
- Never create an untrailed commit (no setup, scaffolding, integration, cleanup, or fix commits).
- Every commit message MUST contain the exact trailer line `GDDP-Node-Id: <feature-id>`.
- The trailer must be in the final paragraph of the commit message (where git recognizes trailers).

**Working directory:** All git and receipt commands must be run from the worktree root
`/Users/sab-mini/probe2-gddp/repoA-wt-probe2a`.

If you cannot complete your work within these boundaries, return to orchestrator. Never violate boundaries.

## Mission Directives

**Tools:**
- `python3 -m pytest -q` — the test suite (run from worktree root)
- `git` — staging, committing, status inspection
- `gddp-node-receipt` — the receipt CLI (run from worktree root, after commit)

**Skills:**
- Invoke `mission-worker-base` for session setup (read mission files, run init.sh, baseline tests).
- Invoke `gddp-node-worker` for the work procedure.

**Dependencies:**
- Python 3.14.6 + pytest 9.1.1 (pre-installed, no virtual env needed)
- `gddp-node-receipt` at `/Users/sab-mini/probe2-gddp/bin/gddp-node-receipt` (on PATH)
- `GDDP_RECEIPTS_PATH` environment variable must be set to `/Users/sab-mini/probe2-gddp/receiptsA.jsonl`

**Other rules:**
- The pre-existing `add` function and its test must never be modified. The import line in
  `test_calc.py` may grow (e.g. `from calc import add, inc`), but `add`'s body and `test_add`'s
  body must stay byte-identical to the baseline.
- Every node after `n1-base` must be implemented by calling its declared parent function(s) —
  never by re-deriving the arithmetic inline. The call graph of `calc.py` must literally be the
  GDDP dependency graph.
- `label_chain` and `final_summary` must return deterministic strings: no timestamps, no
  `hash()`, no `id()`, no `random`, no set/dict iteration order. The test must pin the exact
  expected string with a string literal for at least one concrete input.
- If a previous node was committed incorrectly, do NOT fix it. Report the discrepancy and return.

## Coding Conventions

- `calc.py` is a flat module of pure functions. No classes, no imports beyond stdlib.
- `test_calc.py` is a flat module of `test_*` functions. No fixtures, no parametrize, no classes.
- Functions are added at the bottom of the file, preserving existing content above.
- Tests import from `calc` at the top of `test_calc.py`, growing the import line as needed.

## Testing & Validation Guidance

**Instructions for validators. Validators must follow these.**

### ABSOLUTE PROHIBITION

**Never run `gddp-node-receipt`**, not even with a redirected `GDDP_RECEIPTS_PATH`. Never commit.
Never modify `calc.py` or `test_calc.py`. Never create fixtures, seed data, or any file. Validation
is **strictly read-only**. A stray receipt or commit is unrecoverable and fails the mission.

### How to validate

1. **Code behavior** — use `python3 -c "import calc; ..."` for numeric probes, monkeypatch
   delegation checks, and AST call-graph walks. See `validation-contract.md` for exact commands.
2. **Test suite** — `python3 -m pytest -q` must exit 0.
3. **Git chain** — `git log`, `git show`, `git diff-tree`, `git reflog` to inspect commits,
   trailers, linearity, file scope, and history integrity.
4. **Receipt ledger** — `jq`, `wc`, `python3` to inspect `receiptsA.jsonl`. Verify line count,
   JSON validity, canonical serialization, contiguity, and cross-consistency with git.
5. **Cross-process purity** — `env PYTHONHASHSEED=0 python3 -c "..."` vs
   `env PYTHONHASHSEED=12345 python3 -c "..."` piped through `diff`.

### What NOT to do

- Do not replay the test suite at historical commits (that requires checking out old trees,
  which mutates the worktree).
- Do not create any temporary files in the repo.
- Do not start any services or long-running processes.
- Any defect found is reported back to the orchestrator — do not attempt fixes.

### Known pre-existing issues

None at mission start.
