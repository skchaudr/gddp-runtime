# Patterns and conventions

## Core invariants

The runtime operates under several non-negotiable invariants. Violating these breaks the system's reason for existing.

1. **Runtime never mutates graph truth.** `gddp-config` is read-only from the runtime's perspective. Merged PRs create receipts. Humans decide whether graph truth changes. The `graph_updater.py` module opens evidence PRs against `gddp-config` but never pushes directly.

2. **Receipt-based return flow.** No silent writeback. A merged PR becomes a structured receipt in the `results` table with a verification verdict. The job routes to `awaiting_review` regardless of verdict outcome.

3. **Worst-of verdict combination.** The integrity lane can only worsen the criteria verdict, never upgrade it. A pass on criteria stays pass only if integrity also passes. Any integrity failure (drift, contradicted, block) floors the verdict at needs-human-review.

4. **Subprocess isolation for verification.** The verification bridge runs the CLI as a subprocess so an evaluator crash, hang, or timeout cannot take down the return router. The bridge retries once on transient failures.

5. **Read-only semantic tools.** The semantic agent's toolbox blocks network access (curl, wget, ssh, pip, npm), file mutations (rm, mv, tee, sed -i), git mutations (commit, push, reset, checkout), and destructive shell verbs. Python/python3 execution is allowed for running tests and scripts.

## Coding conventions

### Python style

- Standard library first. External dependencies are limited to Flask, PyYAML, Pydantic, and Anthropic SDK.
- Dataclasses for internal data structures (`NodeData`, `ProjectGraph`, `PlannedDispatch`, `DispatchOutcome`).
- Pydantic models for serialized/persisted schemas (`VerdictReceipt`, `SemanticOutput`, `IntegrityOutput`).
- SQLite connections use `row_factory = sqlite3.Row` and `PRAGMA foreign_keys=ON` everywhere.
- All SQLite mutations go through `state_recorder.py` or `results_store.py`. No ad hoc SQL scattered across the codebase.

### Environment variable resolution

Path resolution follows a consistent priority chain: explicit argument > environment variable > sibling directory convention.

```python
if config_path:
    self.config_path = Path(config_path)
elif os.getenv("GDDP_CONFIG_PATH"):
    self.config_path = Path(os.environ["GDDP_CONFIG_PATH"])
else:
    self.config_path = runtime_root.parent / "gddp-config"
```

### Credential resolution

Secrets (webhook secret, DeepSeek API key) are resolved from environment variables first, then from an external command (default: `pass` password manager). This keeps secrets out of plaintext env files. The pattern is configurable via `_CMD` environment variables.

### Error handling

- Verification errors are never fatal to the return path. A verification crash produces an explicit error record in the receipt, and the job still routes to `awaiting_review`.
- The decision loop catches all exceptions and produces an escalate result rather than crashing.
- The heartbeat uses atomic SQLite claims so a crashed heartbeat leaves events re-eligible after 30 minutes.

## Testing patterns

- Tests use `pytest` with SQLite in-memory or temporary databases.
- Test files live alongside source files: `test_*.py` in the same directory.
- 212 tests cover intake, heartbeat modules, state recording, executor adapters, return routing, verification (deterministic, semantic, integrity, orchestrator, bridge, retry budget, schemas), decision loop, and full-cycle end-to-end flows.

## Naming conventions

- Module names use `snake_case.py`.
- Class names use `PascalCase`.
- Constants use `UPPER_SNAKE_CASE`.
- SQL table names are lowercase plural (`events`, `jobs`, `results`).
- Verdict vocabulary comes from the node YAML in `gddp-config`, not from the runtime. The runtime does not invent verdict words.

## Canon and vocabulary doctrine

Four documents are canon (human-owned, small, and authoritative when prose and code disagree):

1. The project's foundational node (first node in `project.yaml`)
2. `README.md`
3. `PROJECT-BRIEF.md`
4. `AGENTS.md`

Canon has audiences. `AGENTS.md` is executor-canon and is deliberately excluded from evaluator context. Evaluators judge against graph truth plus README/brief context only. Generated artifacts (wikis, receipts, handoffs) capture canon but are never canon themselves.
