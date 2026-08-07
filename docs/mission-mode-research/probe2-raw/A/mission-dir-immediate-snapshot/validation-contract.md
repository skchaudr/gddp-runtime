# Validation Contract — PROBE-2A

Behavioral assertions that define "done". Black-box / behavior-based. Validators test against
this document, never against the implementation.

## Surfaces and tools

This mission has no UI, API, or TUI. `agent-browser` and `tuistory` do not apply. The only
validation tools are:

- `python3 -c "..."` — direct interrogation of `calc.py` (numeric probes, monkeypatch, AST)
- `python3 -m pytest -q` — the test suite
- `git` — commit chain inspection
- `jq` — receipt ledger inspection
- file reads

## Validator preamble

Prepend to every command block:

```sh
WT=/Users/sab-mini/probe2-gddp/repoA-wt-probe2a
RECEIPTS=/Users/sab-mini/probe2-gddp/receiptsA.jsonl
BASELINE=a96356a50f173d98731b9944e65ff593c81333f0
NODE_LIST() { printf '%s\n' n1-base n2-left n3-right n4-merge n5-chain n6-chain n7-chain n8-final; }
FN_LIST()   { printf '%s\n' inc double_after_inc square_after_inc sum_paths negate_merge absolute_chain label_chain final_summary; }
cd "$WT"
```

## ABSOLUTE PROHIBITION FOR VALIDATORS

**Never run `gddp-node-receipt`**, not even with a redirected `GDDP_RECEIPTS_PATH`. Never
commit, never modify `calc.py`/`test_calc.py`, never create fixtures or seed data. Validation
here is strictly read-only. A stray receipt or commit is unrecoverable and fails the mission.

## Ground-truth value table

Verified numerically. `sum_paths(x) = (x+1)(x+3)`.

| x | inc | double_after_inc | square_after_inc | sum_paths | negate_merge | absolute_chain |
|---:|---:|---:|---:|---:|---:|---:|
| -5 | -4 | -8 | 16 | 8 | -8 | 8 |
| -3 | -2 | -4 | 4 | 0 | 0 | 0 |
| **-2** | -1 | -2 | 1 | **-1** | **1** | **1** |
| -1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0 | 1 | 2 | 1 | 3 | -3 | 3 |
| 3 | 4 | 8 | 16 | 24 | -24 | 24 |
| 10 | 11 | 22 | 121 | 143 | -143 | 143 |

**Probe-selection hazards (do not use these as sole witnesses):**
- `x=1`: `double(1) == square(1) == 4`, so a `sum_paths` bug that doubles one sibling is invisible.
- `x=0`: `square_after_inc(0) == 1` collides with the buggy `x**2 + 1`.
- `x=-3` and `x=-1` are the roots (`sum_paths == 0`); a missing negation is invisible there.
- `x=-5` and `x=1` both give `sum_paths == 8`; they are not independent witnesses.

**The `x = -2` fact.** Over all integers, `x = -2` is the *only* input where `sum_paths(x) < 0`
(it equals `-1`). Therefore it is the **only integer input** that distinguishes a correct
`absolute_chain` from a body that just returns `sum_paths(x)`. It is mandatory in every
`absolute_chain` probe set.

---

## Area: Node Behavior

### VAL-NODE-001: `inc` returns x + 1
`inc(x)` returns exactly `-4, -1, 0, 1, 4, 11` for `x = -5, -2, -1, 0, 3, 10`.
Pass: all six equalities hold. Fail: any mismatch.
Tool: `python3 -c "import calc; print([calc.inc(x) for x in (-5,-2,-1,0,3,10)])"`
Evidence: terminal output, exit code

### VAL-NODE-002: `double_after_inc` returns 2*(x+1)
Returns exactly `-8, -4, -2, 0, 2, 8` for `x = -5, -3, -2, -1, 0, 3`.
`x=0 -> 2` is required: it rules out both `2*x` (gives 0) and `inc(2*x)` (gives 1).
Pass: all six. Fail: any mismatch.
Tool: `python3 -c`
Evidence: terminal output

