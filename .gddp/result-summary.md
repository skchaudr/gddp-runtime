# Result Summary: neutral-executor-contract

Milestone 1 of the approved 5-node executor-neutral plan is implemented and ready for human review.

## Acceptance evidence

- **Executor-neutral packet:** `NodePacket` is immutable and deterministically serializable. The same semantic packet reaches Jules CLI, the mediated Jules action path, and the local subprocess adapter without dropping constraints, criteria, required artifacts, prior findings, attempt index, or `execution_attempt_id`.
- **Execution-attempt identity:** attempt identity/index are persisted per executor session before dispatch. Historical sessions remain intact across retries. Retry allocation/finalization uses compare-and-swap behavior to prevent cancellation races and duplicate dispatch.
- **Shared result shape:** direct adapters implement the runtime-checkable `ExecutorAdapter` protocol and return common `DispatchResult`, `SessionStatus`, and `PatchResult` types. The inherited action path is explicitly mediated rather than falsely presented as a direct lifecycle adapter.
- **Evidence only:** returned output remains review evidence. Runtime job/session state can reach `awaiting_review`, but no implementation path changes graph truth or completes the node.

## Verification observed

- `python3 -m pytest -q` — **365 passed in 5.34s** after commit `3881208`.
- Repeated smoke: `python3 scripts/init_db.py && python3 scripts/dry_run.py && python3 scripts/dry_run.py` — both dry runs completed against the same isolated worktree DB.
- Neutrality proof: three targeted adapter-contract tests — **5 passed in 0.10s** (including all parametrized transports and local adapter re-instantiation/collection).
- Retry/cancellation focused gate — **81 passed in 1.94s** before the fixture-only follow-up.
- Task reviews rejected concrete state-machine races, fixes were applied, and final re-reviews approved with no Critical/Important findings.
- Two live Pi evaluator attempts produced fail-closed `needs-human-review` receipts. Both criteria and integrity lanes crashed before judgment because the configured provider received an OpenRouter-formatted key at the OpenAI endpoint; the rerun with explicit GLM selection behaved identically. No semantic or integrity verdict is claimed.

## Commits

- `e670c0b` repeatable dry-run setup
- `1d4c4c7` neutral packet and adapter contract
- `b87b43d` attempt identity and local-adapter hardening
- `d396430` durable retry/cancellation lifecycle
- `79f181d` retry dispatch race hardening
- `c3cc954` bounded missing-session reconciliation
- `3881208` production-shaped test fixtures

## Residual risks

- Jules remote compute may continue after local cancellation because the installed CLI exposes no cancel command; GDDP records this as unsupported and refuses further polling/integration.
- A controller crash after remote acceptance but before finalization leaves a visible reserved attempt for stale recovery rather than automatically risking duplicate execution.
- Legacy executor-session rows receive reconstructed attempt ordering during migration because historical rows did not record an exact ordinal.
- The evaluator CLI/provider configuration must be corrected in its own bounded graph work before a live semantic receipt can replace the preserved crash receipts. Milestone 2 remains blocked on Sab's review of this evidence.
