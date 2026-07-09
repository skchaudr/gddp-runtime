# Background

The background section covers the why behind GDDP Runtime, not the how. The system is built on a small set of architectural decisions and a doctrine about what graph truth means and who owns it. These pages explain where those ideas came from and why they resist simplification.

- [Design decisions](design-decisions.md) — The key architectural choices (two-repo split, receipt-based returns, two-lane evaluator, worst-of combination, subprocess isolation, executor-agnostic adapters, SQLite, cron heartbeat, evidence PRs) and the reasoning behind each one.
- [Doctrine](doctrine.md) — The intent-preservation and graph-integrity principles from `docs/Tests-can-fail-nodes-can-pass.md` and `docs/GDDP-becomes-small-and-real.md`. What counts as graph truth, what does not, and why the evaluator is deliberately kept out of the executor's framing.