### VAL-NODE-003: `square_after_inc` returns (x+1)**2
Returns exactly `16, 4, 1, 0, 1, 16` for `x = -5, -3, -2, -1, 0, 3`.
`x=3 -> 16` and `x=-5 -> 16` are required: they rule out `x**2 + 1` (which gives 10 and 26).
`x=-1 -> 0` rules out `x**2`.
Pass: all six. Fail: any mismatch.
Tool: `python3 -c`
Evidence: terminal output

### VAL-NODE-004: `sum_paths` sums both sibling paths
Returns exactly `8, 0, -1, 0, 3, 24` for `x = -5, -3, -2, -1, 0, 3`. Additionally, sweeping
`x` over `range(-50, 51)`, the set of inputs with `sum_paths(x) < 0` is exactly `{-2}`, and
`sum_paths(-3) == sum_paths(-1) == 0`.
`x=3 -> 24` is required: it rules out double-counting one sibling (16 or 32) and dropping a
sibling (8 or 16). `x=1` is deliberately excluded as a collision point.
The sweep is asserted explicitly because VAL-NODE-006 rests on it.
Pass: all six values plus the sweep results. Fail: any mismatch.
Tool: `python3 -c`
Evidence: terminal output showing the six values and the printed negative-set `[-2]`

### VAL-NODE-005: `negate_merge` negates the merged value
Returns exactly `-8, 0, 1, 0, -3, -24` for `x = -5, -3, -2, -1, 0, 3`. Additionally, for every
`x` in `range(-20, 21)`, `negate_merge(x) == -sum_paths(x)`.
`x=0 -> -3` and `x=3 -> -24` rule out returning `sum_paths` unchanged. `x=-2 -> 1` (positive) is
the sign-flip witness on the one negative input.
Pass: all six values plus 41/41 on the sweep. Fail: any mismatch.
Tool: `python3 -c`
Evidence: terminal output

### VAL-NODE-006: `absolute_chain` takes the absolute value of the negated merge
Returns exactly `8, 0, 1, 0, 3, 24, 143` for `x = -5, -3, -2, -1, 0, 3, 10`.
**`x = -2 -> 1` is mandatory and non-substitutable** — it is the only integer input separating a
correct implementation from one that returns `sum_paths(x)` (which gives `-1`).
`x=0 -> 3` (not `-3`) proves `abs` is applied at all.
Additionally, over `range(-50, 51)`: `absolute_chain(x) >= 0` for every `x`; there is at least
one `x` where `absolute_chain(x) != negate_merge(x)`; and the set where
`absolute_chain(x) != sum_paths(x)` is exactly `{-2}`.
Pass: all seven values plus all three sweep conditions. Fail: any mismatch.
Tool: `python3 -c`
Evidence: terminal output with the `x=-2` result displayed explicitly

### VAL-NODE-007: `label_chain` returns a deterministic string carrying the chain value
For `x` in `{-5, -2, 0, 3}`: `label_chain(x)` is a `str`, and `str(absolute_chain(x))` — i.e.
`"8"`, `"1"`, `"3"`, `"24"` — is a substring of it. `label_chain(-5)`, `label_chain(0)`, and
`label_chain(3)` are pairwise distinct (the label is not a constant).
Pass: all four containments and both inequalities. Fail: any miss, or a non-`str` return.
Tool: `python3 -c`
Evidence: the four returned strings printed verbatim

### VAL-NODE-008: `final_summary` returns a deterministic string composed from the label
For `x` in `{-5, -2, 0, 3}`: `final_summary(x)` is a `str` and contains `label_chain(x)` as a
substring. The four results are pairwise distinct (the four underlying values `8, 1, 3, 24` are
distinct, so the summaries must be too).
Pass: four containments and four distinct results. Fail: any miss or duplicate.
Tool: `python3 -c`
Evidence: the four returned strings printed verbatim

