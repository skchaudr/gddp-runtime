# Factory/Droid mission-mode external forensics

Scope: Droid v0.189.0 at `/Users/sab-mini/.local/bin/droid`; richest specimen `/Users/sab-mini/.factory/missions/3efe69ab-0dc5-4a45-bbca-cc815844a679`; observed 2026-08-07. `~/.factory/` and repositories were read only. The live mission `160ee18c-ca3e-4b6f-ad98-f81bf216459a` was not touched; its files were a mutating mid-flight specimen, so no absence observed there is treated as terminal evidence.

Evidence notation: JSON citations use `path#JSON-pointer`; JSONL citations use `path:line`; binary citations use byte offsets from read-only `mmap` searches. Claims not directly settled are marked **INFERRED** and paired with a probe.

## 1. Artifact inventory

**Verdict: the directory is a mission-wide control/evidence workspace written by the orchestrator/runtime, mission workers, and validators; only handoff files and individual JSONL records have observed write-once semantics — confidence: high**

Inventory (size and mtime are the observed specimen values; directories omitted where their role is obvious from children):

| Artifact | Size | mtime (local) | Role | Writer |
|---|---:|---|---|---|
| `AGENTS.md` | 2,397 | 2026-07-23 22:47:56 | mission boundaries/directives | orchestrator/planning |
| `architecture.md` | 3,655 | 2026-07-23 22:47:19 | planned system/data flow | orchestrator/planning |
| `mission.md` | 4,400 | 2026-07-23 22:46:24 | mission plan and milestones | orchestrator/planning |
| `features.json` | 9,956 | 2026-07-24 00:20:42 | mutable feature queue/status/session linkage | runtime and orchestrator |
| `state.json` | 233 | 2026-07-24 00:27:20 | mutable mission lifecycle state | runtime |
| `progress_log.jsonl` | 35,291 | 2026-07-24 00:27:20 | append-only mission/worker event stream | runtime |
| `worker-transcripts.jsonl` | 103,969 | 2026-07-24 00:20:42 | one transcript skeleton per completed worker | runtime, derived from worker transcript |
| `validation-state.json` | 2,791 | 2026-07-24 00:19:59 | mutable assertion statuses | user-testing validator |
| `validation-contract.md` | 20,865 | 2026-07-24 00:23:25 | mutable validation specification | orchestrator/delegated worker |
| `model-settings.json` | 259 | 2026-07-23 22:46:24 | mission worker/validator model selection | runtime/orchestrator |
| `runtime-custom-models.json` | 13,746 | 2026-07-24 00:09:30 | mission-local resolved model catalog | runtime |
| `working_directory.txt` | 34 | 2026-07-23 22:46:24 | `/Users/sab-mini/repos/gddp-runtime` | runtime at mission creation |
| `services.yaml` | 228 | 2026-07-23 22:47:56 | install/test/typecheck/lint commands; no services | orchestrator/planning |
| `init.sh` | 646 | 2026-07-23 22:47:56 | worker startup checks | orchestrator/planning; executed by workers |
| `library/environment.md` | 1,875 | 2026-07-24 00:08:22 | shared environment discoveries | scrutiny validator applied update |
| `library/user-testing.md` | 2,515 | 2026-07-24 00:19:36 | validator surface and concurrency guidance | user-testing validator |
| `skills/runtime-worker/SKILL.md` | 4,399 | 2026-07-23 22:48:47 | feature-specific worker procedure | orchestrator/planning |
| `handoffs/*.json` (7 files) | 2,996–6,185 | completion timestamps 05:56–07:20Z | terminal per-worker handoff | EndFeatureRun/runtime from worker payload |
| `validation/.../scrutiny/reviews/*.json` (3) | 2,082–2,368 | 00:05–00:07 | per-feature scrutiny reviews | scrutiny subvalidators |
| `validation/.../scrutiny/synthesis.json` | 2,904 | 00:08:40 | milestone scrutiny synthesis | scrutiny validator |
| `validation/.../user-testing/flows/{archive,wrapper,preflight}.json` | 5,759–10,168 | 00:13–00:18 | per-flow test reports | flow validators |
| `validation/.../user-testing/synthesis.json` | 2,416 | 00:20:15 | milestone user-test synthesis | user-testing validator |
| `evidence/.../archive/archive-validation-transcript.txt` | 2,425 | 00:12:27 | archived CLI evidence | flow validator |
| `evidence/.../wrapper/*.txt` (2) | 3,276; 3,854 | 00:14–00:15 | wrapper validation transcripts | flow validator |
| `evidence/.../preflight/*.txt` (3) | 177; 3,933; 17,362 | 00:17 | preflight evidence transcripts | flow validator |

Evidence: metadata from `find ... -print0 | xargs -0 stat -f '%Sp %z %Sm %N'`; writer roles from the embedded `MissionFileService` methods at binary byte offsets around 68,334,953–68,349,247 and from each artifact's content. `worker-transcripts.jsonl` has exactly seven records with schema `{workerSessionId,featureId,milestone,skeleton,timestamp}`.

## 2. Exact schemas and real examples

**Verdict: schemas are explicit and externally parseable; handoffs use `workerSessionId` (not `sessionId`) and contain all requested semantic fields under `handoff` — confidence: high**

### `features.json`

Schema from binary byte 62,914,074 and the whole real file: root `{features: Feature[]}`; `Feature={id:string, description:string, status:pending|in_progress|completed|cancelled, skillName:string, preconditions:string[], expectedBehavior:string[], fulfills?:string[], milestone?:string, workerSessionIds?:string[], currentWorkerSessionId?:string|null, completedWorkerSessionId?:string|null}`. The full real example is reproduced verbatim:

