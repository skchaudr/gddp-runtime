# Architecture — PROBE-2A

Authoritative design document for the mission. Workers receive this alongside their feature
and the validation contract.

## 1. What this mission is

An externally-dictated **GDDP projection**. The external GDDP control plane owns decomposition
and node identity. This mission does not design a decomposition — it projects a fixed graph of
eight nodes into eight worker sessions with zero drift.

The deliverable is not really "a calculator". The deliverable is **two append-only chains that
stay in lockstep**:

1. A **git chain** of exactly eight linear commits above the baseline, each carrying exactly one
   `GDDP-Node-Id` trailer.
2. A **receipt chain** of exactly eight JSON lines in `receiptsA.jsonl`, contiguous by SHA.

`calc.py` is the vehicle that produces those chains. Treat the chains as the product.

## 2. Dependency graph (persisted verbatim)

```text
n1-base -> n2-left
n1-base -> n3-right
n2-left + n3-right -> n4-merge
n4-merge -> n5-chain -> n6-chain -> n7-chain -> n8-final
```

Shape: a **diamond** (`n1-base` fans out to `n2-left` / `n3-right`, which rejoin at `n4-merge`)
followed by a **linear tail** (`n4-merge` → `n5-chain` → `n6-chain` → `n7-chain` → `n8-final`).

`n2-left` and `n3-right` are the diamond siblings. The graph does not order them relative to
each other, but **the features array and execution order are pinned to the dictated sequence
anyway**. Do not exchange them. Do not reorder anything.

## 3. Code shape

`calc.py` is a flat module of small pure functions. `test_calc.py` is a flat module of plain
`test_*` functions. There are no classes, no packages, no config, no dependencies beyond the
Python standard library and pytest.

**The invariant that makes the graph structurally visible:** every node after `n1-base` is
implemented *by calling its declared parent function(s)* — never by re-deriving the arithmetic
inline. The call graph of `calc.py` must literally be the GDDP dependency graph.

```
add        (pre-existing baseline, untouched)

inc                 <- n1-base
double_after_inc    <- n2-left     calls inc
square_after_inc    <- n3-right    calls inc
sum_paths           <- n4-merge    calls double_after_inc AND square_after_inc
negate_merge        <- n5-chain    calls sum_paths
absolute_chain      <- n6-chain    calls negate_merge, and abs
label_chain         <- n7-chain    calls absolute_chain
final_summary       <- n8-final    calls label_chain
```

Concretely, `n3-right` must be `return inc(x) ** 2`. Writing `return (x + 1) ** 2` produces the
same numbers but **breaks the architecture**, because the edge `n1-base -> n3-right` disappears
from the call graph. The same rule applies to every node.

### Node reference

| Node | Function | Required implementation | Notes |
|------|----------|------------------------|-------|
| `n1-base` | `inc(x)` | `x + 1` | The only node with no parent call |
| `n2-left` | `double_after_inc(x)` | `2 * inc(x)` | |
| `n3-right` | `square_after_inc(x)` | `inc(x) ** 2` | |
| `n4-merge` | `sum_paths(x)` | `double_after_inc(x) + square_after_inc(x)` | Must call **both** siblings |
| `n5-chain` | `negate_merge(x)` | `-sum_paths(x)` | |
| `n6-chain` | `absolute_chain(x)` | `abs(negate_merge(x))` | Must use built-in `abs` |
| `n7-chain` | `label_chain(x)` | deterministic string built from `absolute_chain(x)` | Pin exact format in the test |
| `n8-final` | `final_summary(x)` | deterministic string built from `label_chain(x)` | Pin exact format in the test |

**Determinism (`n7-chain`, `n8-final`).** The returned strings must be pure functions of the
input — no timestamps, no randomness, no environment lookups, no dict/set iteration order.
Whatever format the worker chooses, its test asserts the exact expected string for at least one
concrete input, which pins the format permanently. Later nodes must not change an earlier node's
format.

## 4. The per-node protocol

This is the core mechanism of the mission. It keeps the git chain and the receipt chain in
lockstep. It is enforced redundantly in the worker skill, in `AGENTS.md`, and in every feature's
`expectedBehavior` — because a single deviation corrupts the whole projection irrecoverably.