### VAL-NODE-009: `label_chain` output is pure and its format is pinned
Three conditions:
1. **Intra-process purity** — 100 successive calls with the same input return an identical
   string, for `x` in `{-2, 0, 3}`.
2. **Cross-process purity** — a one-liner printing `label_chain(-2)`, `label_chain(0)`,
   `label_chain(3)` produces byte-identical stdout under `PYTHONHASHSEED=0` vs
   `PYTHONHASHSEED=12345`, and under `TZ=UTC` vs `TZ=Asia/Tokyo`. This rules out `hash()`,
   `id()`, timestamps, and set/dict iteration order.
3. **Format pinned in-repo** — `test_calc.py` contains an assertion of the form
   `label_chain(<int literal>) == "<string literal>"`, with a quoted string literal on the
   right-hand side — not an f-string or a re-invocation of `absolute_chain`. Verify by AST:
   find a `Compare(Eq)` whose left operand is a `Call` to `label_chain` and whose right operand
   is an `ast.Constant` of type `str`.
Pass: all three. Fail: any variation across runs, or no pinning assertion found.
Tool: `python3 -c`, `env PYTHONHASHSEED=... python3 -c`, `diff`
Evidence: `sort -u` collapsing to one line; empty `diff`; the quoted source line

### VAL-NODE-010: `final_summary` output is pure and its format is pinned
Same three conditions as VAL-NODE-009, applied to `final_summary` for `x` in `{-2, 0, 3}`.
Pass: all three. Fail: any variation, or no pinning assertion found.
Tool: `python3 -c`, `env PYTHONHASHSEED=... python3 -c`, `diff`
Evidence: identical outputs across all four process variants; the quoted source line

---

## Area: Call Graph / Delegation

The architecture requires each node to be implemented *by calling its declared parent(s)*, never
by re-deriving arithmetic inline. Two techniques are used together:

- **Monkeypatch (primary)** — replace the parent in the `calc` module namespace with a stub
  returning a sentinel, then confirm the child's output changes accordingly. Restore in a
  `finally` block. This proves the parent's value genuinely flows into the child's result.
- **AST (complement)** — parse `calc.py`, walk each `FunctionDef`, collect `Call` nodes whose
  `func` is a `Name`, and compare the callee set. This catches extra/unauthorized edges, calls
  whose result is discarded, and the `abs` builtin requirement, which monkeypatching cannot
  cleanly cover.

Neither alone suffices. Require both.

### VAL-GRAPH-001: `inc` is a leaf
The AST callee-name set of `inc`'s body is empty — it calls nothing.
Pass: callee set == `set()`. Fail: any call present.
Tool: `python3 -c` with `ast.parse`
Evidence: printed callee set

### VAL-GRAPH-002: `double_after_inc` delegates to `inc`
With `calc.inc` replaced by `lambda x: 10`, `double_after_inc(0) == 20` and
`double_after_inc(999) == 20`. After restoring, `double_after_inc(0) == 2`.
AST callee set is exactly `{"inc"}`.
Pass: both stubbed results are 20, restore verified, set equality. Fail: any deviation —
notably an inline `2*x + 2` body, which returns 2 and 1998 under the stub.
Tool: `python3 -c` monkeypatch with try/finally + AST
Evidence: printed stubbed values, post-restore value, callee set

### VAL-GRAPH-003: `square_after_inc` delegates to `inc`
With `calc.inc = lambda x: 10`, `square_after_inc(0) == 100` and `square_after_inc(-7) == 100`.
After restoring, `square_after_inc(3) == 16`. AST callee set is exactly `{"inc"}`.
Pass: both stubbed results are 100, restore verified, set equality. Fail: any deviation —
notably an inline `(x+1)**2` body.
Tool: `python3 -c` monkeypatch + AST
Evidence: printed stubbed values, post-restore value, callee set