```json
{
  "features": [
    {
      "id": "user-testing-validator-evidence-archive-and-wrapper",
      "description": "User testing validation for milestone \"evidence-archive-and-wrapper\". Determines testable assertions from features' fulfills field, sets up environment, spawns flow validator subagents, synthesizes results. Always returns to orchestrator.",
      "skillName": "user-testing-validator",
      "preconditions": [
        "All implementation features for milestone \"evidence-archive-and-wrapper\" are complete"
      ],
      "expectedBehavior": [
        "Testable assertions determined from fulfills mapping",
        "Environment set up (services started, data seeded)",
        "Flow validator subagents spawned and completed",
        "Results synthesized, validation-state.json updated"
      ],
      "milestone": "evidence-archive-and-wrapper",
      "status": "pending",
      "workerSessionIds": [
        "2c6166f9-787f-4b39-9159-0f7eb807daa1"
      ],
      "currentWorkerSessionId": null,
      "completedWorkerSessionId": null
    },
    {
      "id": "dispatch-job-state-consistency",
      "description": "Dispatch job-state-consistency through LocalSubprocessAdapter with the real wrapper. Precondition: local_subprocess is first in allowed_execution_modes. Ask Sab about unloading com.gddp.heartbeat. Inject event, run dispatch tick, agent produces fix in worktree, run reconcile ticks, evaluate with real DeepSeek key, reach awaiting_review.",
      "skillName": "runtime-worker",
      "preconditions": [
        "local_agent_executor.py exists and is tested",
        "job-state-consistency.yaml has local_subprocess as first allowed_execution_modes entry",
        "Pre-flight gate has passed or been resolved with Sab",
        "DeepSeek API key available via pass show api/deepseek"
      ],
      "expectedBehavior": [
        "No GDDP_EXECUTOR_OVERRIDE used for the dispatch",
        "Sab asked about com.gddp.heartbeat before dispatch, choice recorded",
        "Event injected into queue DB",
        "Dispatch tick routes through LocalSubprocessAdapter + wrapper",
        "Agent produces a fix inside the worktree",
        "Reconcile ticks run, patch committed to durable git ref",
        "Evaluation uses real DeepSeek key (not placeholder)",
        "Job reaches awaiting_review"
      ],
      "fulfills": [
        "VAL-DISPATCH-001",
        "VAL-DISPATCH-002",
        "VAL-DISPATCH-003",
        "VAL-DISPATCH-004",
        "VAL-DISPATCH-005",
        "VAL-DISPATCH-006",
        "VAL-DISPATCH-007",
        "VAL-DISPATCH-008",
        "VAL-DISPATCH-009"
      ],
      "milestone": "real-node-dispatch",
      "status": "pending",
      "workerSessionIds": [],
      "currentWorkerSessionId": null,
      "completedWorkerSessionId": null
    },
    {
      "id": "verify-and-preserve-evidence",
      "description": "Verify full round trip end-to-end. Confirm project.yaml hash unchanged. Confirm real semantic judgment (lane_status completed, not crashed). Archive round-trip artifacts as committed files. Compare agent fix with jules branch reference fix. Confirm no resets performed.",
      "skillName": "runtime-worker",
      "preconditions": [
        "job-state-consistency dispatch completed and reached awaiting_review"
      ],
      "expectedBehavior": [
        "Full round trip proven: dispatch through awaiting_review",
        "project.yaml SHA-256 unchanged from baseline 781c626a...80207b8a",
        "Receipt shows lane_status=completed (real semantic judgment)",
        "Forensic artifacts (receipt JSON, patch, git ref) archived as committed files",
        "Agent fix compared with jules branch reference fix, differences documented",
        "No DB rows deleted, no git refs removed, no resets performed"
      ],
      "fulfills": [
        "VAL-VERIFY-001",
        "VAL-VERIFY-002",
        "VAL-VERIFY-003",
        "VAL-VERIFY-004",
        "VAL-VERIFY-005",
        "VAL-VERIFY-006",
        "VAL-XFLOW-001",
        "VAL-XFLOW-002"
      ],
      "milestone": "real-node-dispatch",
      "status": "pending",
      "workerSessionIds": [],
      "currentWorkerSessionId": null,
      "completedWorkerSessionId": null
    },
    {
      "id": "archive-surviving-evidence",
      "description": "Copy both receipt JSONs (job_20260724T010811130dd14802e579-attempt0.json and -attempt0-rerun1.json) from gddp-config/verification-runtime-live into .handoffs/artifacts/053-node2-real-round-trip/. Extract patch from gddp/result-* git ref into surviving-canary-patch.diff. Record ref name, SHA, DB state in summary. Commit as durable artifacts.",
      "skillName": "runtime-worker",
      "preconditions": [
        "Receipt JSONs exist at gddp-config/verification-runtime-live/gddp-runtime/job-state-consistency/",
        "Git ref gddp/result-job_20260724T010811130dd14802e579-* exists in the repo"
      ],
      "expectedBehavior": [
        "Both receipt JSONs copied to .handoffs/artifacts/053-node2-real-round-trip/",
        "Patch diff extracted from git ref",
        "Summary file records ref name, commit SHA, and DB state at time of archival",
        "All artifacts committed to git"
      ],
      "fulfills": [
        "VAL-ARCHIVE-001",
        "VAL-ARCHIVE-002",
        "VAL-ARCHIVE-003",
        "VAL-ARCHIVE-004"
      ],
      "milestone": "evidence-archive-and-wrapper",
      "status": "completed",
      "workerSessionIds": [
        "498a1331-ffed-435f-b768-d4ec017c97b1",
        "ac4d6392-de0c-450f-a585-328db909490b"
      ],
      "currentWorkerSessionId": null,
      "completedWorkerSessionId": null
    },
    {
      "id": "simplify-executor-to-worktree-only",
      "description": "Strip scripts/local_agent_executor.py down to the minimal necessary function: worktree management. The wrapper does exactly three things: (1) git worktree add --detach at expected_base_commit_sha, (2) pipe the raw packet JSON to the agent CLI as its prompt input, (3) emit git diff from the worktree on stdout. No prompt formatting, no DB path plumbing, no constraint decomposition, no isolation enforcement layer. Remove the cancel marker issue causing the test failure. Sab picks the agent CLI at dispatch time via GDDP_LOCAL_SUBPROCESS_ARGV.",
      "skillName": "runtime-worker",
      "preconditions": [
        "scripts/local_agent_executor.py exists (commit 3092206, 200+ lines, over-engineered)",
        "scripts/canary_local_executor.py exists as reference for minimal shape",
        "test_local_subprocess_cancel_best_effort_survives_reinstantiation is failing",
        "Agent wrappers available (grkbg, cdxbg, pibg) or direct agent CLIs (grok, codex, claude)"
      ],
      "expectedBehavior": [
        "Wrapper is minimal: worktree add, pipe packet to agent, git diff to stdout, worktree remove",
        "No prompt formatting or constraint decomposition (agent reads raw JSON)",
        "No DB path plumbing or read-only enforcement (agent can figure out paths)",
        "No redundant isolation layer (worktree IS the isolation)",
        "Failing cancel test fixed (error message contains 'cancel' after adapter.cancel())",
        "All tests pass"
      ],
      "fulfills": [
        "VAL-WRAPPER-001",
        "VAL-WRAPPER-002",
        "VAL-WRAPPER-003",
        "VAL-WRAPPER-004",
        "VAL-WRAPPER-005",
        "VAL-WRAPPER-006",
        "VAL-WRAPPER-007",
        "VAL-WRAPPER-008",
        "VAL-WRAPPER-009"
      ],
      "milestone": "evidence-archive-and-wrapper",
      "status": "completed",
      "workerSessionIds": [
        "f8e4934b-bda6-4bc2-b25f-b2c6df2ca94d"
      ],
      "currentWorkerSessionId": null,
      "completedWorkerSessionId": null
    },
    {
      "id": "preflight-gate",
      "description": "Reproduce the evaluator's suite-green result from the 2026-07-24 receipt. Run pytest inside an evaluator-style worktree. Explain the '4 failed, 360 passed' result. If environmental (missing .venv/bin/python in worktrees), report to Sab before dispatch. Do not fix the evaluator environment in this mission. This gate blocks Milestone 2.",
      "skillName": "runtime-worker",
      "preconditions": [
        "2026-07-24 receipt exists with suite-green criterion showing 4 failed/360 passed",
        "Python 3.11+ available"
      ],
      "expectedBehavior": [
        "pytest run in evaluator-style worktree reproduces or explains the 4 failed/360 passed result",
        "Root cause identified as environmental or code-related",
        "If environmental, reported to Sab before dispatch proceeds",
        "Evaluator environment not modified by this mission"
      ],
      "fulfills": [
        "VAL-PREFLIGHT-001",
        "VAL-PREFLIGHT-002",
        "VAL-PREFLIGHT-003"
      ],
      "milestone": "evidence-archive-and-wrapper",
      "status": "completed",
      "workerSessionIds": [
        "21596971-2fcd-44e9-a891-5988818bf250",
        "ae170fad-957e-445d-8256-c107b42fcfd6"
      ],
      "currentWorkerSessionId": null,
      "completedWorkerSessionId": null
    },
    {
      "id": "scrutiny-validator-evidence-archive-and-wrapper",
      "description": "Scrutiny validation for milestone \"evidence-archive-and-wrapper\". Runs test suite, typecheck, and lint. Spawns review subagents for each completed feature. Synthesizes findings. Always returns to orchestrator.",
      "skillName": "scrutiny-validator",
      "preconditions": [
        "All implementation features for milestone \"evidence-archive-and-wrapper\" are complete"
      ],
      "expectedBehavior": [
        "Validators pass (test, typecheck, lint)",
        "Review subagents spawned for each feature",
        "Findings synthesized into scrutiny report"
      ],
      "milestone": "evidence-archive-and-wrapper",
      "status": "completed",
      "workerSessionIds": [
        "42b8e3ba-1416-4341-b1ba-daef7bc5cab5"
      ],
      "currentWorkerSessionId": null,
      "completedWorkerSessionId": null
    }
  ]
}```

### `state.json`

Schema: `{missionId:string, state:planning|awaiting_input|initializing|running|paused|orchestrator_turn|completed, workingDirectory:string, createdAt:ISO8601, updatedAt:ISO8601, lastReviewedHandoffCount?:integer}`.

```json
{
  "missionId": "mis_b0cadc77",
  "state": "paused",
  "workingDirectory": "/Users/sab-mini/repos/gddp-runtime",
  "createdAt": "2026-07-24T01:26:12.943Z",
  "updatedAt": "2026-07-24T07:27:20.378Z",
  "lastReviewedHandoffCount": 7
}```

### One full handoff

Top-level schema: `{timestamp, workerSessionId, featureId, milestone?, commitId?, repoPath?, successState:success|partial|failure, returnToOrchestrator:boolean, handoff}`. `handoff` has `salientSummary`, `whatWasImplemented`, `whatWasLeftUndone`, `verification`, `tests`, `discoveredIssues`, and optional `skillFeedback`. Requested-field audit across all seven files: `commitId` and `repoPath` occur only in two commit-bearing success handoffs; `successState`, `featureId`, `workerSessionId`, `returnToOrchestrator` occur in all; top-level `sessionId` is absent from all; all six requested nested semantic fields occur in all seven.

