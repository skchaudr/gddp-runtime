# Changelog

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
