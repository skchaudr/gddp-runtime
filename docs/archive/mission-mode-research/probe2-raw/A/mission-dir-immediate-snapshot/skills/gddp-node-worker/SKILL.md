---
name: gddp-node-worker
description: Executes one GDDP node: write a failing test, implement the function by calling its declared parent(s), run tests, commit exactly once with the GDDP-Node-Id trailer, and invoke gddp-node-receipt.
---

# GDDP Node Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## Required Skills and Tools

- `mission-worker-base` — session setup (read mission files, run init.sh, baseline tests)
- `python3 -m pytest -q` — test runner
- `git` — staging and committing
- `gddp-node-receipt` — receipt CLI (run from worktree root, after commit)
- `GDDP_RECEIPTS_PATH` — environment variable (verified by init.sh)

## Work Procedure

You are implementing exactly ONE node of the GDDP projection. Your feature description tells you
which function to add, which parent(s) it must call, and what it must return. Follow these steps
in this exact order. **Do not skip or reorder any step.**

### Step 1: Verify preconditions

1. Confirm you are in the worktree root: `pwd` must print
   `/Users/sab-mini/probe2-gddp/repoA-wt-probe2a`.
2. Confirm the branch: `git branch --show-current` must print `probe2a`.
3. Confirm the working tree is clean: `git status --porcelain` must be empty (or show only
   untracked `__pycache__/`).
4. Confirm `GDDP_RECEIPTS_PATH` is set: `echo "$GDDP_RECEIPTS_PATH"` must print
   `/Users/sab-mini/probe2-gddp/receiptsA.jsonl`.
5. Confirm `gddp-node-receipt` is on PATH: `command -v gddp-node-receipt`.
6. Run the baseline test suite: `python3 -m pytest -q` — all tests must pass.

If any precondition fails, return to orchestrator. Do not attempt to fix environment issues.

### Step 2: Capture BASE

```sh
BASE=$(git rev-parse HEAD)
echo "BASE=$BASE"
```

Record this value. It is the `--base` argument for the receipt. For node 1, this will be the
mission baseline `a96356a...`. For subsequent nodes, it will be the previous node's commit SHA.

### Step 3: Write the failing test (RED)

Read the existing `test_calc.py`. Add a new `test_*` function at the bottom that tests your
node's function. Import your function by extending the import line at the top.

**For numeric nodes (n1 through n6):** assert the function returns the correct value for at least
3 representative inputs. Include `x=0` and at least one negative input. For `n6-chain`
(`absolute_chain`), you MUST include `x=-2` in your probe set — it is the only integer that
distinguishes a correct implementation from one that returns `sum_paths(x)`.

**For string nodes (n7, n8):** assert the function returns the exact expected string for at least
one concrete input, using a string literal on the right-hand side of `==`. Also assert the value
is a `str` and that the numeric content appears as a substring.

