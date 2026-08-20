# Changelog

## [1.1.2] - 2026-04-07

### Changed
- `scripts/runtime/return_router.py` now converts merged PRs into structured review receipts only; it no longer mutates graph truth or calls `graph_updater.py`
- `scripts/runtime/results_store.py` now writes return receipts into the canonical `results` table and preserves the existing `needs_review` receipt status
- merged PR handling now routes matching jobs and queue records to `awaiting_review` instead of implying automatic node completion
- `scripts/runtime/heartbeat/job_factory.py` now builds jobs with the classifier-selected executor and frames the goal as producing a reviewable result
- `scripts/runtime/heartbeat/dispatcher.py` now routes through an executor registry keyed by the persisted job executor instead of hardcoded Jules-only branching
- `scripts/runtime/heartbeat/classifier.py` no longer advertises automatic return-path routing through the heartbeat runner
- `scripts/adapters/jules_action_adapter.py`, `README.md`, and `scripts/dry_run.py` now document the review-receipt boundary instead of automatic graph advancement

### Removed
- `scripts/runtime/graph_updater.py` is no longer an active runtime graph mutation mechanism; it remains only as a disabled compatibility stub
- runtime return flow no longer depends on `return_results`-style persistence or `graph-update.yaml` mutation artifacts

## [1.1.1] - 2026-03-19

### Added
- `deploy/deploy.sh` — canonical Big Pi deploy command
- `~/opclaw/.gddp-runtime-deploy.json` deploy marker written by `deploy/deploy.sh`

### Changed
- `deploy/setup.sh` now uses the canonical deploy command instead of ad hoc script copying
- `README.md` now documents `~/repos/gddp-runtime` as source of truth and `~/opclaw/scripts` as deployed runtime surface

## [1.1.0] - 2026-03-13

### Added
- `scripts/runtime/heartbeat/` — modular heartbeat vNext replacing hardcoded Phase 3 dispatcher
  - `graph_reader.py` — reads gddp-config project/node YAML; resolves ready nodes dynamically
  - `classifier.py` — maps event → node based on graph state and priority ordering
  - `scope_checker.py` — active job guard + dependency check (prevents duplicate dispatch)
  - `job_factory.py` — builds job payload from NodeData (replaces inline hardcoded dict)
  - `state_recorder.py` — all SQLite mutations in one module
  - `dispatcher.py` — routes to executor adapter (v1: jules; extensible to codex/vertex)
  - `runner.py` — main loop; entry point replacing `scripts/heartbeat.py`

---

## [1.0.0] - 2026-03-13

### Added
- Initial commit — promoted scripts from untracked `~/opclaw-test/`
- `scripts/intake_server.py` — Flask webhook intake server
- `scripts/heartbeat.py` — event poller and job dispatcher
- `scripts/init_db.py` — SQLite schema initialization
- `scripts/dry_run.py` — fake end-to-end flow for testing
- `scripts/rollback.py` — job rollback utility
- `scripts/adapters/jules_action_adapter.py` — Jules dispatch via GitHub Actions label
- `scripts/adapters/jules_cli_adapter.py` — Jules CLI adapter stub
- `deploy/opclaw-intake.service` — systemd service unit for Big Pi
- `deploy/setup.sh` — Pi deployment script

### Fixed
- Heartbeat classifier: `pull_request.opened` events no longer trigger Jules dispatch
  (was causing infinite dispatch loops during Phase 3-4 testing)
