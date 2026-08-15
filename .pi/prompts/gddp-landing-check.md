---
description: Verify actual git landing and commit ancestry for a finished GDDP attempt
subagent: scout
context: fresh
---

Inspect attempt result for node "$1" in repo "$2" (target branch: $3).
1. Read result SHA from `jobs.status` or event log for node $1.
2. Run `git -C $2 status -sb` and check working tree state.
3. Test ancestry: `git -C $2 merge-base --is-ancestor <result-sha> $3`.
4. Verify physical files modified in `<result-sha>` against claimed receipt artifacts.
5. Report landing verdict: `MATCH` (landed on tip), `DIVERGED` (on wrong branch), or `DIRTY`.
