# Testing

`gddp-runtime` uses pytest. Tests live beside the modules they exercise. There is no configured linter or formatter; match the neighboring file style.

## Running the suite

The canonical command:

```bash
.venv/bin/python -m pytest -q scripts
```

This walks `scripts/` and picks up every `test_*.py` / `*_test.py`. The suite covers intake, heartbeat, adapters, verification, jobs status, and mission machinery.

Run from the repo root. Tests set up their own temporary DB paths and fixtures; they do not touch `db/queue.db`.

## Focused mission tests

The README calls out a focused mission suite. It exercises the Factory mission projection, adapter, evidence, git-verify, push-guard, reconciler, and node receipt paths:

```bash
.venv/bin/python -m pytest -q \
  scripts/adapters/test_mission_adapter.py \
  scripts/adapters/test_mission_projection.py \
  scripts/adapters/test_mission_evidence.py \
  scripts/adapters/test_mission_git_verify.py \
  scripts/adapters/test_mission_push_guard.py \
  scripts/runtime/heartbeat/test_mission_config.py \
  scripts/runtime/heartbeat/test_mission_reconciler.py \
  scripts/runtime/heartbeat/test_mission_pipeline_e2e.py \
  scripts/test_gddp_node_receipt.py
```

Use this when you are changing mission code; it is faster than the full suite and catches most regressions in the Factory integration.

## Running a single file or test

```bash
# One file
.venv/bin/python -m pytest -q scripts/runtime/heartbeat/test_runner.py

# One test
.venv/bin/python -m pytest -q scripts/adapters/test_mission_adapter.py::test_name
```

Add `-v` for verbose output, `-x` to stop on first failure, `-s` to disable capture when you need prints during a debug session.

## Test layout

Tests live beside the code they exercise:

| Area | Location |
| --- | --- |
| Intake / webhook | `scripts/test_intake_server.py`, `scripts/test_intake_webhook_roundtrip.py` |
| Jobs status | `scripts/test_jobs_status.py`, `scripts/test_jobs_status_evaluator.py` |
| Heartbeat / runner | `scripts/runtime/heartbeat/test_runner.py`, `test_parallel_dispatch.py`, `test_claiming.py`, `test_frontier.py`, `test_classifier.py`, `test_classifier_routing.py`, `test_completion_discipline.py`, `test_provisional_gate.py`, `test_mission_config.py`, `test_mission_reconciler.py`, `test_mission_pipeline_e2e.py`, `test_executor_sessions.py`, `test_base_chaining.py` |
| Adapters / mission | `scripts/adapters/test_mission_adapter.py`, `test_mission_projection.py`, `test_mission_evidence.py`, `test_mission_git_verify.py`, `test_mission_push_guard.py` |
| Node receipt | `scripts/test_gddp_node_receipt.py` |
| Local agent executor | `scripts/test_local_agent_executor.py` |
| Verification | `scripts/runtime/verification/` (alongside verifier modules) |
| Mini-heartbeat kit | `deploy/mini-heartbeat/test_arm_refuse.py`, `test_smoke_dry.py`, `test_render_plist.py` |

When adding a new module, place `test_<module>.py` next to it. The suite finds it via the `scripts` root passed to pytest.

## Fixture patterns

Tests use temp DB paths and isolated fixtures. Do not depend on production `db/queue.db`. When a test needs SQLite:

- Create a temp directory (`tmp_path` from pytest) and point `DB_PATH` / `RUNTIME_ROOT` at it.
- Run `scripts/init_db.py` (or its in-test equivalent) to create the schema.
- Use that connection; close and tear down at the end.

The heartbeat tests in `scripts/runtime/heartbeat/` share a common pattern of building a small in-memory graph (a handful of nodes with explicit dependencies), creating a temp `queue.db`, and driving the runner through `run_heartbeat(...)` with explicit project / repo / config-path arguments. Follow that shape for new heartbeat tests.

Mission adapter tests similarly build a fake Factory mission state under a temp dir and exercise the projection / evidence / git-verify pipeline without touching `~/.factory/missions`.

## Database isolation

**Never hit the production DB from tests.** This is a hard rule. The test suite is expected to be runnable on any machine with the repo cloned and the venv set up, without any production state present.

When in doubt:

- Set `GDDP_RUNTIME_ROOT` to a temp directory before importing runtime modules that resolve `DB_PATH` at module load time.
- Pass explicit paths into functions that accept them.
- Patch `sqlite3.connect` if a deeper module insists on the default path.

## What the suite does and does not cover

The suite is a regression net, not a proof of correct behavior under production load. It does not cover:

- Live webhook round-trips against `sab-mini`'s intake server (HMAC and secret rotation are tested in unit tests against `GITHUB_WEBHOOK_SECRET`, not against production).
- Real droid mission end-of-run behavior (mission adapter has partial crash/resume coverage via PROBE-2A but not a full live droid run).
- Real Jules CLI/API dispatch against the external service; adapters are implemented, while the suite uses doubles.
- Concurrent SQLite contention at production scale (coordinator serialization is covered by unit tests, not load tests).

When a behavior is not covered and the assumption matters, record it in the handoff and add a probe or integration test before relying on it.

## Known test limitations

- `test_mission_pipeline_e2e.py` is the largest test and the slowest. When iterating, start with `test_mission_reconciler.py` and `test_mission_config.py`.
- Some mission tests assert on specific exit-reason strings; if you change a reason, update the test.
- The heartbeat runner has a large number of edge-case tests; the suite passes but individual tests can be slow under load.
- Intake tests assume `GITHUB_WEBHOOK_SECRET` is either set in the environment or `GDDP_INTAKE_INSECURE=1` is accepted by the harness. For dev runs, the latter is fine.

## Related

- [Development workflow](development-workflow.md) — definition of done
- [Debugging](debugging.md) — when tests pass but the runtime misbehaves
- [Tooling](tooling.md) — `init_db` and replay
- [Patterns and conventions](patterns-and-conventions.md) — evidence over ceremony
- [Overview — getting started](../overview/getting-started.md) — install, DB, first smoke