### VAL-GRAPH-004: `sum_paths` calls both siblings exactly once each
With `double_after_inc -> 1000` and `square_after_inc -> 7`, `sum_paths(0) == 1007` and
`sum_paths(-4) == 1007`. With only `double_after_inc -> 1000`, `sum_paths(3) == 1016`. With only
`square_after_inc -> 7`, `sum_paths(3) == 15`.
The decomposition `1007 = 1000 + 7` is unique among confusions: doubling one sibling gives 2000
or 14; dropping one gives 1000 or 7.
AST callee set is exactly `{"double_after_inc", "square_after_inc"}` — no `inc`, no inline
arithmetic.
Pass: all four probes plus set equality. Fail: any mismatch.
Tool: `python3 -c` monkeypatch + AST
Evidence: printed `1007, 1007, 1016, 15` and callee set

### VAL-GRAPH-005: `negate_merge` delegates to `sum_paths`
With `sum_paths -> 42`, `negate_merge(0) == -42`; with `sum_paths -> -42`, result is `42`; with
`sum_paths -> 0`, result is `0`. AST callee set is exactly `{"sum_paths"}`.
Pass: all three plus set equality. Fail: any mismatch.
Tool: `python3 -c` monkeypatch + AST
Evidence: printed `-42, 42, 0` and callee set

### VAL-GRAPH-006: `absolute_chain` delegates to `negate_merge` and uses built-in `abs` — CRITICAL
With `negate_merge -> -9`, `absolute_chain(0) == 9`; with `negate_merge -> 9`, result is `9`;
with `negate_merge -> 0`, result is `0`. The unpatched value at `x=0` is `3`, which must be
recorded to demonstrate the stub actually changed the output.
AST callee set is exactly `{"abs", "negate_merge"}`; `abs` resolves to the builtin (`"abs"` is
not shadowed in `vars(calc)`); the body contains no `ast.If` and no `ast.Compare` (no
hand-rolled sign branch).
Pass: all three stub probes, builtin identity, no branch nodes, set equality. Fail: any deviation.

**Why this assertion is critical.** A body written as `abs(sum_paths(x))` is numerically
identical to the correct implementation for *every possible input, integer or real* — because
`abs(-v) == abs(v)`. No black-box numeric probe can ever detect it, yet it deletes the
`n5-chain -> n6-chain` edge from the call graph. Under this assertion it returns `3, 3, 3` and
is caught. This is the one place in the graph where delegation checking is not a style gate but
the **only available correctness signal**.
Tool: `python3 -c` monkeypatch with try/finally + AST
Evidence: printed `9, 9, 0`, the unpatched `3`, the callee set, `abs shadowed: False`

### VAL-GRAPH-007: `label_chain` delegates to `absolute_chain`
With `absolute_chain -> 987654`, `"987654" in label_chain(0)`.
AST callee set contains `"absolute_chain"` and none of `negate_merge`, `sum_paths`,
`double_after_inc`, `square_after_inc`, `inc`, `abs`.
Pass: substring present and callee constraint satisfied. Fail: otherwise.
Tool: `python3 -c` monkeypatch + AST
Evidence: printed stubbed string containing `987654`; callee set

### VAL-GRAPH-008: `final_summary` delegates to `label_chain`
With `label_chain -> "ZQXJV"`, `"ZQXJV" in final_summary(0)`.
AST callee set contains `"label_chain"` and none of `absolute_chain`, `negate_merge`,
`sum_paths`, `double_after_inc`, `square_after_inc`, `inc`.
Pass: substring present and callee constraint satisfied. Fail: otherwise — in particular,
calling `absolute_chain` directly deletes the `n7 -> n8` edge.
Tool: `python3 -c` monkeypatch + AST
Evidence: printed stubbed string containing `ZQXJV`; callee set

### VAL-GRAPH-009: the complete call graph equals the dependency graph
A single AST pass over `calc.py` produces a callee map exactly equal to:

```
add:              {}
inc:              {}
double_after_inc: {inc}
square_after_inc: {inc}
sum_paths:        {double_after_inc, square_after_inc}
negate_merge:     {sum_paths}
absolute_chain:   {negate_merge, abs}
label_chain:      {absolute_chain}
final_summary:    {label_chain}
```

No extra functions defined in the module, no extra edges, no missing edges.
Pass: exact dict equality. Fail: any extra/missing key or edge.
Tool: `python3 -c` AST walk printing the full map
Evidence: printed callee map alongside the expected literal

---

## Area: Regression

### VAL-REG-001: the pre-existing `add` survives and the suite is green
`git show $BASELINE:calc.py` lines `def add(a, b):` and `return a + b` are byte-identical at
HEAD. `def test_add():` and `assert add(2, 3) == 5` are byte-identical at HEAD. `add` is still
imported in `test_calc.py`. `python3 -c "import calc; assert calc.add(2,3)==5 and calc.add(-1,1)==0"`
exits 0. `python3 -m pytest -q` exits 0 with zero failures and zero errors, and `test_add` is
among the collected tests.

**Required carve-out:** the import line `from calc import add` will legitimately grow to
`from calc import add, inc, ...`. That is **not** a regression. A naive "no removed lines in
`test_calc.py`" rule produces a false failure here. The rule is: `add` must still be imported,
and the `def add` body and `def test_add` body must be unchanged. The only permissible removal
is the original bare import line replaced by a superset import.
Pass: all conditions hold. Fail: any protected body line altered, or `add` no longer imported,
or the suite not green.
Tool: `git show`, `git diff`, `python3 -c`, `python3 -m pytest -q`, `python3 -m pytest -v --collect-only`
Evidence: diff output, pytest summary line

### VAL-REG-002: the chain is purely additive — no node rewrote an earlier node
The cumulative diff `$BASELINE..refs/heads/probe2a` on `calc.py` and `test_calc.py` contains
zero removed lines, except for the single permitted import-line replacement described in
VAL-REG-001.

This one check enforces: the baseline `add` untouched; no later node rewrote an earlier node's
function; no node changed an earlier node's pinned string literal; no "fix the previous node"
edit smuggled in. Additionally, the exact string literal pinned by `n7-chain` (VAL-NODE-009) is
still present verbatim in `test_calc.py` at HEAD.
Pass: removed-line count is 0 (or exactly the permitted import replacement), and the pinned
literal is intact. Fail: otherwise.
Tool: `git diff "$BASELINE" refs/heads/probe2a -- calc.py test_calc.py | grep -c '^-[^-]'`, `grep`
Evidence: the removal count and, on failure, the listed removals

---

## Area: Per-Node Commit & Receipt Protocol

Eight structurally identical assertions, one per node. Each verifies that node *K*'s own commit
and own receipt line conform to the protocol at the moment that node completed. `K` is the
1-based node index; `NODE` is the node id; `SHA` is that node's commit; `FN` is the function
name that node adds.

Every assertion in this area checks all of the following for its node:

1. **Exactly one exact trailer.** `git show -s --format=%B "$SHA" | grep -c "^GDDP-Node-Id: ${NODE}\$"`
   is exactly `1`. Anchored both ends, single ASCII space after the colon. Rejects `0` (untrailed),
   `2` (duplicate), and the whitespace variants `GDDP-Node-Id:n1-base`, `GDDP-Node-Id:  n1-base`,
   `  GDDP-Node-Id: n1-base`, `GDDP-Node-Id: n1-base `.
2. **No near-duplicate key.** The loose count
   `grep -ciE '^[[:space:]]*gddp[-_ ]?node[-_ ]?id[[:space:]]*:'` is also exactly `1`, proving the
   single occurrence is the canonical one.
3. **Git's own parser agrees.** `git show -s --format='%(trailers:key=GDDP-Node-Id,valueonly)' "$SHA"`
   yields exactly one non-empty line equal to `NODE`. This catches a trailer stranded above a
   later prose paragraph, which passes a raw grep but is not a real trailer.