Run `python3 -m pytest -q`. Your new test MUST FAIL (the function doesn't exist yet). If it
passes or errors with an import error, that's expected — the point is that the test is in place.

### Step 4: Implement the function (GREEN)

Read the existing `calc.py`. Add your function at the bottom of the file.

**CRITICAL — the delegation invariant:** your function MUST call its declared parent function(s).
Never re-derive the arithmetic inline. The call graph of `calc.py` must literally be the GDDP
dependency graph. Specifically:

| Node | Function | Required implementation |
|------|----------|------------------------|
| `n1-base` | `inc(x)` | `return x + 1` |
| `n2-left` | `double_after_inc(x)` | `return 2 * inc(x)` |
| `n3-right` | `square_after_inc(x)` | `return inc(x) ** 2` |
| `n4-merge` | `sum_paths(x)` | `return double_after_inc(x) + square_after_inc(x)` |
| `n5-chain` | `negate_merge(x)` | `return -sum_paths(x)` |
| `n6-chain` | `absolute_chain(x)` | `return abs(negate_merge(x))` |
| `n7-chain` | `label_chain(x)` | deterministic string built from `absolute_chain(x)` |
| `n8-final` | `final_summary(x)` | deterministic string built from `label_chain(x)` |

Writing `return (x + 1) ** 2` instead of `return inc(x) ** 2` produces the same numbers but
**breaks the architecture** — the edge `n1-base -> n3-right` disappears from the call graph.
This applies to every node.

**For string nodes (n7, n8):** the returned string must be a pure function of the input. No
timestamps, no `hash()`, no `id()`, no `random`, no set/dict iteration order. Whatever format you
choose, your test pins it with a string literal, so it is permanent.

Run `python3 -m pytest -q`. ALL tests must pass (including the baseline `test_add` and all
previous nodes' tests). If any test fails, fix your implementation and re-run. Do NOT commit
until all tests pass.

### Step 5: Commit exactly once

Stage both files and commit with a message containing the exact trailer:

```sh
git add calc.py test_calc.py
git commit -m "probe2a: add <function_name>" -m "GDDP-Node-Id: <feature-id>"
```

Replace `<function_name>` with your function's name and `<feature-id>` with your feature's id
(e.g. `n1-base`, `n2-left`, etc.).

**The trailer `GDDP-Node-Id: <feature-id>` MUST be in the commit message.** It must be an exact
match: `GDDP-Node-Id: n1-base` — single space after the colon, no leading whitespace, no trailing
whitespace. The trailer must be in the final paragraph of the message (using `-m` twice puts the
trailer in the body, which is the final paragraph — this is correct).

Verify the trailer is present:
```sh
git show -s --format=%B HEAD | grep "^GDDP-Node-Id: <feature-id>$"
```
This must print exactly one line.

Verify exactly two files were changed:
```sh
git diff-tree --no-commit-id --name-only -r HEAD
```
This must print exactly `calc.py` and `test_calc.py`.

If either check fails, return to orchestrator. Do NOT amend or create another commit.

### Step 6: Capture RESULT

```sh
RESULT=$(git rev-parse HEAD)
echo "RESULT=$RESULT"
```

### Step 7: Invoke the receipt

From the worktree root, run exactly:

```sh
gddp-node-receipt --node-id <feature-id> --base "$BASE" --result "$RESULT"
```

Replace `<feature-id>` with your feature's id. The command must exit 0 and print a JSON record.

**Verify:**
- The command exited 0.
- The printed JSON has `node_id` equal to your feature id.
- The printed JSON has `result` equal to `$RESULT`.
- The printed JSON has `git_head` equal to `$RESULT` (proves the receipt was taken after the commit).
- The printed JSON has `base` equal to `$BASE`.

If any of these fail, return to orchestrator. Do NOT re-run the receipt.

### Step 8: Final verification

Run these checks:

1. **Test suite still green:**
   ```sh
   python3 -m pytest -q
   ```

2. **Receipt line count is correct:**
   ```sh
   wc -l < /Users/sab-mini/probe2-gddp/receiptsA.jsonl
   ```
   For node K (1-based), this must equal K.

3. **Working tree clean:**
   ```sh
   git status --porcelain
   ```
   Must be empty (or only untracked `__pycache__/`).

4. **Your function is callable and correct:**
   ```sh
   python3 -c "import calc; print(calc.<your_function>(0))"
   ```
   Must print the expected value.

All checks must pass. Only now is the node complete.

## Example Handoff

```json
{
  "salientSummary": "Implemented n3-right: added square_after_inc(x) returning inc(x)**2, with a passing test probing x=-5,0,3. Committed once with trailer GDDP-Node-Id: n3-right and recorded the receipt. All 4 tests green.",
  "whatWasImplemented": "Added square_after_inc(x) to calc.py, implemented as return inc(x) ** 2 (calls inc, does not re-derive). Added test_square_after_inc to test_calc.py with probes for x=-5 (16), x=0 (1), x=3 (16). Extended import line. Committed as a single commit with GDDP-Node-Id: n3-right trailer. Receipt appended to receiptsA.jsonl as line 3.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "python3 -m pytest -q", "exitCode": 0, "observation": "4 passed in 0.01s" },
      { "command": "git show -s --format=%B HEAD | grep '^GDDP-Node-Id: n3-right$'", "exitCode": 0, "observation": "GDDP-Node-Id: n3-right" },
      { "command": "git diff-tree --no-commit-id --name-only -r HEAD", "exitCode": 0, "observation": "calc.py\ntest_calc.py" },
      { "command": "gddp-node-receipt --node-id n3-right --base $BASE --result $RESULT", "exitCode": 0, "observation": "{\"base\":\"...\",\"git_branch\":\"probe2a\",\"git_head\":\"...\",\"git_toplevel\":\"/Users/sab-mini/probe2-gddp/repoA-wt-probe2a\",\"node_id\":\"n3-right\",\"result\":\"...\",\"timestamp_utc\":\"...\"}" },
      { "command": "wc -l < /Users/sab-mini/probe2-gddp/receiptsA.jsonl", "exitCode": 0, "observation": "3" },
      { "command": "git status --porcelain", "exitCode": 0, "observation": "" }
    ],
    "interactiveChecks": []
  },
  "tests": {
    "added": [
      {
        "file": "test_calc.py",
        "cases": [
          { "name": "test_square_after_inc", "description": "Verifies square_after_inc returns inc(x)**2 for x=-5 (16), x=0 (1), x=3 (16), ruling out x**2+1 and x**2 bugs" }
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- **Precondition failure:** environment not set up, wrong branch, dirty working tree, baseline
  tests failing.
- **Test failure you cannot resolve:** if after implementing the function correctly, tests still
  fail for reasons you cannot diagnose within the scope of your single node.
- **Trailer verification failure:** if the commit was created but the trailer check fails. Do NOT
  amend — return and report.
- **Receipt failure:** if `gddp-node-receipt` exits non-zero, or if the printed record has wrong
  field values. Do NOT re-run — return and report.
- **Previous node appears wrong:** if you discover that a prior node's function or commit is
  incorrect. Do NOT fix it — report and return.
- **Anything that would require violating the mission boundaries:** a second commit, an untrailed
  commit, a file outside `calc.py`/`test_calc.py`, a receipt re-run, etc.