```json
{
  "timestamp": "2026-07-24T06:45:05.333Z",
  "workerSessionId": "f8e4934b-bda6-4bc2-b25f-b2c6df2ca94d",
  "featureId": "simplify-executor-to-worktree-only",
  "milestone": "evidence-archive-and-wrapper",
  "commitId": "35b41a1fe6855b211a30eacee103de7bc34bdadd",
  "repoPath": "/Users/sab-mini/repos/gddp-runtime",
  "successState": "success",
  "returnToOrchestrator": false,
  "handoff": {
    "salientSummary": "Reduced the local executor to raw packet transport through a detached worktree, propagated the pinned base SHA in NodePacket, and removed the racy cancel.signalled marker. The repository is clean at commit 35b41a1, with all 379 tests passing.",
    "whatWasImplemented": "Replaced prompt construction, DB path plumbing, pinned Grok configuration, and fallback base resolution with a minimal wrapper that validates expected_base_commit_sha, creates a detached worktree, pipes the unchanged packet to the operator-selected agent argv, emits the staged binary diff, and always removes the worktree. Added dispatch and retry propagation for expected_base_commit_sha, and made cancellation durability rely on cancel.requested so reinstantiated adapters report a cancellation error without the racy cancel.signalled marker.",
    "whatWasLeftUndone": "",
    "verification": {
      "commandsRun": [
        {
          "command": "python3 -m pytest -q scripts/test_local_agent_executor.py scripts/adapters/test_executor_contract.py scripts/runtime/heartbeat/test_runner.py scripts/runtime/heartbeat/test_parallel_dispatch.py scripts/runtime/heartbeat/test_executor_sessions.py",
          "exitCode": 0,
          "observation": "71 focused executor, adapter, packet, runner, retry, and cancellation tests passed."
        },
        {
          "command": "python3 -m pytest -q",
          "exitCode": 0,
          "observation": "Full project suite completed with 379 passed in 5.63 seconds."
        },
        {
          "command": "echo \"No typecheck configured (per AGENTS.md)\"",
          "exitCode": 0,
          "observation": "Manifest confirms no typechecker is configured."
        },
        {
          "command": "echo \"No lint configured (per AGENTS.md)\"",
          "exitCode": 0,
          "observation": "Manifest confirms no linter is configured."
        },
        {
          "command": "set -o pipefail; <raw packet> | python3 scripts/local_agent_executor.py -- python3 -c '<probe agent>'",
          "exitCode": 0,
          "observation": "End-to-end CLI probe emitted only a unified diff containing .gddp-wrapper-probe.txt and raw-probe-token, left no live-tree file, and left no gddp-agent-wt worktree."
        },
        {
          "command": "git diff HEAD^ HEAD --check",
          "exitCode": 0,
          "observation": "Committed patch contains no whitespace errors."
        },
        {
          "command": "git status --porcelain",
          "exitCode": 0,
          "observation": "Working tree is clean after commit and post-commit hook completion."
        }
      ]
    },
    "tests": {
      "added": [],
      "updated": [
        "scripts/test_local_agent_executor.py",
        "scripts/adapters/test_executor_contract.py",
        "scripts/runtime/heartbeat/test_executor_sessions.py"
      ],
      "coverage": "Covers malformed and missing base SHA packets, exact raw packet forwarding, operator-selected argv, detached expected-base worktrees, diff-only stdout, stderr routing, cleanup after agent exceptions, partial diff salvage on nonzero exit, initial and retry base-SHA propagation, and durable cancellation after adapter reinstantiation without cancel.signalled."
    },
    "discoveredIssues": [],
    "skillFeedback": {
      "followedProcedure": false,
      "deviations": [
        {
          "step": "Wrapper procedure steps 4-5: add DB read-only prompt plumbing and prompt-construction tests",
          "whatIDidInstead": "Removed all prompt construction and DB path plumbing, then rewrote tests around raw JSON forwarding and worktree-only transport.",
          "why": "The assigned feature explicitly superseded those older runtime-worker instructions and required no prompt formatting, no DB path plumbing, and no constraint decomposition."
        }
      ],
      "suggestedChanges": [
        "Update the runtime-worker wrapper procedure to distinguish the new worktree-only transport from the superseded prompt-building wrapper design."
      ]
    }
  }
}
```

Filename convention is `<UTC timestamp>__<sanitized featureId>__<sanitized workerSessionId>.json`: (1) `2026-07-24T06-45-05-333Z` is `timestamp`, with `:` and `.` changed to `-`; (2) double underscore is the delimiter; (3) `simplify-executor-to-worktree-only` is `featureId`; (4) the UUID is `workerSessionId`; (5) `.json` is the serialization. Embedded `ensureWorkerHandoffJson` constructs exactly ```${fuL(timestamp)}__${hF0(featureId)}__${hF0(workerSessionId)}.json``` and returns without rewriting if the path exists (binary around byte 68,337,000).

### `validation-state.json`

Schema: `{assertions: Record<assertionId,{status:pending|passed|failed|blocked, validatedAtMilestone?:string, issues?:string}>}` (the observed file contains pending/passed/failed). Full example:

```json
{
  "assertions": {
    "VAL-ARCHIVE-001": { "status": "passed", "validatedAtMilestone": "evidence-archive-and-wrapper" },
    "VAL-ARCHIVE-002": { "status": "passed", "validatedAtMilestone": "evidence-archive-and-wrapper" },
    "VAL-ARCHIVE-003": { "status": "passed", "validatedAtMilestone": "evidence-archive-and-wrapper" },
    "VAL-ARCHIVE-004": { "status": "passed", "validatedAtMilestone": "evidence-archive-and-wrapper" },
    "VAL-WRAPPER-001": { "status": "failed", "issues": "Required packet fields are not enforced; contract selector is absent." },
    "VAL-WRAPPER-002": { "status": "failed", "issues": "The minimal wrapper pipes raw packet JSON and has no contract-required build_prompt interface." },
    "VAL-WRAPPER-003": { "status": "failed", "issues": "Only packet expected_base_commit_sha is accepted; required environment and HEAD fallbacks are absent." },
    "VAL-WRAPPER-004": { "status": "passed", "validatedAtMilestone": "evidence-archive-and-wrapper" },
    "VAL-WRAPPER-005": { "status": "failed", "issues": "Contract prompt-file exclusion is absent; emit_diff stages all worktree changes." },
    "VAL-WRAPPER-006": { "status": "passed", "validatedAtMilestone": "evidence-archive-and-wrapper" },
    "VAL-WRAPPER-007": { "status": "failed", "issues": "The contract --dry-prompt and absolute read-only DB guidance are unsupported." },
    "VAL-WRAPPER-008": { "status": "failed", "issues": "No wrapper DB writes were found, but required prompt rules and decision.md routing are absent." },
    "VAL-WRAPPER-009": { "status": "failed", "issues": "The contract pinned agent argv and GDDP_AGENT_ARGV JSON override are absent." },
    "VAL-PREFLIGHT-001": { "status": "passed", "validatedAtMilestone": "evidence-archive-and-wrapper" },
    "VAL-PREFLIGHT-002": { "status": "passed", "validatedAtMilestone": "evidence-archive-and-wrapper" },
    "VAL-PREFLIGHT-003": { "status": "passed", "validatedAtMilestone": "evidence-archive-and-wrapper" },
    "VAL-DISPATCH-001": { "status": "pending" },
    "VAL-DISPATCH-002": { "status": "pending" },
    "VAL-DISPATCH-003": { "status": "pending" },
    "VAL-DISPATCH-004": { "status": "pending" },
    "VAL-DISPATCH-005": { "status": "pending" },
    "VAL-DISPATCH-006": { "status": "pending" },
    "VAL-DISPATCH-007": { "status": "pending" },
    "VAL-DISPATCH-008": { "status": "pending" },
    "VAL-DISPATCH-009": { "status": "pending" },
    "VAL-VERIFY-001": { "status": "pending" },
    "VAL-VERIFY-002": { "status": "pending" },
    "VAL-VERIFY-003": { "status": "pending" },
    "VAL-VERIFY-004": { "status": "pending" },
    "VAL-VERIFY-005": { "status": "pending" },
    "VAL-VERIFY-006": { "status": "pending" },
    "VAL-XFLOW-001": { "status": "pending" },
    "VAL-XFLOW-002": { "status": "pending" }
  }
}
```

### Scrutiny synthesis

Schema is directly visible in this complete example: milestone, round, status, command validator results, review counts, blocking issues, applied/suggested guidance updates, rejected observations, previous round.