4. **Clean message bytes.** No line in the message contains a CR or ends in space/tab.
5. **Real subject.** The subject line is non-empty and does not itself begin with `GDDP-Node-Id:`.
6. **Exactly two files changed.** `git diff-tree --no-commit-id --name-only -r "$SHA"` sorted is
   exactly `calc.py test_calc.py`.
7. **Exactly one new function, correctly named.** The added lines in `calc.py` contain exactly one
   `^+def ` line and its name is `FN`. This is what prevents two nodes being implemented in one
   commit.
8. **At least one new test.** The added lines in `test_calc.py` contain at least one `^+def test_`.
   Combined with (6) and (7), this makes both "two nodes in one commit" and "one node split
   across two commits" detectable.
9. **Linear.** The commit has exactly one parent; it is not a merge.
10. **Receipt line count.** After this node, `wc -l < "$RECEIPTS"` is exactly `K`. This is the only
    way to catch a double-append at the moment it happens.
11. **Receipt is canonical JSON.** Line `K` re-serializes byte-identically under
    `json.dumps(json.loads(line), sort_keys=True)`, and its key set is exactly
    `{base, git_branch, git_head, git_toplevel, node_id, result, timestamp_utc}`. The tool writes
    with `sort_keys=True`, so any hand-edit or foreign line is detected.
12. **Receipt fields correct.** Line `K` has `node_id == NODE`, `result == SHA`,
    `git_head == result` (proving the receipt was taken *after* the commit),
    `git_branch == "probe2a"`, `git_toplevel == "$WT"`, `base != result`, and all three SHA fields
    match `^[0-9a-f]{40}$` (full 40-char lowercase hex, not abbreviated).
13. **Receipt chains to its predecessor.** `base` equals the `result` of line `K-1`, or equals
    `$BASELINE` when `K == 1`. Additionally `git rev-parse "${SHA}^"` equals `base` — the receipt
    chains the same way git does.
14. **No history rewriting yet.** `git reflog show probe2a --format='%gs'` has exactly `K+1`
    entries: `K` entries of the form `commit: ...` plus the final
    `branch: Created from HEAD`. Zero entries matching
    `amend|rebase|reset|cherry|revert|checkout: moving`. Author/committer date skew under 300s.
15. **Boundaries intact.** `refs/heads/main` still at `$BASELINE`; no tags; no remotes; working
    tree clean apart from untracked `__pycache__/`.

Tool: `git`, `jq`, `python3`
Evidence for each: the per-commit trailer table, the added-def and added-test lists, the receipt
line printed verbatim, the reflog listing

### VAL-PROTO-001: `n1-base` commit and receipt conform
K=1, NODE=`n1-base`, FN=`inc`. `base` must equal `$BASELINE`.

### VAL-PROTO-002: `n2-left` commit and receipt conform
K=2, NODE=`n2-left`, FN=`double_after_inc`.

### VAL-PROTO-003: `n3-right` commit and receipt conform
K=3, NODE=`n3-right`, FN=`square_after_inc`.

### VAL-PROTO-004: `n4-merge` commit and receipt conform
K=4, NODE=`n4-merge`, FN=`sum_paths`.

### VAL-PROTO-005: `n5-chain` commit and receipt conform
K=5, NODE=`n5-chain`, FN=`negate_merge`.

### VAL-PROTO-006: `n6-chain` commit and receipt conform
K=6, NODE=`n6-chain`, FN=`absolute_chain`.

### VAL-PROTO-007: `n7-chain` commit and receipt conform
K=7, NODE=`n7-chain`, FN=`label_chain`.

### VAL-PROTO-008: `n8-final` commit and receipt conform
K=8, NODE=`n8-final`, FN=`final_summary`.

---

## Cross-Area Flows

Terminal assertions — only fully evaluable once all eight nodes are complete.

