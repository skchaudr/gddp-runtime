# 126 — Dispatch schema drift: init_db path, isolated reservation proof, live hold

------------------------------------------------ Agent Section START

Date: 2026-09-06
Worktree: /home/sab-mini/gddp-runtime
Branch: main

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Live `db/queue.db` `jobs` still lacks `expected_base_commit_sha`; `gddp-heartbeat.timer` is active and each tick that reaches reservation dies at `state_recorder.insert_job` (journal 11:49:40Z and 14:31:10Z). Isolated tests reproduce that OperationalError on a disposable copy of the live jobs shape, then `init_db()` (existing `_ensure_column`) makes `_plan_dispatches` succeed; fake-executor success/failure receipts and stranded-claim recovery (30-minute lease, then `awaiting_result` scope-block or `mark_event_mapped`) are proven. `runner.connect()` still skips `ensure_schema()` so the installed systemd unit will keep crashing until the operator holds the timer and applies the canonical migrate; the repo unit file now runs `scripts/init_db.py` before the runner, and the installed copy in `~/.config/systemd/user/` is unchanged.

### Scope touched (One file per line, +/- for only what was changed)

+ scripts/init_db.py (`db_path` / `quiet` on existing `init_db()`)
+ scripts/runtime/heartbeat/runner.py (`ensure_schema()` helper; `connect()` body unchanged)
+ scripts/runtime/heartbeat/scope_checker.py (`awaiting_result` in the active-job guard)
+ scripts/runtime/heartbeat/test_claiming.py (parametrize `awaiting_result`)
+ scripts/runtime/heartbeat/test_schema_reservation.py
+ deploy/mini-heartbeat/systemd/gddp-heartbeat.service (ExecStart runs `init_db.py`; installed unit left as-is)

### Constrained areas touched (none / list + justification)

Live `db/queue.db`, graph YAML, node statuses, aa-cli checkout, and `gddp-heartbeat.timer` left as found. `scope_checker` now treats `awaiting_result` as active (aligns with frontier/adopt); that only narrows duplicate dispatch.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

`main` tracks `origin/main`; task files uncommitted (operator forbade commit/push). `.tmp/` was already untracked. aa-cli checkout untouched (`main` ahead 1 with its own dirty hub-rs files).

### Artifacts (Filepath - Description, 1 line max per artifact)

- scripts/runtime/heartbeat/test_schema_reservation.py — legacy schema reproduction, init_db reservation, fake-executor smoke, stranded-claim recovery
- deploy/mini-heartbeat/systemd/gddp-heartbeat.service — repo copy; live unit still the 2026-08-05 install without init_db

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Validation: `python3 -m pytest -q scripts/runtime/heartbeat/ scripts/test_init_db.py` → 298 passed. Live recovery after `systemctl --user stop gddp-heartbeat.timer`: `source deploy/mini-heartbeat/env/gddp.env && python3 scripts/init_db.py`, then hold `evt_frontier_20260906T060450_nav-input-repair_9f1cbe` via `jobs adopt` (scope-block) or `mark_event_mapped`, then `ensure_schema()` as the first line of `connect()` (covers launchd/smoke) and/or copy the repo systemd unit + `daemon-reload`. Restart the timer only after that hold; a migrate-only restart will reclaim the stale claim and launch `cursor_cli` on `nav-input-repair`.

------------------------------------------------ Agent Section END
