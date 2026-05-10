# 001 — Repo Hygeine and Sanity Checking README  

Date: 2026-05-09 → 2026-05-10
Branch: `docs/opclaw-root-cleanup` (currently checked out; PR #25 open). Two other branches (`docs/portfolio-readme-public`, `docs/graph-state-note`) were merged and deleted during the session.

## Empirical Reality (AGENT ONLY)
Scope touched:
- `gddp-runtime/README.md` — full portfolio rewrite (180 insertions, 56 deletions) from the working-tree draft that was sitting uncommitted on `main`. Neutralized 9 internal-nomenclature references ("Big Pi"/"Small Pi"), dropped unverified "running since 2026-01 / for three months" duration claim, corrected `gddp-runtime` graph count from `2/4` (unmerged-feat-branch state) to `1/1 + pending OpenClaw on feat/openclaw-nodes`. Later: dropped `OPCLAW_ROOT` row from env var table (PR #25).
- `gddp-config/README.md` — added "Current Graph State" table (`vault-doctor` 7/7, `gddp-runtime` 1/1) per the polish item flagged in `HANDOFF-PI-README.md`.
- Read-only scope (truth check): `scripts/runtime/`, `scripts/adapters/`, `scripts/intake_server.py`, `scripts/init_db.py`, `scripts/dry_run.py`, `scripts/rollback.py`, `scripts/heartbeat.py`, `deploy/`, `docs/`, `gddp-config/schemas/v1/`, `gddp-config/graphs/`.

Current state:
- `gddp-runtime` main: `9100386 docs: rewrite README as portfolio-facing` (merged from PR #24).
- `gddp-config` main: `08456b2 docs: add current graph state to README` (merged from PR #7).
- One open PR: `gddp-runtime` PR #25 (`docs/opclaw-root-cleanup`) — drops `OPCLAW_ROOT` from the env var table.
- Local Python env now has pytest 9.0.3, pyyaml 6.0.3, pydantic 2.13.4 installed via `pip3 install --user --break-system-packages` (was needed to run the test suite on this Pi).
- Test suite: **40 passed in 0.90s** — confirms the README claim exactly.

Artifacts:
- gddp-runtime PR #24 (merged, rebase): https://github.com/skchaudr/gddp-runtime/pull/24
- gddp-config PR #7 (merged, rebase): https://github.com/skchaudr/gddp-config/pull/7
- gddp-runtime PR #25 (open): https://github.com/skchaudr/gddp-runtime/pull/25
- Truth-check verification (all confirmed against current code):
  - All 22 README-referenced file paths exist.
  - `scripts/runtime/graph_updater.py` is a disabled stub returning `graph_mutation_disabled_review_required`.
  - `scripts/runtime/return_router.py:16` has `ALLOWED_REPOS = ["skchaudr/vault-doctor"]`.
  - Env vars `GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `GDDP_CONFIG_PATH` all wired as documented.
  - `python3 -m runtime.replay --result-id <id>` / `--job-id <id>` CLI matches `replay.py` docstring.
  - 7 schemas in `gddp-config/schemas/v1/` match the README's schema table exactly.
- Real inconsistency found: `OPCLAW_ROOT` env var is honored by `runtime/replay.py:44` and `runtime/openclaw/engine.py:31`, but ignored by `intake_server.py:27`, `rollback.py:21`, `heartbeat.py:29`, `dry_run.py:18` (all hardcode `Path(__file__).parent.parent`). PR #25 drops the doc claim only; the underlying code inconsistency is unresolved.

Resume point:
- Rebase-merge PR #25, then `git pull` locally to sync.
- Optional follow-up PR: make the four older modules (`intake_server`, `rollback`, `heartbeat`, `dry_run`) honor `OPCLAW_ROOT` the same way `replay.py` does, with tests. Behavioral change — own PR.
- Outstanding non-agent verification: comparative framing in the runtime README about other agent tools (GitHub Copilot, Claude-in-editor, "agent frameworks run autonomously until they hit a token limit") needs Saboor's web-search calibration before LinkedIn post — these are positioning claims, not facts I can grep.
- Working tree is clean except for the `docs/opclaw-root-cleanup` branch checkout.

## Narrative / Trajectory (SAB ONLY)
Intent:
Interpretation:
Tension:
Momentum:
