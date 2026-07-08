# GDDP Verification Module — Parallel Build Setup

A reference for building Tasks 1–5 on a single Pi using `git worktree` + `tmux`, two agents at a time.

---

## Core model

A branch is a separate line of work.

A worktree is a separate folder attached to a branch.

One repo can have many worktrees. Each agent gets its own folder, its own branch, and its own clean working state. `main` stays the integration rail.

Example layout:

```text
~/code/myproject          main / integration rail
~/code/myproject-t1       feature/t1-structural
~/code/myproject-t2       feature/t2-decision
~/code/myproject-t4       feature/t4-semantic
~/code/myproject-t5       feature/t5-shape-profiles
```

---

## Environment

One venv, shared across every worktree of this project. All worktrees are branches of the same repo with the same dependency tree. There is nothing to keep in sync, and the disk cost of duplicating venvs is avoided.

```bash
# use whatever venv you already have for this project
source ~/.venvs/gddp/bin/activate
```

Activate it once per tmux pane as you open it.

If a later task adds a dependency, such as an LLM client in Task 4, install it once into the shared venv **and record it in the repo dependency file** (`requirements.txt`, `pyproject.toml`, or whichever dependency surface this project uses). The venv makes the work locally runnable; the dependency file makes the repo reproducible.

---

## Pre-work on main

One commit before any branching.

These land on `main` so every branch inherits them. Skipping any of these forces live coordination between agents, which is what the worktree split is trying to avoid.

1. **Module skeleton:** create `scripts/runtime/verification/__init__.py`.
   - Keep it empty.
   - Treat it as frozen for Tasks 1, 2, and 4 unless a later task explicitly needs exports.
2. **`SemanticOutput` stub** in `scripts/runtime/verification/semantic_schema.py`.
   - Just the class signature with the literal fields.
   - Task 2's `decide()` imports it.
   - Task 4 fills in the body later.
3. **Shape profile schema** at `gddp-config/schemas/v1/shape_profile.yaml`.
   - Schema definition only, no profile content.
   - Both Task 4 and Task 5 reference this.
4. **`graph_updater` decision resolved.**
   - PR-proposal model vs direct Contents API write.
   - Record the choice in a short ADR or comment near `return_router.py`.
   - Task 3 needs this decision before conductor wiring.

My recommended decision: use the **PR-proposal model**. Runtime should propose graph/source-of-truth mutations, not silently mutate them. Direct writes are faster, but the PR-proposal model better preserves reviewability and graph integrity.

Commit and push:

```bash
cd ~/code/myproject
git status
git checkout main
git pull --ff-only

# make pre-work edits
git add scripts/runtime/verification/__init__.py \
        scripts/runtime/verification/semantic_schema.py \
        gddp-config/schemas/v1/shape_profile.yaml

git commit -m "verification: add shared scaffolding for parallel build"
git push
```

Ready to branch.

---

## Per-agent stop condition

Each agent stops when:

```text
- Task files are implemented.
- Task-local tests pass.
- No out-of-scope files changed.
- New dependencies, if any, are recorded in repo dependency files.
- git diff is reviewed.
- Branch is committed.
- Final summary names files changed, tests run, and unresolved questions.
```

This is the termination contract. It keeps each agent from drifting into the next task.

---

## Wave 1 — Tasks 1 + 2 in parallel

Create the worktrees:

```bash
cd ~/code/myproject
git checkout main
git pull --ff-only

git worktree add ../myproject-t1 -b feature/t1-structural main
git worktree add ../myproject-t2 -b feature/t2-decision main
```

tmux layout:

| Pane | Command |
|------|---------|
| Top-left | `cd ~/code/myproject-t1 && source ~/.venvs/gddp/bin/activate && claude` |
| Top-right | `cd ~/code/myproject-t2 && source ~/.venvs/gddp/bin/activate && claude` |
| Bottom | scratch terminal for `git status`, `pytest`, `git diff`, etc. |

Scope each agent to its task spec.

### Task 1 packet — Structural Validator

```text
Implement Task 1 only: Structural Validator.

Create or modify only:
- scripts/runtime/verification/invariant_schema.py
- scripts/runtime/verification/structural.py
- scripts/runtime/verification/test_structural.py

Do not modify:
- scripts/runtime/verification/__init__.py
- decision_engine.py
- semantic.py
- return_router.py
- init_db.py
- Pi harness packets
- shape profiles

Acceptance:
- Pydantic models exist exactly as specified.
- Five check functions return InvariantResult.
- run_structural_validator returns StructuralOutput.
- Tests cover valid graph, cyclic DAG, missing artifact, out-of-scope file, and acceptance weakening.
- Relevant tests pass.
- Branch is committed.
```

### Task 2 packet — Decision Loop rules engine

```text
Implement Task 2 only: Decision Loop rules engine.

Create or modify only:
- scripts/runtime/verification/verdict_schema.py
- scripts/runtime/verification/decision_engine.py
- scripts/runtime/verification/test_decision_engine.py

Do not modify:
- scripts/runtime/verification/__init__.py
- structural.py
- semantic.py
- return_router.py
- init_db.py
- Pi harness packets
- shape profiles

Acceptance:
- DecisionOutput Pydantic model exists exactly as specified.
- decide(structural, semantic=None) is a pure function.
- The 6-row decision matrix is represented as a lookup table, not nested if chains.
- Tests include one test per matrix row.
- No mocking needed.
- Relevant tests pass.
- Branch is committed.
```

Merge when both are done:

```bash
cd ~/code/myproject
git checkout main
git pull --ff-only

git merge --no-ff feature/t1-structural
pytest scripts/runtime/verification

git merge --no-ff feature/t2-decision
pytest scripts/runtime/verification

git worktree remove ../myproject-t1
git worktree remove ../myproject-t2
git branch -d feature/t1-structural feature/t2-decision
```

Use `--no-ff` because these are meaningful architecture units. The merge commits preserve the build history.

---

## Wave 2 — Task 3 standalone

Task 3 touches existing files and the Pi harness surface, so it gets a single branch and no parallelism.

Expected surfaces:

```text
scripts/runtime/return_router.py
scripts/runtime/init_db.py
scripts/runtime/review_queue.py
~/.pi/harness/packets/review-node.yaml
```

Create the branch or worktree:

```bash
cd ~/code/myproject
git checkout main
git pull --ff-only

git checkout -b feature/t3-conductor
```

Or, if you want physical isolation:

```bash
cd ~/code/myproject
git checkout main
git pull --ff-only

git worktree add ../myproject-t3 -b feature/t3-conductor main
cd ../myproject-t3
```

The `graph_updater` decision from pre-work determines what `write_verdict` does.

Recommended conductor path:

```text
return_router
→ review_queue
→ review-node packet
→ structural validator
→ optional semantic evaluator
→ decision engine
→ verdict artifact
→ graph_updater creates PR-proposal / reviewable event
```

Task 3 should not silently mutate the source-of-truth graph.

Merge when done:

```bash
cd ~/code/myproject
git checkout main
git pull --ff-only

git merge --no-ff feature/t3-conductor
pytest scripts/runtime/verification

# if a worktree was used:
git worktree remove ../myproject-t3

git branch -d feature/t3-conductor
```

---

## Wave 3 — Tasks 4 + 5 in parallel

Same shape as Wave 1.

Task 4 writes new verification files.
Task 5 writes shape profile files plus a one-line project config addition.

This split is safe because `shape_profile.yaml` already exists on `main` from pre-work.

Create worktrees:

```bash
cd ~/code/myproject
git checkout main
git pull --ff-only

git worktree add ../myproject-t4 -b feature/t4-semantic main
git worktree add ../myproject-t5 -b feature/t5-shape-profiles main
```

### Shared shape profile interface

Task 4 and Task 5 both assume this schema shape:

```yaml
profile_id: cli-tool
description: CLI tool shape profile
expected_node_chain:
  - spec
  - parser
  - validator
  - executor
  - tests
invariant_rules:
  - Graph legality must be preserved
  - Acceptance criteria must not weaken
anti_patterns:
  - Runtime silently mutates source graph
  - Acceptance criteria removed without replacement
```

### Task 4 packet — Semantic Evaluator

```text
Implement Task 4 only: Semantic Evaluator.

Create or modify only:
- scripts/runtime/verification/semantic_schema.py
- scripts/runtime/verification/evaluator_prompt.py
- scripts/runtime/verification/semantic.py
- scripts/runtime/verification/test_semantic.py

Do not modify:
- scripts/runtime/verification/__init__.py
- structural.py
- decision_engine.py
- return_router.py
- init_db.py
- gddp-config/profiles/*
- project.yaml

Acceptance:
- CriterionVerdict and SemanticOutput schemas validate the expected literal fields.
- evaluator_prompt.py renders a prompt from node_spec, pr_diff, and shape_profile.
- semantic.py calls an LLM runner abstraction, extracts JSON, validates SemanticOutput, and returns it or raises.
- Tests cover happy-path extraction and schema rejection.
- Any new dependency is recorded in the repo dependency file.
- Relevant tests pass.
- Branch is committed.
```

### Task 5 packet — Shape Profiles

```text
Implement Task 5 only: Shape Profiles.

Create or modify only:
- gddp-config/profiles/cli-tool.yaml
- gddp-config/profiles/runtime-orchestrator.yaml
- gddp-config/profiles/web-app.yaml
- gddp-config/profiles/automation.yaml
- project.yaml

Do not modify:
- scripts/runtime/verification/*
- return_router.py
- init_db.py
- Pi harness packets

Acceptance:
- Four profile YAML files exist and follow gddp-config/schemas/v1/shape_profile.yaml.
- project.yaml gets one optional shape_profile field.
- Default behavior remains generic when shape_profile is absent.
- Relevant validation/tests pass.
- Branch is committed.
```

Merge when done:

```bash
cd ~/code/myproject
git checkout main
git pull --ff-only

git merge --no-ff feature/t4-semantic
pytest scripts/runtime/verification

git merge --no-ff feature/t5-shape-profiles
pytest scripts/runtime/verification

git worktree remove ../myproject-t4
git worktree remove ../myproject-t5
git branch -d feature/t4-semantic feature/t5-shape-profiles
```

---

## Cleanup

After all three waves:

```bash
git worktree list    # confirm only main remains
git worktree prune   # clean up any stragglers
git status
pytest
```

---

## Quick reference

| Wave | Branches | Parallel? | Dependency |
|------|----------|-----------|------------|
| 1 | `feature/t1-structural`, `feature/t2-decision` | Yes | `SemanticOutput` stub on main |
| 2 | `feature/t3-conductor` | No | `graph_updater` decision made |
| 3 | `feature/t4-semantic`, `feature/t5-shape-profiles` | Yes | `shape_profile.yaml` schema on main |

One Pi. One venv. Two tmux panes per parallel wave. Merge sequentially into main. Test after each merge.
