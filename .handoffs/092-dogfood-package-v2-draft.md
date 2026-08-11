# 092 — Dogfood run package v2 (DRAFT ONLY — nothing imports or dispatches)

**Date:** 2026-08-10. **Status:** DRAFT awaiting Sab review. Incorporates
co-advisor (Codex) corrections and operator rulings: report-only first, edit
shapes earned after evaluator visibility is proven; no live
dispatch/evaluator/reconciler/lock/capacity/status-semantics changes anywhere
in this package (those live in 091, unapproved backlog). 091's Factory lesson
applied: every node dead simple, one observable artifact, binary criteria.

**Graph:** `gddp-dogfood` (new). **Repo:** `skchaudr/gddp-runtime` (canonical
clone `/data/repos/gddp-runtime` — must be ff'd to origin/main first, see
reconciliation below). **Executor:** `local_subprocess` one-shot, pi
`xai/grok-4.5` (pinned in VM gddp.env, auth smoke PASSED 2026-08-10: "OK").
**Evaluator:** post-hoc pi harness, DeepSeek lane — effective key confirmed
(later line-21 export matches operator-confirmed key). Stale earlier duplicate
export is later cleanup, not a dispatch block. Env untouched per operator
ruling.
**Doctrine:** auto-advance, ≤3 retries, fresh one-shot per retry with
previous_findings. Artifacts land under `reports/gddp-dogfood/` on each node's
result branch; nothing merges without Sab.

## Tranche 1 — report-only canaries (3 nodes, read-only shape proven by vm-loop-smoke)

- **node-01-env-var-registry** — Grep all `GDDP_*` env vars read under
  `scripts/`; write `reports/gddp-dogfood/01-env-var-registry.md`: a table of
  name, file:line where read, default if any. Criteria: file exists, ≥10 rows,
  every row cites file:line, suite green.
- **node-02-archive-inventory** — Inventory `scripts/_archive/` and
  `deploy/_archive/`; write `02-archive-inventory.md`: exact path of every
  entry and its current stated purpose/evidence (README or header comments).
  Criteria: file exists, covers both dirs, suite green.
- **node-03-docs-inventory** — One line per `docs/*.md` plus a flag list of
  docs referencing removed machinery (`mission_push_guard`,
  `verify_planned_feature_ids`, `_feature_drift_reason`). Criteria: file
  exists, every docs file listed, flag list present (may be empty), suite green.

## Tranche 2 — more reports (7 nodes, release only after T1 lands evaluator-visible)

- **node-04-scripts-entrypoint-surface** — table of `scripts/*.py` CLI
  entrypoints and their subcommands. One report file.
- **node-05-test-suite-map** — per-file test counts + slowest 10 via
  `pytest --durations`. One report file.
- **node-06-deploy-topology** — `deploy/mini-heartbeat/` tree, one line per
  file's purpose, quoting real paths. One report file.
- **node-07-hook-surface** — what fires on commit/push in this repo
  (.agents/, graphify hooks, git hooks). One report file.
- **node-08-verification-module-map** — one line per module under
  `scripts/runtime/verification/`, including the two-lane flow. One report file.
- **node-09-heartbeat-module-map** — one line per module under
  `scripts/runtime/heartbeat/`. One report file.
- **node-10-agents-md-drift-report** — statements in AGENTS.md that contradict
  current code (removed gates, renamed paths), quoted with file:line
  counterevidence. Report only, no edits. One report file.

## Tranche 3 — tiny pure-function tests (6 nodes, first edit-shaped work; release after T2 reviewed)

- **node-11-test-manifest-name** — unit test for `_manifest_name` sanitize +
  digest shape. Criteria: new test file passes; suite green.
- **node-12-test-topological-order** — unit test for `_topological_nodes`.
- **node-13-test-render-item** — unit test for `_render_item` proxy rendering.
- **node-14-test-completion-id-digest** — unit test for `_completion_id` /
  `_completion_digest` stability.
- **node-15-test-normalize-digest** — unit test for `_normalize_digest`
  hex-shape validation.
- **node-16-test-select-handoff** — unit test for `_select_handoff` latest-wins
  and worker-session pinning.

## Tranche 4 — one-file docs/cleanup (6 nodes, release after T3 reviewed)

- **node-17-doc-local-executor** — `docs/local-subprocess-executor.md`: the
  argv/env contract as implemented. One file.
- **node-18-doc-evaluator-cli** — `docs/evaluator-cli.md`: post-hoc evaluation
  invocation, flags, env keys. One file.
- **node-19-handoff-index** — `.handoffs/INDEX.md`: every handoff file with a
  one-line title. One file.
- **node-20-register-annotations** — annotate `docs/blocking-mechanisms-register.md`
  header with which BMs demolition Stages 1–3 executed (BM-019/020/030–036).
  One file, mechanical edit.
- **node-21-worktree-convention-doc** — `docs/worktree-convention.md`: stage
  work in worktrees, never the shared checkout. One file.
- **node-22-doc-executor-contract** — `docs/executor-contract.md`: NodePacket /
  PatchResult field reference as implemented in `executor_protocol.py`. One file.

22 nodes drafted (T1 3 · T2 7 · T3 6 · T4 6). **Excluded on purpose:**
everything in 091, node_status_history classification (operator-preserved
evidence, not package scope), flask intake tests (env gap), merge machinery,
node-10/11.
