# Mission Plan: Node 2 Real Direct Executor Round Trip

## Plan Overview

Prove the direct executor round trip with a real local agent dispatching `job-state-consistency`, producing a real evaluator verdict A/B-comparable against the 2026-07-24 fail receipt. All evidence persists. No resets. Also: archive surviving canary evidence, write the reusable local executor wrapper.

## Milestone 1: evidence-archive-and-wrapper

### Feature 1: Archive surviving synthetic canary evidence

- Copy both receipts -- `job_20260724T010811130dd14802e579-attempt0.json` and `-attempt0-rerun1.json` -- into `.handoffs/artifacts/053-node2-real-round-trip/`. The pair is evidence of the duplicate-evaluation race observed twice 2026-07-23 and is itself input to Node 4.
- Extract patch from the `gddp/result-...` ref into `surviving-canary-patch.diff`; record ref name, SHA, DB state in the summary; commit as durable artifacts.

### Feature 2: Write real local executor wrapper

- Create `scripts/local_agent_executor.py`. Reads `packet.json` on stdin; extracts criteria/constraints/goal; builds the agent prompt.
- The wrapper creates a temporary git worktree at the packet's `expected_base_commit_sha` and runs the agent CLI inside that worktree only, never the live repo tree. It emits `git diff` from that worktree to stdout and removes the worktree afterward. The prompt passes the absolute path to the live `db/queue.db` for read-only inspection; reconcile SQL is written into `decision.md`, never executed against the live DB by the agent.
- Pin the agent CLI in the script; tests for packet parsing, prompt construction, diff emission.

### Pre-flight gate

Reproduce the evaluator's `suite-green` result from the 2026-07-24 receipt. Run pytest inside an evaluator-style worktree; note that `.venv/bin/python` does not exist in worktrees. Explain the "4 failed, 360 passed." If environmental, report to Sab before dispatch -- the A/B expected pass may be unreachable on that criterion regardless of fix quality. Do not fix the evaluator environment in this mission. This gate blocks Milestone 2.

## Milestone 2: real-node-dispatch

### Feature 3: Dispatch job-state-consistency through local executor

- Precondition: `gddp-config/graphs/gddp-runtime/nodes/job-state-consistency.yaml` has `local_subprocess` as the first entry in `allowed_execution_modes`.
- Before dispatch, ask Sab whether to unload `com.gddp.heartbeat` for the run window. Record the choice and consequence in the evidence.
- Inject event, run dispatch tick via LocalSubprocessAdapter with the wrapper, agent produces fix, run reconcile ticks, evaluate with real DeepSeek key, reach `awaiting_review`.

### Feature 4: Verify and preserve evidence

- Full round-trip verification: dispatch through awaiting_review, hash unchanged, real semantic judgment confirmed via `lane_status`, artifacts archived, compare against jules branch reference fix. No resets.

## Environment / Infrastructure

- Repo: `/Users/sab-mini/repos/gddp-runtime`, main, 373 tests pass
- gddp-config: `allowed_execution_modes` on `job-state-consistency` has `local_subprocess` as first entry
- Local agents: `claude`, `codex`, `grok`, `gemini`, `pi` -- all available
- DeepSeek key: `pass show api/deepseek`
- No services to start. No fake keys. No resets. No `GDDP_EXECUTOR_OVERRIDE` for real nodes.

### Off-limits

- gddp-config graph truth -- read-only except Sab's edits
- Live repo working tree during agent execution -- wrapper worktree only
- No fake API keys
- No resetting or deleting evidence after runs
- Port 5050 -- not needed

## Testing

- Milestone gate: `python3 -m pytest -q`
- User testing surface: CLI (`node_status.py show/list`), SQLite queries, git refs, file existence checks, `project.yaml` hash verification

## Mission Readiness

All dependencies verified: Python 3.11+, 373 tests pass, local agents available, DeepSeek key accessible, SQLite DB accessible, git clean. The pre-flight gate is a blocking readiness item before Milestone 2 dispatch.

## Non-Functional Requirements

- Evidence preservation: all forensic artifacts committed to repo, no resets, DB rows and git refs survive
- Graph truth integrity: `project.yaml` hash unchanged
- Real evaluation: real DeepSeek API key only
- No `GDDP_EXECUTOR_OVERRIDE` for real nodes
- Human-owned acceptance: mission stops at `awaiting_review`
