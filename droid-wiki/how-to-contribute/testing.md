# Testing

The test suite is 212 tests, all run through pytest. No lint is configured.

## Running the tests

```bash
python3 -m pytest -q
```

All 212 tests should pass. The `-q` flag keeps output to one line per test. There is no coverage tooling configured and no lint step. If pytest is not installed, install it with `pip install pytest`.

## Test file layout

Test files live alongside source files, not in a separate `tests/` directory. Each test file is named `test_*.py` and sits in the same directory as the module it tests. This is the project convention. If you add a module, put its tests next to it.

## Test categories

The suite covers every runtime subsystem. Here are the categories and the test files that belong to each.

### Intake server

Tests for the webhook intake server in `scripts/test_intake_server.py`. Covers event normalization, signature verification, raw payload storage, and event insertion into the `events` table.

### Heartbeat modules

Tests for the heartbeat subsystem under `scripts/runtime/heartbeat/`:

- `test_classifier.py` - event classification logic
- `test_parallel_dispatch.py` - parallel dispatch of ready nodes to executors
- `test_claiming.py` - atomic SQLite claims that prevent double-dispatch

### State recording

Tests for the state recorder and results store:

- `scripts/runtime/test_results_store.py` - receipt persistence in the `results` table
- State recorder tests covering job status transitions and event mapping (tested through the heartbeat and return router test suites)

### Executor adapters

Tests for the Jules adapter in `scripts/adapters/test_jules_action_adapter.py`. Covers GitHub issue creation, work packet formatting, and dispatch outcome handling.

### Return router

Tests in `scripts/runtime/test_return_router.py` for the return router (`scripts/runtime/return_router.py`). Covers merged-PR handling, receipt creation, verification trigger, and job routing to `awaiting_review`.

### Verification

The largest test category, covering the two-lane evaluator under `scripts/runtime/verification/`:

- `deterministic/test_deterministic.py` - deterministic probe lane
- `semantic/test_context_builder.py` - semantic agent context assembly
- `semantic/test_semantic_agent_tools.py` - read-only tool constraints for the semantic agent
- `test_integrity_runner.py` - integrity lane execution
- `test_integrity_combiner.py` - worst-of verdict combination between lanes
- `test_orchestrator.py` - orchestrator that coordinates both lanes
- `test_bridge.py` - subprocess isolation bridge between return router and evaluator CLI
- `test_retry_budget.py` - retry budget tracking for transient verification failures
- `test_schemas.py` - Pydantic schema validation for verdict receipts and lane outputs
- `test_shape_profiles.py` - shape profile matching for deterministic checks
- `test_cli.py` - the verification CLI entry point
- `test_dry_run_e2e.py` - end-to-end verification against the dry-run flow
- `test_decision_engine.py` - decision engine within the verification layer

### Decision loop

Tests for the decision loop under `scripts/runtime/decision_loop/`:

- `test_decision_loop.py` - core decision loop logic
- `test_engine_verification.py` - engine verification integration
- `test_runner_resolution.py` - runner resolution for dispatch targets

### Runtime root config

Tests in `scripts/test_runtime_root_config.py` for the environment variable resolution chain (`GDDP_RUNTIME_ROOT`, `OPCLAW_ROOT` fallback, repo-root default) and path resolution across modules.

### Full-cycle end-to-end

Tests in `scripts/runtime/test_full_cycle_e2e.py` that exercise the complete cycle: event intake through classification, dispatch, result, verification, and review routing. These are the integration tests that validate the pipeline plumbing end to end.

### Replay and graph updater

- `scripts/runtime/test_replay.py` - replay utilities for re-running return router logic and re-dispatching jobs
- `scripts/runtime/test_graph_updater.py` - graph updater that opens evidence PRs against `gddp-config` (never pushes directly)

## Testing patterns

Tests use pytest with SQLite in-memory or temporary databases. No test touches real GitHub APIs, real executors, or real LLM endpoints. The verification bridge is mocked in tests so no actual subprocess or API call happens. See [Patterns and conventions](patterns-and-conventions.md) for the coding and naming conventions that apply to test code as well.

## What is not tested

There is no lint configuration. No type checker is configured. The test suite does not cover the systemd service files, cron configuration, or ngrok setup. Those are operational concerns documented in the [Big Pi runbook](../../deploy/BIGPI_RUNBOOK.md) and the [Deployment](../deployment.md) page.

## Related pages

- [Development workflow](development-workflow.md) - the branch/commit/test cycle
- [Patterns and conventions](patterns-and-conventions.md) - test file layout and conventions
- [Debugging](debugging.md) - what to do when tests fail or the runtime misbehaves
- [Getting started](../overview/getting-started.md) - first-time setup