### VAL-CHAIN-001: exactly eight linear commits above the baseline
`git rev-list --count "${BASELINE}..refs/heads/probe2a"` is exactly `8`.
`git rev-list --parents "${BASELINE}..refs/heads/probe2a"` has 2 fields on every line (no merges,
no roots); `git rev-list --count --merges` is `0`.
`git rev-parse "refs/heads/probe2a~8"` equals `$BASELINE`.
`git merge-base --is-ancestor "$BASELINE" refs/heads/probe2a` exits 0.
HEAD is attached to `refs/heads/probe2a` and equals the branch tip.
`refs/heads/main` is still at `$BASELINE`.

**Why `main` matters:** the worktree shares its object store and refs with
`/Users/sab-mini/probe2-gddp/repoA`. A commit made from the wrong checkout would advance `main`
while still producing a valid-looking object.
Pass: all conditions. Fail: any deviation.
Tool: `git`
Evidence: all command outputs

### VAL-CHAIN-002: trailer values, in commit order, equal the dictated sequence
Extracting the `GDDP-Node-Id` value from each commit in `--reverse` (oldest-first) order yields
exactly: `n1-base n2-left n3-right n4-merge n5-chain n6-chain n7-chain n8-final`.
This catches swapped diamond siblings (`n2-left` / `n3-right`), any reordering, and any
substitution.
Pass: `diff` against `NODE_LIST` is empty. Fail: otherwise.
Tool: `git log`, `diff`
Evidence: the extracted 8-line list and empty diff

### VAL-CHAIN-003: the ledger has exactly eight well-formed lines in dictated order
`receiptsA.jsonl` exists at the mandated path. `wc -l` is exactly `8`. The final byte is `\n`.
No blank or whitespace-only lines. Every line parses as JSON with exactly the seven tool-written
keys. Every line re-serializes byte-identically under `json.dumps(..., sort_keys=True)`.
`jq -r '.node_id'` in file order equals `NODE_LIST` exactly, with no duplicates and no unknown
ids.
A 9th line means a receipt was re-run; a 7th means one was skipped.
Pass: all conditions. Fail: any deviation.
Tool: `wc`, `od`, `jq`, `python3`, `diff`
Evidence: line count, canonical-check output `NONCANONICAL: []`, empty diff

### VAL-CHAIN-004: the receipt chain is contiguous
Line 1's `base` equals `$BASELINE`. For every `k > 1`, `base(k) == result(k-1)`. Line 8's
`result` equals `git rev-parse refs/heads/probe2a`.
Contiguity is what makes the eight receipts a *chain* rather than eight unrelated records.
Pass: no break detected at any index. Fail: any break.
Tool: `jq`, `awk`
Evidence: exit 0 with no `BREAK:` lines; the base/result table

### VAL-CHAIN-005: git and the ledger agree
`jq -r '.result'` in file order equals `git rev-list --reverse "${BASELINE}..refs/heads/probe2a"`
in order.
Independently of ordering: for each receipt, searching the range for commits carrying that
node's exact trailer returns exactly one SHA and it equals that receipt's `result`.
For every receipt, `git rev-parse "<result>^"` equals `base`.
Every receipt has `git_head == result`, `git_branch == "probe2a"`, `git_toplevel == "$WT"`.
Every distinct SHA appearing in `base`/`result`/`git_head` is an existing commit object **and**
an ancestor-or-self of `refs/heads/probe2a`.

**Why reachability matters:** because the object store is shared with repoA, a SHA can exist
without being part of this chain — dangling after an amend, or created on `main` from the
sibling checkout. Existence is not enough; reachability is required.
Pass: all conditions. Fail: any mismatch, `MISSING_OBJECT`, or `UNREACHABLE`.
Tool: `git`, `jq`, `diff`
Evidence: empty diffs, the per-node lookup table, the parent/base table

