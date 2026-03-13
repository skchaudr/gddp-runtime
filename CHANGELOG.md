# Changelog

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
