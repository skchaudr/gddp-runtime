# N2-7 — direct-executor-round-trip evidence (attempt 1)

Attempt 1 of Node 2: a real local round-trip from `received` event to
`awaiting_review` receipt on `job-state-consistency`, captured as evidence
for the two human decisions below.

Attempt 0 (preserved at `../n2-live-attempt-0/`) failed at the worker
layer: `pi` v0.82.1 emitted a `session_id` field that the Codex-compatible
backend rejected with `Unsupported parameter: session_id`. The transport
layer still produced a valid empty commit + create-only ref. That attempt
remains in the DB as historical evidence and is **not** the receipt for
this node.

## IDs

| Field | Value |
| --- | --- |
| event_id | `evt_n2_live_attempt_1_3f7b2e` |
| event status | `mapped` (classification: `implementation_request` → node `job-state-consistency`) |
| job_id | `job_20260726T081330259c7d2af87dc3` |
| job status / queue_state | `awaiting_review` / `awaiting_review` |
| session_db_id | `ses_20260726T081330263a8fbf31b139` |
| session_id | `job_20260726T081330259c7d2af87dc3-job-state-consistency-attempt-0-fce8cfb20bdc460a89badba27c072379` |
| session state | `evaluated` |
| result_id | `res_job_20260726T081` |
| result outcome / status | `pass` / `awaiting_review` |

## Refs and SHAs

| Field | Value |
| --- | --- |
| expected_base_commit_sha | `665465e54b3b60951c9e2931852d36295f1fdfad` (current main at dispatch) |
| result_ref | `gddp/attempt-job_20260726T081330259c7d2af87dc3-attempt-0` |
| result_commit_sha | `6c0a4b2ddc41ba6e796310c919749b8cb13bb5ff` |
| result_commit parent | `665465e54b3b60951c9e2931852d36295f1fdfad` (descends from base) |
| diff stat | 10 files changed, +1008 / -98 |

## Worker model

| Field | Value |
| --- | --- |
| smoke (N2-3 transport proof) model | `clinepass/cline-pass/minimax-m3` |
| live (N2-5 attempt 1) model | `clinepass/cline-pass/minimax-m3` — **identical to smoke**; the route is the proven one |
| agent CLI | `pi` (Homebrew) |
| argv route | `/opt/homebrew/bin/pi --model clinepass/cline-pass/minimax-m3 --thinking high --print --no-session --approve --tools read,bash,edit,write,grep,find,ls` |
| supervisor | `scripts/local_agent_executor.py` (worktree → create-only ref → gddp.local_result.v1 handoff on stdout) |

The Codex path (`openai-codex/gpt-5.6-sol`) was attempted in attempt 0 and
failed with `Unsupported parameter: session_id`. Same `pi` wrapper hits
that error on the openai and openai-codex backends; the clinepass path
used here is the proven one and is the argv the live attempt is pinned to.

## Required artifacts (provenance at result SHA `6c0a4b2d…`)

| File | Present at result SHA | Changed vs base `665465e…` |
| --- | --- | --- |
| `decision.md` | yes (blob `d55a5209…`) | yes (+199 / -9) |
| `result-summary.md` | yes (blob `267aa1dc…`) | yes (+68 / -6) |
| `patch.diff` | yes (blob `8a54df0e…`) | yes (+399 / -77) |
| `graph-update.yaml` | yes (blob `38c3f249…`) | yes, new (not in base) (+53) |

`artifact_verifications` DB rows for this job: **0**. The receipt lives in
`results.acceptance_check` (the `evaluator-receipt.json` next to this
file), not in `artifact_verifications`. This is the truthful count, not
a misreport.

## Runner outcome (N2-5)

- `RUNNER_RC=0`
- invariant check: `OK: N2-5 dispatch boundary holds`
  (one job, executor `local_subprocess`, one `executor_session`,
  packet + command files exist, packet base SHA matches, command argv
  matches pinned live argv, zero results rows, zero artifact verifications)
- blast-radius: `OK: no unrelated rows changed`
- `gddp-config` HEAD: `4657c86aa69ea0236b90d8e719536ae993b4f08a` (unchanged)
- runtime HEAD: `665465e54b3b60951c9e2931852d36295f1fdfad` (unchanged at dispatch)

## Reconciliation outcome (N2-6)

- controlled Python invocation: `reconcile_sessions(con, repo_path, repo)`
  for `repo='skchaudr/gddp-runtime'`, no full heartbeat planner
- stdout (one cycle):
  `[reconcile] 1 active executor session(s) to poll. ses_…: completed → evaluation: ok → verdict: pass → result commit 6c0a4b2d… → job → awaiting_review`
- evaluator verdict: `pass` (criteria `pass`, integrity `pass @ 0.95`,
  `intent_preserved=true`, `graph_integrity_preserved=true`)
- evaluator's `evaluated_commit_sha` = `merge_commit_sha` = `6c0a4b2d…b5ff`
  (commit matches merge — a direct local route, not a PR)
- required_next_action (evaluator recommendation, not applied): "Proceed
  to accept_node (open evidence PR)"

## Service final state

| Service | Before N2-7 | After N2-7 |
| --- | --- | --- |
| `com.gddp.heartbeat` | unloaded (kept down while N2 event existed in queue) | **loaded** (idempotent reload after reconciliation) |
| `com.gddp.intake` | loaded | **loaded** |

## PENDING Sab decisions

Two separate human calls. (1) does not imply (2).

1. **Attempt evidence — is attempt 1 a valid real-round-trip receipt?**
   - Path forward options: accept proof, retry run, revise route.
2. **Capability node — `direct-executor-round-trip` in the graph?**
   - Path forward options: accept, retry, revise, defer, abandon.

## What this archive preserves

- N2-5 dispatch evidence (`00.preflight.txt`, `04.runner.stdout`,
  `05.dispatch-report.json`, `06.db-blast-radius.txt`, `06.db.sha256.after`,
  `06.db.mtime.after`, `PHASE_INJECT_OK`, `PHASE_DISPATCH_OK`)
- N2-6 reconcile evidence (`n2-6-00.preconditions.txt`,
  `n2-6-01.reconcile.stdout`, `n2-6-02.verdict.txt`)
- The full evaluator JSON receipt (`evaluator-receipt.json`)
- This summary (`n2-7-summary.md`)

## What this archive does NOT do

- does not merge the result commit
- does not touch graph truth (`gddp-config` HEAD unchanged at `4657c86`)
- does not write node status (the capability node stays `pending` until
  Sab's decision #2)
- does not retry, does not change the runbook, does not push to remote

## Cross-references

- Attempt 0 (failed Codex path) — preserved at `../n2-live-attempt-0/`
- Smoke (N2-3 transport proof) — ref `gddp/attempt-n2-smoke-0a7051c01ea3-attempt-0` at commit `b785375…` in the main repo
- Plan — `docs/pi-native-five-node-baseline-plan.md` (now reflects N2-3/4/5/6 closed, N2-7 next)
- Handoff — `.handoffs/055-*.md` (created in this same change)