### VAL-CHAIN-006: no history was rewritten
`git reflog show probe2a --format='%gs'` has exactly `9` entries: 8 of the form `commit: ...`
followed by `branch: Created from HEAD`. Zero entries matching
`amend|rebase|reset|cherry|revert|checkout: moving`. The oldest reflog entry's old-value
abbreviates to `a96356a`.
No `rebase-merge`, `rebase-apply`, `MERGE_HEAD`, `CHERRY_PICK_HEAD`, or `ORIG_HEAD` in the git dir.
Author/committer date skew is under 300 seconds on every commit (an amend, rebase, or
cherry-pick leaves committer date far ahead of author date).
Committer dates are non-decreasing along the chain.
No commit message contains `revert` / `this reverts commit`, and no two commits share a tree
(a commit-then-revert pair produces a duplicate tree).
`git fsck --no-reflogs --unreachable` reports no unreachable **commit** objects.

**Why this assertion exists:** after an amend, every SHA-based check in VAL-CHAIN-001 through
005 passes again, because the chain is once more internally consistent. The reflog is the
primary amend detector; date skew and dangling-object checks corroborate it from the object
side and survive reflog expiry.
Pass: all conditions. Fail: any deviation.
Tool: `git reflog`, `git log`, `git fsck`, `ls`
Evidence: the full reflog listing, the `%at %ct` table, fsck output

### VAL-CHAIN-007: receipts were written live, interleaved with commits — not deferred or batched
For `k = 1..8`: `committer_date(commit_k) <= timestamp_utc(receipt_k)`.
For `k = 1..7`: `timestamp_utc(receipt_k) <= committer_date(commit_{k+1})`.

That is: receipt *k* was written **after** commit *k* and **before** commit *k+1*.

**Why this is the highest-value assertion in the contract.** The protocol forbids deferring or
batching receipts. A worker could complete all eight commits and then run all eight receipts at
the end with correct `--base`/`--result` pairs — and every other assertion in this document
would pass. Temporal interleaving is the only invariant that cannot be satisfied after the fact.
If all eight receipt timestamps cluster after commit 8, this fails loudly.

Timestamps must be parsed with `datetime.fromisoformat`, **not** compared lexicographically:
`datetime.isoformat()` omits the microsecond field entirely when it is exactly zero, so string
comparison is unreliable.
Pass: `VIOLATIONS: []`. Fail: any receipt preceding its own commit or following the next commit.
Tool: `python3` with `git show -s --format=%cI` and the ledger
Evidence: the interleaved commit/receipt timeline table

### VAL-CHAIN-008: scope was contained
The cumulative diff `$BASELINE..refs/heads/probe2a` touches exactly `calc.py` and `test_calc.py`.
`git ls-tree -r --name-only refs/heads/probe2a` is exactly those two files — no README, no docs,
no `.gitignore`, no committed `__pycache__`.
No tags. No remotes and no `refs/remotes`. The complete ref inventory is exactly
`refs/heads/main` and `refs/heads/probe2a` — no stash, no notes, no `refs/original/`, no bisect
refs, no extra branches.
Exactly two registered worktrees, at the expected paths and branches.
Working tree clean apart from untracked `__pycache__/`.
Sibling state untouched: repoA is on `main` at `$BASELINE` and clean; repoB is on `main` at
`$BASELINE` and clean; `baseA.sha` and `baseB.sha` both still hash (sha256) to
`ef00a9b45299ba60205c1795ff77b1ecbab57fe9ae0f56fa19926b2b7e2e4091`.
`find /Users/sab-mini/probe2-gddp -name '*.jsonl' -not -path '*/.git/*'` prints exactly
`/Users/sab-mini/probe2-gddp/receiptsA.jsonl` — no stray ledger written elsewhere.
Pass: all conditions. Fail: any deviation.
Tool: `git`, `find`, `shasum`
Evidence: all command outputs

---

## Known residual risk

Nothing in a receipt record captures `GDDP_RECEIPTS_PATH`. A receipt written to a different file
and later concatenated into `receiptsA.jsonl` is not directly detectable. VAL-CHAIN-003
(canonical serialization), VAL-CHAIN-007 (interleaving), and the stray-ledger check in
VAL-CHAIN-008 are the best available triangulation. Documented, accepted.