```json
{
  "milestone": "evidence-archive-and-wrapper",
  "round": 1,
  "status": "pass",
  "validatorsRun": {
    "test": {
      "passed": true,
      "command": "python3 -m pytest -q",
      "exitCode": 0
    },
    "typecheck": {
      "passed": true,
      "command": "echo \"No typecheck configured (per AGENTS.md)\"",
      "exitCode": 0
    },
    "lint": {
      "passed": true,
      "command": "echo \"No lint configured (per AGENTS.md)\"",
      "exitCode": 0
    }
  },
  "reviewsSummary": {
    "total": 3,
    "passed": 3,
    "failed": 0,
    "failedFeatures": []
  },
  "blockingIssues": [],
  "appliedUpdates": [
    {
      "target": "library/environment.md",
      "description": "Documented evaluator-worktree interpreter behavior and the requirement to unset inherited GDDP_EXECUTOR_OVERRIDE before evaluator-style adapter tests.",
      "sourceFeature": "preflight-gate"
    }
  ],
  "suggestedGuidanceUpdates": [
    {
      "target": "skills/runtime-worker/SKILL.md",
      "suggestion": "Replace obsolete prompt-building and database-plumbing wrapper instructions with the approved worktree-only wrapper contract.",
      "evidence": "Review of simplify-executor-to-worktree-only found the implemented raw-packet transport intentionally contradicts the existing procedural steps.",
      "isSystemic": true
    },
    {
      "target": "architecture.md and validation-contract.md",
      "suggestion": "Reconcile wrapper descriptions and assertions with the approved minimal worktree-only executor contract.",
      "evidence": "The architecture and VAL-WRAPPER-001..009 still require prompt construction, database instructions, argv behavior, and fallback resolution that the completed feature intentionally removed.",
      "isSystemic": true
    },
    {
      "target": "skills/runtime-worker/SKILL.md",
      "suggestion": "For evaluator pre-flight runs, require inspection and sanitization of inherited GDDP_* environment variables, especially GDDP_EXECUTOR_OVERRIDE.",
      "evidence": "Preflight review established that the exact historical four failures were caused by inherited override leakage; a clean environment passed 364/364.",
      "isSystemic": true
    },
    {
      "target": "skills/runtime-worker/SKILL.md",
      "suggestion": "Document whether a single retry is permitted for the known intermittent cancellation-status test race.",
      "evidence": "Archive worker observed 381 passed/1 failed on first run and 382 passed on immediate rerun.",
      "isSystemic": false
    },
    {
      "target": "mission init.sh",
      "suggestion": "Make the mission init script executable or update worker startup instructions to invoke it explicitly with /bin/bash.",
      "evidence": "Archive worker observed direct execution exit 126 and succeeded only via /bin/bash.",
      "isSystemic": false
    }
  ],
  "rejectedObservations": [],
  "previousRound": null
}
```

### User-testing synthesis

Schema is directly visible in this complete example: milestone, round, status, assertion summary and IDs/reasons, applied updates, flow-report paths, salient summary, previous round.

```json
{
  "milestone": "evidence-archive-and-wrapper",
  "round": 1,
  "status": "fail",
  "assertionsSummary": {
    "total": 16,
    "passed": 9,
    "failed": 7,
    "blocked": 0
  },
  "passedAssertions": [
    "VAL-ARCHIVE-001",
    "VAL-ARCHIVE-002",
    "VAL-ARCHIVE-003",
    "VAL-ARCHIVE-004",
    "VAL-WRAPPER-004",
    "VAL-WRAPPER-006",
    "VAL-PREFLIGHT-001",
    "VAL-PREFLIGHT-002",
    "VAL-PREFLIGHT-003"
  ],
  "failedAssertions": [
    {
      "id": "VAL-WRAPPER-001",
      "reason": "Required packet fields are not enforced and the contract test selector is absent."
    },
    {
      "id": "VAL-WRAPPER-002",
      "reason": "The minimal wrapper pipes raw packet JSON and has no contract-required build_prompt interface."
    },
    {
      "id": "VAL-WRAPPER-003",
      "reason": "Only packet expected_base_commit_sha is accepted; environment and HEAD fallbacks are absent."
    },
    {
      "id": "VAL-WRAPPER-005",
      "reason": "Contract prompt-file exclusion is absent; emit_diff stages all worktree changes."
    },
    {
      "id": "VAL-WRAPPER-007",
      "reason": "The contract --dry-prompt and absolute read-only DB guidance are unsupported."
    },
    {
      "id": "VAL-WRAPPER-008",
      "reason": "No wrapper DB writes were found, but required prompt rules and decision.md routing are absent."
    },
    {
      "id": "VAL-WRAPPER-009",
      "reason": "The contract pinned agent argv and GDDP_AGENT_ARGV JSON override are absent."
    }
  ],
  "blockedAssertions": [],
  "appliedUpdates": [
    {
      "target": "user-testing.md",
      "description": "Added serial CLI isolation guidance for the shared SQLite and git evidence surface.",
      "source": "setup"
    },
    {
      "target": "user-testing.md",
      "description": "Recorded nested receipt lane fields, clean preflight override handling, and the wrapper-contract drift discovered by flow validation.",
      "source": "flow-report"
    }
  ],
  "flowReports": [
    "flows/archive.json",
    "flows/wrapper.json",
    "flows/preflight.json"
  ],
  "salientSummary": "Archive evidence and preflight assertions passed. Seven wrapper assertions fail because the current intentionally minimal raw-packet wrapper no longer matches the older validation contract's prompt, DB-guidance, fallback, dry-prompt, and pinned-argv requirements. Repository suite remains green at 379 passed.",
  "previousRound": null
}
```

## 3. `progress_log.jsonl`

**Verdict: an external tailer can reconstruct a per-execution tuple in real time only partially: feature/session/start/end/outcome are present, commit is optional, and there is no attempt ID or validator synthesis payload — confidence: high**

Across all mission directories, only `3efe69ab...` had a progress log. Counts:

```text
 5 handoff_items_dismissed
 1 milestone_validation_triggered
 1 mission_accepted
 3 mission_paused
 2 mission_resumed
 8 mission_run_started
 7 worker_completed
 2 worker_paused
 7 worker_selected_feature
 7 worker_started
```

Observed event schemas and one full real line each:

- `mission_accepted {timestamp,type,title}` — line 1: `{"timestamp":"2026-07-24T05:46:24.285Z","type":"mission_accepted","title":"Node 2 Real Direct Executor Round Trip"}`
- `mission_run_started {timestamp,type,message?}` — line 2: `{"timestamp":"2026-07-24T05:54:54.164Z","type":"mission_run_started","message":"Starting Node 2 Real Direct Executor Round Trip mission. Note: some M1 artifacts may already exist in .handoffs/artifacts/053-node2-real-round-trip/ (receipts and patch were archived earlier). Check current state before redoing work. The gddp-config edit (local_subprocess as first allowed_execution_modes entry on job-state-consistency) is already applied but uncommitted."}`
- `worker_selected_feature {timestamp,type,workerSessionId,featureId}` — line 3: `{"timestamp":"2026-07-24T05:54:56.006Z","type":"worker_selected_feature","workerSessionId":"498a1331-ffed-435f-b768-d4ec017c97b1","featureId":"archive-surviving-evidence"}`
- `worker_started {timestamp,type,workerSessionId,spawnId,featureId?}` — line 4: `{"timestamp":"2026-07-24T05:54:56.007Z","type":"worker_started","workerSessionId":"498a1331-ffed-435f-b768-d4ec017c97b1","spawnId":"worker_721aa2f4","featureId":"archive-surviving-evidence"}`
- `worker_completed {timestamp,type,workerSessionId,featureId,successState,returnToOrchestrator,commitId?,repoPath?,exitCode,validatorsPassed?,handoff?}` — line 5 is the full first handoff embedded in the log; its top-level fields are `timestamp=2026-07-24T05:56:17.607Z`, worker `498a...`, feature `archive-surviving-evidence`, `successState=failure`, `returnToOrchestrator=true`, `exitCode=0`, `validatorsPassed=false`, no commit/repo, plus the full handoff object. The complete same payload is `/handoffs/2026-07-24T05-56-17-607Z__...json`.
- `worker_paused {timestamp,type,workerSessionId,featureId?}` — line 15: `{"timestamp":"2026-07-24T06:31:20.915Z","type":"worker_paused","workerSessionId":"f8e4934b-bda6-4bc2-b25f-b2c6df2ca94d","featureId":"simplify-executor-to-worktree-only"}`
- `mission_paused {timestamp,type,pauseReason?}` — line 16: `{"timestamp":"2026-07-24T06:31:20.924Z","type":"mission_paused"}`
- `mission_resumed {timestamp,type,resumeWorkerSessionId?}` — line 17: `{"timestamp":"2026-07-24T06:33:41.686Z","type":"mission_resumed","resumeWorkerSessionId":"f8e4934b-bda6-4bc2-b25f-b2c6df2ca94d"}`
- `handoff_items_dismissed {timestamp,type,dismissals?}` — line 6: `{"timestamp":"2026-07-24T06:10:03.988Z","type":"handoff_items_dismissed","dismissals":[{"type":"discovered_issue","sourceFeatureId":"archive-surviving-evidence","summary":"init.sh not executable (permission denied on direct invocation)","justification":"Already fixed: chmod +x applied to init.sh"},{"type":"discovered_issue","sourceFeatureId":"archive-surviving-evidence","summary":"test_local_subprocess_cancel_best_effort_survives_reinstantiation failing - error message says 'exited with code -15' not 'cancel'","justification":"Folded into the simplify-executor-to-worktree-only feature which explicitly requires fixing this test"}]}`
- `milestone_validation_triggered {timestamp,type,milestone,featureId}` — line 32: `{"timestamp":"2026-07-24T07:01:37.987Z","type":"milestone_validation_triggered","milestone":"evidence-archive-and-wrapper","featureId":"scrutiny-validator-evidence-archive-and-wrapper"}`

