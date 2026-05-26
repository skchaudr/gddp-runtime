# GDDP Verification Module — Parallel Build Setup

A reference for building Tasks 1–5 on a single Pi using `git worktree` + `tmux`, two agents at a time.

---

## Environment

One venv, shared across every worktree of this project. All worktrees are branches of the same repo with the same dependency tree — there's nothing to keep in sync, and the disk cost of duplicating venvs is the only thing avoided here.

```bash
# use whatever venv you already have for this project
source ~/.venvs/gddp/bin/activate
```

Activate it once per tmux pane as you open it. If a later task adds a dependency (e.g. an LLM client in Task 4), `pip install` it once — every worktree sees it immediately because they all point at the same interpreter.

---

## Pre-work on main (one commit, before any branching)

These land on `main` so every branch inherits them. Skipping any of these forces live coordination between agents, which is what the worktree split is trying to avoid.

1. **Module skeleton:** create `scripts/runtime/verification/__init__.py`.
2. **`SemanticOutput` stub** in `scripts/runtime/verification/semantic_schema.py`. Just the class signature with the literal fields. Task 2's `decide()` imports it; Task 4 fills in the body later.
3. **Shape profile schema** at `gddp-config/schemas/v1/shape_profile.yaml`. Schema definition only, no profile content. Both Task 4 and Task 5 reference this.
4. **`graph_updater` decision resolved.** PR-proposal model vs direct Contents API write. Record the choice in a short ADR or comment near `return_router.py`. Task 3 needs it.

Commit, push, ready to branch.

---

## Wave 1 — Tasks 1 + 2 in parallel

Create the worktrees:

```bash
cd ~/code/myproject
git worktree add ../myproject-t1 -b feature/t1-structural
git worktree add ../myproject-t2 -b feature/t2-decision
```

tmux layout:

| Pane | Command |
|------|---------|
| Top-left | `cd ~/code/myproject-t1 && source ~/.venvs/gddp/bin/activate && claude` |
| Top-right | `cd ~/code/myproject-t2 && source ~/.venvs/gddp/bin/activate && claude` |
| Bottom (small) | scratch terminal for `git status`, `pytest`, `git diff`, etc. |

Scope each agent to its task spec. Both write net-new files under `scripts/runtime/verification/`, zero file overlap.

Merge when done:

```bash
cd ~/code/myproject
git checkout main
git pull
git merge feature/t1-structural
git merge feature/t2-decision    # different files, no conflicts
git worktree remove ../myproject-t1
git worktree remove ../myproject-t2
git branch -d feature/t1-structural feature/t2-decision
```

---

## Wave 2 — Task 3 standalone

Touches existing files (`return_router.py`, `init_db.py`, new `review_queue.py`) plus the Pi harness packet at `~/.pi/harness/packets/review-node.yaml`. Single branch, no parallelism:

```bash
git checkout -b feature/t3-conductor
```

The `graph_updater` decision from pre-work determines what `write_verdict` does. Implement, test, merge.

```bash
git checkout main && git merge feature/t3-conductor
```

---

## Wave 3 — Tasks 4 + 5 in parallel

Same shape as Wave 1. Task 4 writes new files in `scripts/runtime/verification/`. Task 5 writes new files in `gddp-config/profiles/` plus a one-line addition to `project.yaml`. Zero overlap because the shape profile schema is already on main from pre-work.

```bash
git worktree add ../myproject-t4 -b feature/t4-semantic
git worktree add ../myproject-t5 -b feature/t5-shape-profiles
```

Same tmux layout. Same merge dance:

```bash
git checkout main
git merge feature/t4-semantic
git merge feature/t5-shape-profiles
git worktree remove ../myproject-t4 ../myproject-t5
git branch -d feature/t4-semantic feature/t5-shape-profiles
```

---

## Cleanup

After all three waves:

```bash
git worktree list    # confirm only main remains
git worktree prune   # clean up any stragglers
```

---

## Quick reference

| Wave | Branches | Parallel? | Dependency |
|------|----------|-----------|------------|
| 1 | `t1-structural`, `t2-decision` | Yes | `SemanticOutput` stub on main |
| 2 | `t3-conductor` | No | `graph_updater` decision made |
| 3 | `t4-semantic`, `t5-shape-profiles` | Yes | `shape_profile.yaml` schema on main |

One Pi. One venv. Two tmux panes per wave. Merge sequentially into main.