For each node, in this exact order:

1. Confirm the worktree is clean and capture `BASE=$(git rev-parse HEAD)`.
2. Write the failing test in `test_calc.py` (red).
3. Implement the function in `calc.py`, calling the declared parent(s) (green).
4. `python3 -m pytest -q` — all tests must pass.
5. Create **exactly one** commit containing both file changes, whose message carries the exact
   trailer line `GDDP-Node-Id: <feature-id>`.
6. Capture `RESULT=$(git rev-parse HEAD)`.
7. From the worktree root, run exactly:
   `gddp-node-receipt --node-id <feature-id> --base "$BASE" --result "$RESULT"`
8. Confirm the command exited 0 and appended exactly one line. Only now is the node complete.

### Why the ordering is rigid

`gddp-node-receipt` (source inspected) appends one JSON line to the file named by
`GDDP_RECEIPTS_PATH`, and hard-fails if that variable is unset. Alongside the `--base` /
`--result` / `--node-id` you pass, it records **live** `git_head`, `git_branch`, and
`git_toplevel` read from the current working directory. Two hard consequences:

- **Receipt after commit, never before.** Otherwise the recorded `git_head` will not equal
  `result`, and the receipt is self-inconsistent.
- **Receipt from the worktree root** (`/Users/sab-mini/probe2-gddp/repoA-wt-probe2a`).
  Otherwise `git_toplevel` points somewhere else and the record is wrong.

### Chain invariants

- Node 1's `BASE` is the mission baseline `a96356a50f173d98731b9944e65ff593c81333f0`.
- For every subsequent node *k*: `BASE(k) == RESULT(k-1)`. Contiguity is what makes the eight
  receipts a *chain* rather than eight unrelated records.
- Each node's `RESULT` is the SHA of that node's single trailer-bearing commit.
- Exactly one receipt line per node, in the dictated order. A successful node's receipt is
  **never** re-run.

## 5. Boundaries and prohibitions

**Only two files may ever be modified:** `calc.py` and `test_calc.py`.

Never, under any circumstances:

- Combine two nodes into one commit, or split one node across two commits.
- Create an untrailed commit of any kind — no setup, scaffolding, integration, cleanup,
  documentation, or "fix the previous node" commits.
- Call a receipt before its commit exists.
- Call a receipt more than once for a node that already succeeded.
- Defer or batch receipts to the end.
- Edit, rewrite, reorder, or hand-craft lines in `receiptsA.jsonl`. It is append-only and
  written *only* by `gddp-node-receipt`.
- Modify the pre-existing `add` function or its baseline test.
- Touch README or any documentation file. **This mission has no README step**, by explicit
  instruction — the usual end-of-mission README gate is waived here.
- `git push`, create remotes, create tags, amend, rebase, reset, or otherwise rewrite history.
- Touch the sibling checkout `/Users/sab-mini/probe2-gddp/repoA` (on `main`),
  `/Users/sab-mini/probe2-gddp/repoB`, `baseA.sha`, or `baseB.sha`.

## 6. Failure posture

The chains are append-only and cannot be safely repaired in place. A corrective commit would
itself violate the eight-commit invariant, and a duplicate receipt would corrupt the ledger.

Therefore: **a worker that cannot complete its node cleanly must stop and return to the
orchestrator, leaving the repo clean.** It must not improvise a fix, not commit partial work,
and not attempt to undo a prior node. Escalation is always cheaper than a corrupted projection.

If a worker discovers that a *previous* node was committed incorrectly, it must not fix it. It
reports the discrepancy and returns.

## 7. Definition of done

- Exactly eight commits above `a96356a`, linear, in the dictated order, each with exactly one
  correct `GDDP-Node-Id` trailer.
- Exactly eight lines in `receiptsA.jsonl`, node ids in the dictated order, `base`/`result`
  contiguous, each `result` equal to the corresponding commit SHA.
- `python3 -m pytest -q` fully green.
- No extra commits, no extra receipts, no modified files outside `calc.py` / `test_calc.py`.