The installed binary additionally supports an unobserved `worker_failed` schema: `{timestamp,type:"worker_failed",workerSessionId?,spawnId,exitCode?,reason,failureReason?}`. Exact Zod union is at binary byte 62,914,074.

Append behavior is directly implemented as `appendFile(progressLogPath, line)`, falling back to `writeFile` only if append throws (binary around byte 68,337,000). Therefore normal operation is append-only; there is no sequence number or hash chain, and the exceptional fallback means tamper-evidence is not guaranteed.

Tuple verdict:
- `featureId`: yes, selected/started/completed.
- `workerSessionId`: yes.
- `startedAt`: yes, `worker_started.timestamp` (or selected time one millisecond earlier in this specimen).
- `endedAt`: yes for completion/failure via `worker_completed.timestamp`; pause is separately visible.
- `outcome`: yes, `successState` plus `returnToOrchestrator`, `exitCode`, optional `validatorsPassed`.
- `commitId`: **partial**; only 2/7 completions carry one.
- validator result: only optional boolean `validatorsPassed`; synthesis details are in separate validation files.
- exact attempt identity: **no**; `spawnId` and worker session identify an execution, but no `attempt`, `retryOf`, or idempotency key exists.

## 4. Write-once versus mutable

**Verdict: hash individual completed handoffs, completed JSONL lines, and Git commits; do not hash whole mutable mission files as terminal receipts until a separately observed terminal/abandonment condition — confidence: high**

| Class | Behavior/evidence | Safe-to-hash event |
|---|---|---|
| `handoffs/<timestamp>__<feature>__<session>.json` | write once: writer checks existence and returns; filename contains immutable identity | file appears, parses, and matching `worker_completed` line is newline-terminated |
| individual `progress_log.jsonl` line | append-only in nominal writer; prefix line does not change | complete newline observed; for attempt terminal evidence require `worker_completed`/`worker_failed` |
| whole `progress_log.jsonl` | grows across resumes; mtime tracks later state | only after `state=completed` **and** orchestrator `SessionEnd`, or explicit human abandonment; no single observed log event proves closure |
| individual `worker-transcripts.jsonl` record | append-only writer, one skeleton per completion | complete newline after matching completion; useful context, not authoritative result |
| whole `worker-transcripts.jsonl` | grows as workers finish | same mission-terminal trigger as whole progress log |
| `features.json` | overwritten by `writeFile`; statuses/session arrays mutate (`writeFeatures` embedded at byte 68,337,064) | only a snapshot, never a standalone receipt; terminal mission closure makes its whole-file hash archival |
| `state.json` | overwritten by `writeState`; every write replaces `updatedAt` | snapshot only; hash after `completed` + orchestrator `SessionEnd`, or human-declared abandonment |
| `validation-state.json` | rewritten as assertions are validated/revalidated | after relevant validator completion **and** no pending rerun; strongest only at terminal mission closure |
| validation synthesis/reviews/flows | per-path round data can be replaced on rerun; no write-once guard observed | hash content referenced by a completed validator handoff, then bind hash into external receipt; do not assume future immutability |
| `evidence/**` | worker-created, no runtime immutability contract | only after content is committed and commit object verified |
| `mission.md`, `AGENTS.md`, `architecture.md`, `library/**`, `skills/**`, `validation-contract.md` | planning/shared-state files; explicitly editable mid-mission | archival only at terminal closure; not attempt receipts |
| `working_directory.txt` | written at creation, but generic writer can overwrite | mission identity metadata, not receipt |
| `model-settings.json`, `runtime-custom-models.json` | overwritten by runtime refresh/write | snapshot only |
| Git commit object | content-addressed immutable object | `git cat-file -t <commit> == commit`; separately record reachable ref if durability matters |

Mtime/timestamp correlation: handoff mtimes equal embedded completion timestamps to the second; progress/state share final 07:27:20 update; features/worker-transcripts share final worker completion 07:20:42. This is consistent with in-place feature rewrites and JSONL append, not proof by itself.

## Identity graph

**Verdict: the strongest join is mission-directory UUID → `sessions-index`/worker transcript `callingSessionId` → worker UUID → feature/progress/handoff; `state.missionId` is a telemetry/runtime tag, not the filesystem key — confidence: high**

| Identifier | Where it lives | Joins to | Stable across restart? | Evidence |
|---|---|---|---|---|
| mission directory/session UUID `3efe69ab-...` | mission path; orchestrator session filename; sessions index | all mission artifacts; worker `callingSessionId`; mission-session tag | yes in persisted artifacts; observed across pause/resume | `sessions-index.json#entries[sessionId=3efe...]`; worker transcript first records |
| internal mission ID `mis_b0cadc77` | `state.json#/missionId`; logs telemetry tags | runtime logs/metrics for the directory-backed mission | observed stable through run; restart behavior **INFERRED** stable because persisted | `state.json:2`; `droid-log-single.log.2026-07-24` tags |
| feature ID | `features.json#/features/*/id`; progress; handoff filename/body; validation review names | execution history and validation artifacts | yes as mission-authored identifier, unless orchestrator edits scope | e.g. `preflight-gate` in all surfaces |
| worker session UUID | feature session arrays; progress; handoff; session filename/index; hook payload | exact worker transcript and feature execution | yes; persisted UUID | `f8e4934b...` across all listed surfaces |
| `spawnId` `worker_721aa2f4` | `worker_started` progress line | dispatch event only | unknown across resume; resumed path uses `resume_<session>` in embedded code | progress line 4; binary resume error path |
| task invocation UUID | `task-invocations.json#/invocations/*/taskInvocationId` | parent/child subagent sessions and tool-use | yes in registry | full record schema below |
| child subagent UUID | task invocation `childSessionId`; session file/index | validator/reviewer/explorer transcript | yes | six scrutiny + six user-testing task records |
| host/computer IDs | session index/config/log tags | machine identity | persisted on host | `host.json`, `computer.json` |

Concrete graph for the feature worker `f8e4934b...`:

```text
~/.factory/missions/3efe69ab.../
  state.missionId = mis_b0cadc77
  features[id=simplify...].workerSessionIds = [f8e4934b...]
  progress worker_started/completed(featureId=simplify..., workerSessionId=f8e4934b...)
  handoff ...__simplify...__f8e4934b....json
      commitId = 35b41a1..., repoPath = /Users/sab-mini/repos/gddp-runtime
~/.factory/sessions/.../f8e4934b....jsonl
  first record callingSessionId = 3efe69ab...
~/.factory/sessions-index.json entry
  callingSessionId = 3efe69ab...
  tags mission-session {role:worker, missionId:3efe69ab...}
~/.factory/task-invocations.json
  five records with parentSessionId=f8e4934b... join its review subagents
```

`task-invocations.json` complete record schema observed: `{taskInvocationId,createdAt,parentSessionId,parentToolUseId,childSessionId,runInBackground,status,subagentType,description,cwd,promptMessageId?,completionEvidenceVersion?,updatedAt,completionReason?,toolUseCount?,durationMs?}`. Important correction to the initial hypothesis: mission workers are **not** represented as child records of the mission in this registry. Records whose `parentSessionId` equals the mission UUID are ordinary Task subagents invoked by the orchestrator. Mission feature workers join directly through progress/features/sessions-index. Once a mission worker invokes Task, it appears as `parentSessionId` (5 records for `f8e...`, 6 each for scrutiny and user-testing validators). Archive workers and the first preflight worker have zero task records.

Session storage: `~/.factory/sessions/<cwd-sanitized>/<sessionUUID>.jsonl`, plus `<sessionUUID>.settings.json` and occasional `.bak`. The JSONL first record is `session_start` with `{type,id,title,owner,callingSessionId?,version,cwd,hostId,isSessionTitleManuallySet,sessionTitleAutoStage?}`; subsequent records are `{type:"message",id,timestamp,message,parentId}` where `message` contains role/content and model/tool/hook metadata. `sessions-index.json` v2 stores summary entries with `sessionId,hostId,mtime,settingsMtime,title,cwd,messagesCount,callingSessionId?,callingToolUseId?,tags`. Worker transcripts are independently retrievable by worker UUID; the seven full worker JSONLs exist separately, while mission `worker-transcripts.jsonl` is only a condensed skeleton.

## 6. Commit mapping

**Verdict: only 2/7 handoffs carry commits; a handoff does not reliably declare the feature's exact base, and consecutive feature handoffs do not provide a complete boundary chain — confidence: high**

All handoff commit mappings across every mission directory (only `3efe...` has handoffs):

| Feature/session | success | commit/repo |
|---|---|---|
| archive / `498a...` | failure | absent |
| archive / `ac4d...` | success | `31f549d83053148560d7776ff7a0f79b5592c6da`, gddp-runtime |
| simplify / `f8e...` | success | `35b41a1fe6855b211a30eacee103de7bc34bdadd`, gddp-runtime |
| preflight / `2159...` | partial | absent |
| preflight / `ae17...` | success | absent |
| scrutiny validator / `42b8...` | success | absent |
| user-testing validator / `2c61...` | failure | absent |

Read-only Git verification:

```text
$ git show -s --format='commit=%H parents=%P subject=%s' 31f549d...
commit=31f549d83053148560d7776ff7a0f79b5592c6da parents=2072d33b90e9a6e7ff1ef5a5cfe35e9da5d519d2 subject=docs: archive surviving canary evidence for Node 2 real round trip (053)
$ git show -s ... 35b41a1...
commit=35b41a1fe6855b211a30eacee103de7bc34bdadd parents=3092206d28f06d43677db9a0947b23c09fe033f9 subject=fix(executor): reduce local wrapper to worktree transport
$ git log --reverse 31f549d^..35b41a1
31f549d... parent 2072d33... docs: archive surviving canary evidence...
3092206... parent 31f549d... feat: local_agent_executor wrapper...
35b41a1... parent 3092206... fix(executor): reduce local wrapper...
$ git merge-base --is-ancestor 31f549d 35b41a1; echo $?
0
```

Both commits exist (`git cat-file -t` returned `commit`) and are reachable from local `main`, `origin/main`, and many later refs. No commit-bearing handoff is orphaned/unreachable.

Three concrete handoff demonstrations:
1. Archive success points to `31f549d`, whose parent is `2072d33`. However its text says it *verified* already-present artifacts/commit; the handoff does not prove `2072d33..31f549d` was authored by that worker.
2. Simplify success points to `35b41a1`, whose immediate parent is `3092206`, not the prior feature handoff `31f549d`. The prior result is an ancestor two commits back, so “base = prior feature result” would incorrectly include intermediate `3092206`.
3. Preflight success `ae170fad...` has no commit or repo path, so no Git boundary exists at all despite a successful feature handoff.

Thus `result^..result` is the exact boundary of a commit object, **not necessarily the feature boundary**. Exact feature base→result requires an explicit base SHA in the handoff/progress event; it is absent.

Isolation: `working_directory.txt` is the live repo root, and commits are on `main`/`origin/main`, not mission-named branches. Workers did use temporary detached worktrees internally (preflight handoff commands and architecture), but mission output was committed in-place/on main rather than isolated onto a per-feature branch. The chain is linear for the two recorded commits, but incomplete as a feature-result ledger.

## 7. Retry versus duplicate

**Verdict: repeated features are represented as separate worker executions with new session UUIDs, but there is no explicit `attempt`, `retryOf`, or duplicate-completion discriminator — confidence: high**

Archive pair:
- attempt-like execution 1: `498a...`, start 05:54:56Z, end 05:56:17Z, `failure`, no commit/repo, returned to orchestrator; startup/test gate failed and no implementation occurred.
- execution 2: `ac4d...`, start 06:22:04Z, end 06:27:36Z, `success`, commit `31f549d`, returned to orchestrator; verified durable archive and tests.

Preflight pair:
- execution 1: `2159...`, start 06:45:07Z, end 06:49:53Z, `partial`, no commit, returned to orchestrator; established environmental evidence but awaited Sab's decision.
- execution 2: `ae17...`, start 06:57:02Z, end 07:01:37Z, `success`, no commit; completed clean/contaminated comparison after proceed decision.

Each pair differs in timestamp, worker session, outcome, handoff content, verification, and (archive only) commit. `features.json#/features[id=...]/workerSessionIds` preserves both UUIDs. The event stream shows a fresh `worker_selected_feature` + `worker_started` for each. This proves separate executions, not duplicated file writes.

What artifacts cannot answer: whether the second execution was a “retry,” intentional re-run after human guidance, or duplicate assignment. There is no semantic relation. A duplicate `worker_completed` append for the same worker could be noticed by identical `(featureId,workerSessionId)` but is not prevented by a progress-log idempotency key; handoff creation would collapse to the same filename because it refuses overwrite. Duplicate quarantine should key on `(missionDirUUID, featureId, workerSessionId)` and retain all completion-line hashes/timestamps, while classifying cross-session repeats as “new execution, retry relation unknown.”

## 8. State and status enums

**Verdict: observed values are a strict subset of binary-supported enums; `cancelled` is a supported feature status, but no per-running-feature cancellation API/event was found — confidence: high for enum, medium for control conclusion**

Observed across all mission dirs:
- mission `state`: `planning` (3), `paused` (1).
- feature `status`: `pending`, `completed` (only richest mission had features).

Binary enum inventory verbatim at byte 62,902,944:

```text
MissionState: planning, awaiting_input, initializing, running, paused, orchestrator_turn, completed
FeatureStatus: pending, in_progress, completed, cancelled
SuccessState: success, partial, failure
```

The embedded mission instructions explicitly say pending features can be cancelled rather than deleted and assertions have no cancelled state. No observed progress type records `feature_cancelled`; no daemon method specific to feature cancellation was found. The daemon has `interrupt_session` and `kill_worker_session`, which act on sessions, and mission pause interrupts the current worker. **INFERRED:** cancellation is an orchestrator edit to pending feature state, not an externally exposed running-feature cancellation primitive. Probe 5 settles runtime behavior.

## 9. Isolation: mission-wide versus per-worker

**Verdict: execution is session-isolated but artifact coordination is mission-wide; top-level workers ran sequentially, while validator/reviewer subagents sometimes ran concurrently — confidence: high**

Mission-wide: `state.json`, `features.json`, both JSONLs, planning docs, models, service/init config, library, skills, validation contract/state, milestone validation trees, and evidence tree. Per-worker: one handoff JSON and one full session JSONL/settings pair. Per-feature: feature entry, zero-or-more handoffs/sessions, scrutiny review, and flow/evidence files named for that feature/flow.

Roles from content:
- `AGENTS.md`: hard mission boundaries; planning/orchestrator writer.
- `architecture.md`: planned runtime, wrapper, evidence data flow; planning/orchestrator writer.
- `mission.md`: milestone/feature scope; planning/orchestrator writer.
- `services.yaml`: command catalog and empty service set; planning/orchestrator writer, consumed by workers/validators.
- `init.sh`: clean-state, tests, config access, key availability checks; planning/orchestrator writer, executed by workers.
- `library/environment.md`: shared discovered environment; later amended by scrutiny validation.
- `library/user-testing.md`: serial validation surface and known caveats; user-testing validator updates.
- `skills/runtime-worker/SKILL.md`: work procedure injected into feature workers; planning/orchestrator writer.

Top-level timeline has no overlap: every next `worker_started` follows the previous `worker_completed`, except the same `f8e...` session is paused/resumed. The exact sequence is archive fail → archive success → simplify (pause/resume) → preflight partial → preflight success → scrutiny → user-testing. `task-invocations.json` shows concurrency inside validation: three scrutiny child records share createdAt `1784876585235/6`; later two successful reviews share `1784876761047`; top-level mission workers themselves are sequential.

## 10. Binary inspection

**Verdict: Droid is a signed arm64 Mach-O containing a bundled/minified JavaScript runtime/application; embedded source exposes mission schemas and RPC names but no public per-feature admission method — confidence: high**

`file`: `Mach-O 64-bit executable arm64`; size 118,763,184 bytes; code signed by `Developer ID Application: The San Francisco AI Factory Inc. (SW6TL4V6Q5)`. `head -c 300` showed Mach-O headers and `__jsc_int`; `otool -L` links ICU, resolver, libc++, and libSystem. Embedded paths reference JavaScriptCore/Bun and minified JS, so inspection used read-only byte searches/regex, not execution.

Mission methods/tools found verbatim: `start_mission_run`, `EndFeatureRun`, `DismissHandoffItems`, `ProposeMission`, `InspectMissionReadiness`. Key paths: `features.json`, `state.json`, `progress_log.jsonl`, `handoffs`, `worker-transcripts.jsonl`, `validation-state.json`, validation trees. Worktree handling appears both in `droid exec --worktree` help and mission worker content, but mission runner spawning itself uses `spawnWorkerSession({cwd,baseSessionId,modelId,interactionMode...})`; no mandatory per-feature worktree parameter is visible in that call.

Progress event enum embedded in the mission core: `mission_accepted`, `mission_paused`, `mission_resumed`, `mission_run_started`, `worker_started`, `worker_selected_feature`, `worker_completed`, `worker_failed`, `worker_paused`, `handoff_items_dismissed`, `milestone_validation_triggered`.

Hook enum: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Notification`, `Stop`, `SubagentStop`, `SessionStart`, `SessionEnd`, `PreCompact`.

ACP slash-method inventory extracted verbatim:

```text
authenticate
fs/read_text_file
fs/write_text_file
session/cancel
session/list
session/load
session/new
session/prompt
session/request_permission
session/resume
session/set_config_option
session/set_mode
session/set_model
session/update
terminal/create
terminal/kill
terminal/output
terminal/release
terminal/wait_for_exit
```

Stream JSON-RPC/Droid method inventory extracted from the same literal schemas:

```text
droid.add_mcp_server
droid.add_user_message
droid.ask_user
droid.authenticate_mcp_server
droid.cancel_mcp_auth
droid.change_working_directory
droid.clear_mcp_auth
droid.close_session
droid.compact_session
droid.execute_rewind
droid.fork_session
droid.get_context_breakdown
droid.get_context_stats
droid.get_rewind_info
droid.initialize_session
droid.interrupt_session
droid.kill_worker_session
droid.list_commands
droid.list_mcp_registry
droid.list_mcp_servers
droid.list_mcp_tools
droid.list_skills
droid.list_tools
droid.load_session
droid.remove_mcp_server
droid.rename_session
droid.request_permission
droid.resolve_queued_user_message
droid.session_notification
droid.set_skill_disabled
droid.submit_bug_report
droid.submit_mcp_auth_code
droid.submit_mcp_auth_error
droid.toggle_mcp_server
droid.toggle_mcp_tool
droid.update_session_settings
droid.warmup_cache
notifications/activeFile
notifications/diagnostics
notifications/heartbeat
notifications/openFiles
relay.authenticate
```

The full daemon method inventory is appended programmatically below under task 11. No method named admit/start/assign/cancel feature was found. `start_mission_run` is an orchestrator tool, not a daemon RPC exposed in the daemon method union.

## 11. Daemon and logs

**Verdict: worker spawning and operation are externally observable in logs/sessions, and a broad daemon JSON-RPC API exists; no stable default socket path was observed on disk — confidence: high for observability/API, low for default socket endpoint**

`daemon-stderr.log` repeatedly reports `daemon.start() completed -- ipc transport ready`; filesystem search found no current Unix socket under `~/.factory` or Factory/Droid-named socket under `~/Library`. Help proves configurable `--unix`, `--port`, `--host`, `--listen websocket|ipc`, `--enable-child-ipc`, `--remote-access`, `--parent-pid`, `--liveness-fd`, and `--droid-path`. Therefore transport capability is proven; the actual endpoint used by desktop/factoryd on this host remains unknown.

Logs expose worker spawn/runtime facts: `/Users/sab-mini/.factory/logs/droid-log-single.log.2026-07-24` records worker UUIDs, top-level orchestrator session UUID in tags, internal `missionId=mis_b0cadc77`, `subcommand=exec`, `inputFormat/outputFormat=stream-jsonrpc`, `isStreamJsonRpcWorker=true`, model, and mission-worker session tags. Example line 19 associates worker `ae170fad...` with internal mission ID and stream JSON-RPC execution. Line 29 records its tags including `{role:"worker",missionId:"3efe69ab..."}`. Thus external log/session tailing sees worker spawning/operation even without daemon attachment.

Configuration evidence: `settings.json` has `remoteAccessEnabled:true`, mission model settings, trusted folders, and custom models (keys deliberately not reproduced); `settings.local.json` supplies model endpoints/templates; `host.json` and `computer.json` persist host/computer identities; `mcp.json` has one disabled HTTP MCP; `hooks.json` is detailed in task 12. A real log error on 2026-08-05 records JSON-RPC method `daemon.list_git_branches` and protocol-version mismatch/no handler, proving daemon RPC traffic and versioned method handling.

Daemon methods extracted verbatim from embedded literal schemas:

```text
daemon.acknowledge_mission_readiness_warning
daemon.add_marketplace
daemon.add_mcp_server
daemon.add_user_message
daemon.apply_automation_config
daemon.archive_session
daemon.ask_user
daemon.authenticate
daemon.authenticate_mcp_server
daemon.cancel_mcp_auth
daemon.change_working_directory
daemon.check_folder_trust
daemon.checkout_git_branch
daemon.clear_mcp_auth
daemon.close_session
daemon.close_terminal
daemon.compact_session
daemon.connection_status
daemon.create_automation
daemon.create_cron
daemon.create_pr
daemon.create_terminal
daemon.cron.state_changed
daemon.delete_automation
daemon.delete_cron
daemon.delete_custom_model
daemon.execute_rewind
daemon.fork_automation
daemon.fork_session
daemon.generate_semantic_diff
daemon.get_automation_history
daemon.get_automation_visual
daemon.get_context_breakdown
daemon.get_default_settings
daemon.get_git_branch_divergence
daemon.get_git_diff
daemon.get_mcp_config
daemon.get_proxy_token
daemon.get_rewind_info
daemon.get_semantic_diff_cache
daemon.get_session_messages
daemon.get_workspace_file_content
daemon.git_commit
daemon.git_push
daemon.hold_session_crons
daemon.initialize_session
daemon.inspect_mission_readiness
daemon.install_plugin
daemon.install_ssh_key
daemon.interrupt_session
daemon.kill_worker_session
daemon.list_automations
daemon.list_available_plugins
daemon.list_available_sessions
daemon.list_commands
daemon.list_crons
daemon.list_custom_models
daemon.list_files
daemon.list_git_branches
daemon.list_installed_plugins
daemon.list_marketplaces
daemon.list_mcp_registry
daemon.list_mcp_servers
daemon.list_mcp_tools
daemon.list_opened_sessions
daemon.list_skills
daemon.list_terminals
daemon.load_session
daemon.logout
daemon.pause_automation
daemon.pull_url_to_cwd_file
daemon.push_cwd_file_to_url
daemon.relay.get_status
daemon.relay.start
daemon.relay.status_changed
daemon.relay.stop
daemon.remove_marketplace
daemon.remove_mcp_server
daemon.rename_automation
daemon.rename_session
daemon.request_permission
daemon.resize_terminal
daemon.resolve_pull_request_statuses
daemon.resolve_queued_user_message
daemon.resume_automation
daemon.resume_session_crons
daemon.run_automation
daemon.save_semantic_diff_cache
daemon.search_files
daemon.search_sessions
daemon.session_notification
daemon.set_plugin_enabled
daemon.set_skill_disabled
daemon.sf.create_workstream
daemon.sf.delete_workstream
daemon.sf.get_workstream
daemon.sf.list_activities
daemon.sf.list_changes
daemon.sf.list_events
daemon.sf.list_signals
daemon.sf.list_workstreams
daemon.sf.mark_events_read
daemon.sf.mark_events_unread
daemon.sf.resolve_activity_review
daemon.sf.update_workstream
daemon.submit_bug_report
daemon.submit_mcp_auth_code
daemon.submit_mcp_auth_error
daemon.toggle_mcp_server
daemon.toggle_mcp_tool
daemon.trigger_update
daemon.trust_folder
daemon.unarchive_session
daemon.uninstall_plugin
daemon.update_automation
daemon.update_automation_model
daemon.update_automation_privacy
daemon.update_automation_prompt
daemon.update_automation_schedule
daemon.update_cron
daemon.update_marketplace
daemon.update_mcp_config
daemon.update_plugin
daemon.update_session_defaults
daemon.update_session_settings
daemon.upsert_custom_model
daemon.validate_working_directory
daemon.warmup_cache
daemon.write_terminal_data
```

This is an inventory of names embedded in request/notification schemas, not proof every method is handled by the currently running daemon; the observed `daemon.list_git_branches` no-handler error demonstrates version skew can invalidate a name.

## 12. Hooks as an integration point

**Verdict: `SessionStart` and `SessionEnd` definitely fire inside mission worker sessions and are useful evidence-capture triggers, but they do not carry feature ID, outcome, or commit and cannot enforce pre-assignment admission — confidence: high**

Supported binary events: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Notification`, `Stop`, `SubagentStop`, `SessionStart`, `SessionEnd`, `PreCompact`. Configured here: Pre/Post tool (selected write-capable tools), UserPromptSubmit, SessionStart, SessionEnd, Notification. `~/.factory/hooks/` contains `herdr-agent-state.sh`; active commands instead point to `/Users/sab-mini/.local/share/droid-observability/hooks/flight-recorder.sh` (and PostToolUse also git-trailer).

