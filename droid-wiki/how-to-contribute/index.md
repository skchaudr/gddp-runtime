# How to contribute

Contribution guidance for `gddp-runtime`. The project is mostly solo-authored by Saboor, with agents and occasional external reviewers touching the machinery. The emphasis is on durable handoffs, small commits, and never accidentally advancing graph truth from inside this repo.

## Pages

| Page | What it covers |
| --- | --- |
| [Development workflow](development-workflow.md) | Branching, small commits, handoffs, PR/merge expectations, definition of done |
| [Testing](testing.md) | Pytest layout, focused mission tests, fixture patterns, DB isolation |
| [Debugging](debugging.md) | Common failures, log locations, spool lifecycle, HMAC, KillMode gotchas |
| [Tooling](tooling.md) | `init_db`, `replay`, `rollback`, deploy scripts, `gddp` CLI, smoke/arm/disarm |
| [Patterns and conventions](patterns-and-conventions.md) | Hard boundaries, anti-patterns, evidence over ceremony, naming |

## Who contributes

- **Saboor** — operator, graph author, reviewer; sole authority on graph truth in `gddp-config`.
- **Agents** (Droid, Jules, etc.) — change runtime machinery under Saboor's direction; must follow AGENTS.md session contracts and co-author commits with `<agent> + <model>`.
- **Reviewers** (Sol, etc.) — audit diffs for safety, correctness, and assumption creep; findings surface as review comments, not direct commits.

## Start of session (every agent)

1. Run `git status --short --branch` before editing. Classify existing state if dirty.
2. Do not overwrite inherited changes until you know whether they are user work, another agent's work, or generated noise.
3. Verify branch and upstream; run `git fetch --prune` before merge/rebase decisions.
4. On any armed control plane (`sab-mini`, `pi-big`, etc.), run `git pull --ff-only` before anything else. Repo files on production change only via git.

## End of session (definition of done)

1. Run relevant validation (tests, smoke) and record results.
2. Run `git status --short --branch`. Target: clean, synced with upstream. Anything remaining must be called out with a path and reason.
3. Commit all intended changes. No staged/unstaged/untracked task artifacts for the next session to interpret.
4. Push the working branch. If the task lands on `main`, merge to `main`, push `main`, and verify local `main` equals `origin/main`.
5. Leave a handoff in `.handoffs/` with the next number, covering branch, commit, pushed status, validation, changed surfaces, and residual risk.

## Cross-references

- [Overview — getting started](../overview/getting-started.md) — install, DB init, first smoke
- [Overview — architecture](../overview/architecture.md) — component map and data flows
- [Deployment](../deployment/index.md) — topology and mini-heartbeat kit
- [Doctrine](../background/doctrine.md) — invariants and the four kinds of truth