Observed payload schemas from `/Users/sab-mini/.local/share/droid-observability/flight-recorder/20260724.ndjson`:
- common: `session_id,transcript_path,cwd,permission_mode,hook_event_name`.
- `SessionStart`: common + `source`, optional `calling_session_id`, `CLAUDE_ENV_FILE`.
- `SessionEnd`: common + `reason,session_duration_ms,message_count`.
- `PreToolUse`: common + `tool_name,tool_input`.
- `PostToolUse`: common + `tool_name,tool_input,tool_response`.
- `UserPromptSubmit`: common + `prompt,has_images`.
- `Notification`: common + `message,notification_type`.

Concrete proof worker hooks fire: 2026-07-24 recorder entries have `SessionStart.calling_session_id=3efe69ab...` for workers, and the full worker transcript `f8e4934b....jsonl` ends with a `SessionEnd` hook record whose command completed. The same is true for `2159...` and `ae17...`. Therefore hooks are not top-level-only.

Assessment:
- Best event: `SessionEnd` for a post-hoc capture wakeup; payload gives session UUID and transcript path, enough to join to sessions-index/progress/handoff.
- Earlier join event: `SessionStart` gives `calling_session_id`, which identifies the mission parent, but still no feature ID. A tailer must wait for `worker_selected_feature`/`worker_started` to join.
- What it misses: `featureId`, `successState`, `commitId`, validators, `spawnId`, and a guarantee that EndFeatureRun completed before SessionEnd. The terminal handoff/progress line must be read separately.
- `Stop`/`SubagentStop`: binary-supported but not configured/observed in the recorder sample; no evidence they carry mission feature identity.
- Admission: hooks are process/session lifecycle callbacks after spawning (SessionStart) or during/after work. They cannot veto which feature the mission runner selects. PreToolUse can gate tools, not feature assignment.

No environment variables specific to mission identity were observed as a guaranteed hook contract. `CLAUDE_ENV_FILE` is present in SessionStart payload; mission/session identities are JSON stdin fields and log tags. **INFERRED:** relying on ambient `MISSION_ID` env would be unsafe; inspect only the payload and persisted artifacts.

## What GDDP can treat as a terminal receipt

**Verdict: bind a write-once handoff and terminal progress line to an immutable Git object; do not treat mutable feature/state snapshots as receipts — confidence: high**

Ranked:
1. **Git commit object + recorded reachability/ref** — strongest content receipt. Trigger: handoff has commit/repo, `git cat-file -t` says commit, record parents and containing durable ref. Caveat: handoff lacks explicit feature base and commit may predate worker authorship.
2. **Handoff JSON** — strongest Factory per-execution semantic receipt. Trigger: file appears, parses, filename/body/session/feature agree, and matching terminal progress line is present. Hash immediately; embedded writer will not overwrite an existing filename.
3. **Exact newline-terminated `worker_completed`/`worker_failed` progress line** — strongest real-time runtime receipt. Trigger: complete line observed; bind line hash/byte offset to mission UUID. Includes outcome and optional commit, but not explicit attempt relation.
4. **Worker session transcript JSONL + SessionEnd hook payload** — detailed audit evidence. Trigger: SessionEnd observed and transcript last complete line readable. Large/mutable before end; may continue with reminders after EndFeatureRun in some sessions.
5. **Validator synthesis + validation-state snapshot** — milestone evidence. Trigger: corresponding validator handoff completed and hashes captured together. Paths may be overwritten on later validation rounds.
6. **Feature/state snapshots** — context only. Trigger for archival hash: `state=completed` plus orchestrator SessionEnd, or explicit human abandonment. Never use alone as an attempt receipt.

Recommended external receipt envelope:
`{missionDirUUID, internalMissionId, featureId, workerSessionId, startedLineHash, terminalLineHash, handoffPath, handoffSha256, repoPath?, resultCommit?, resultParents?, containingRefs[], capturedAt}`. Leave `baseCommit` null unless separately evidenced; do not infer it from the prior feature.

## Live probes required

**Verdict: five sacrificial-mission probes can settle the remaining re-read, cancellation, hook, closure, and daemon endpoint gaps without touching the live specimen — confidence: high**

1. **Does the runner re-read externally edited feature status / can edits gate assignment?** In a disposable repo and sacrificial mission, before `start_mission_run`, run `cp features.json before.json; python3 -c '...set first pending feature status="cancelled"...'`; then explicitly start the sacrificial mission and tail `progress_log.jsonl`. Exact answer: if the cancelled feature never receives `worker_selected_feature` and the next does, pre-start status is honored. Then repeat while a different worker runs to test mid-run re-read. This must never be run against `160ee18c...`.
2. **What exact status transitions and write mechanics occur?** During one sacrificial feature run: `while true; do stat -f '%i %z %m' features.json state.json; shasum -a 256 features.json state.json; jq '.features[]|{id,status,currentWorkerSessionId,completedWorkerSessionId,workerSessionIds}' features.json; sleep .2; done`. Answer: captures in-progress mutation, inode replacement vs same-file truncation, and when completion/session fields change.
3. **What marks whole-mission closure?** `tail -F progress_log.jsonl` plus `jq .state state.json` and `tail -F <orchestrator-session>.jsonl` through a sacrificial successful mission. Answer: whether a `mission_completed` progress line exists (binary core does not define one), whether only `state=completed` changes, and ordering relative to SessionEnd.
4. **What daemon endpoint and methods are live?** Start a fresh isolated, unauthenticated test daemon only after authorization: `droid daemon --listen ipc --unix /tmp/droid-forensics.sock --enable-child-ipc --parent-pid $$ --droid-path /Users/sab-mini/.local/bin/droid --debug`; use a minimal JSON-RPC client to send initialize/list requests and log responses. Answer: negotiated protocol, authentication requirement, handled method subset, child IPC shape. Do not attach to the user's current daemon.
5. **How does feature cancellation differ from worker termination?** In a sacrificial mission, cancel one pending feature via the supported orchestrator flow, then pause/interrupt one running worker. Capture features/state/progress/hooks. Answer: whether pending cancellation emits any event, whether running cancellation is possible, and whether it yields `cancelled`, `worker_failed`, `worker_paused`, or only mission pause.

Secondary probe: configure temporary `SessionStart`, `Stop`, `SubagentStop`, `SessionEnd` commands in an isolated Factory home and run one sacrificial worker. Compare JSON stdin keys and ordering against EndFeatureRun/handoff creation. This settles currently unobserved Stop/SubagentStop payloads.

## Bottom line

**Verdict: per-node external assignment admission is (c) not exposed; use one mission-level engagement and post-hoc per-node evidence slicing, not per-node admission leases — confidence: high for supported surface, medium for impossibility of all undocumented control paths**

Observed control surfaces can start/resume/pause a mission or interrupt/kill sessions, edit mission planning files, and operate daemon sessions. Observed status surfaces can reconstruct worker/feature executions well after selection and mostly in real time. None exposes a callback or RPC between feature selection and worker spawn where an external GDDP lease can atomically admit/deny that assignment. `SessionStart` is already after spawn; `PreToolUse` gates tools, not assignment. Editing `features.json` is mutable shared state, and nothing observed proves a running mission re-reads an external edit at the required boundary.

Therefore the reliable architecture is: acquire one **mission-level engagement/lease**, observe `progress_log.jsonl` + hooks + sessions index, slice each `(featureId,workerSessionId)` execution into external evidence envelopes, and quarantine duplicates post hoc. Do not claim per-node admission leases. An undocumented workaround based on editing `features.json` remains **INFERRED and unreliable** until live probe 1 proves both re-read timing and atomicity; even if honored, file editing would still lack an atomic compare-and-admit contract.
