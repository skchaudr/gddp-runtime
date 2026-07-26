# Pi-Native Five-Node Baseline Plan

**Plan ID:** `gddp-five-node-baseline`  
**Revision:** v3.5<br>
**Status:** active map (pivot when reality changes)  
**v3.1:** N2-0 commit-ref transport; secrets preflight (`gpg`, not `pass` under launchd).  
**v3.2:** N2-7 = two Sab decisions; N2-1 uses **jobs** path (`gddp jobs set` when landed), never graph node write.  
**v3.3:** N2-0 ref consumed directly (descends-from check, no reconstruction worktree); N2-1 landed argv (`jobs_status.py set --reason`).  
**v3.4:** N2-0/N2-1/N2-2 closed from live evidence; **N2-3 is next**.  
**v3.5:** N2-3/4/5/6 closed from live evidence (attempt 0 failed on Codex `session_id`; attempt 1 used the exact proven MiniMax smoke argv and reached `awaiting_review`); **N2-7 archive complete; two Sab decisions pending** on `.handoffs/.../n2-live-attempt-1/`.
**Runtime:** `/Users/sab-mini/repos/gddp-runtime`  
**Graph:** `/Users/sab-mini/repos/gddp-config/graphs/gddp-runtime`

## Goal

Finish the five-node GDDP capability spine baseline with Pi as executor. Sab alone owns graph definitions, node status, acceptance, and completion. Packet success, tests, executor success, and evaluator verdicts are **evidence only** — never completion.

Factory mission `3efe69ab` is **closed**. Its commits and receipts are historical evidence. Do not resume Factory mission mode.

## How this plan behaves

- **Packets chart current intent.** They size and order work. They are not a frozen program.
- **Pivot rule:** when reality changes (stuck job, design change, wrong surface), supersede the next packet. Keep evidence. Do not re-validate against a dead script.
- **Parallel when isolation holds.** Same phase can run concurrent work if paths, jobs, and control-plane ownership do not collide.
- **Sequential only at real gates.** A later **capability node** opens after the prior node’s human decision (or explicit waiver) — not after ceremony.
- **Deferred is a decision, not a queue.** Node 1 does not invent a task list that blocks Node 2.

### Execution horizon

Plan at different resolutions instead of pretending future knowledge is current:

| Horizon | Commitment |
|---------|------------|
| **Now — active node** | Specify the next actions, owner, live boundary, evidence, and stop gate tightly enough to execute. Node 2 below is at this resolution. |
| **Next — next capability** | Preserve intent, entry gate, likely proof, and known risks. Read-only preparation may run early when it shortens the next gate without changing code, graph, or live state. |
| **Later — remaining baseline** | Preserve outcomes, authority, and dependency shape only. Task lists are hypotheses to re-check when their gate opens. |

Abundant model/token capacity is used on independent evidence gathering, route smoke, competing analysis, and failure-mode review that reduces a named uncertainty in **Now** or **Next**. It is not a reason to implement later-node guesses or repeat already-settled validation.

### Checkpoint and pivot rule

After each active task, parent Pi records the new facts and chooses exactly one:

- **continue** — evidence supports the next listed task;
- **repair in scope** — a load-bearing failure is owned by the active node and has a bounded fix;
- **pivot** — supersede the next task/route because live evidence changed, preserving the abandoned attempt and its effect on dependencies;
- **propose graph amendment** — the node meaning, criteria, dependency, or frontier should change; stop implementation for Sab.

Only the active slice is rewritten when evidence changes. Charted later nodes remain a map until their entry gate. Provider failure, an empty/incorrect agent diff, wrong executor selection, stale artifact provenance, duplicate control-plane activity, or unexpected graph/DB state stops the affected route; it does not become a node verdict or trigger a wholesale mission rewrite.

## Authority

| Domain | Owner |
|--------|--------|
| Graph definitions / status / acceptance / baseline completion | **Sab** |
| Live production dispatch windows, credentials, launchd unload/load | **Sab authorizes** |
| Packet dispatch, evidence capture, synthesis | Parent Pi |
| Subagents / peers (Codex, Claude, …) | Bounded help; silence ≠ approval; outputs = evidence |

## Current truth (re-check before each live step)

| Fact | State |
|------|--------|
| Runtime | `main` (current main contains the published N2-7 archive `6238452` and the corrective archive commit with the result-artifacts extraction); **dispatch base** for attempt 1 was `665465e` (the HEAD N2-5 dispatched from); N2-0 commit/ref handoff landed in `f4c3b11`, `8fa4bd5`, `b28125d`; suite green at `665465e`. Exact current HEAD discoverable via `git rev-parse origin/main`. |
| Factory | Mission ended; ignore stale wrapper-validator loops |
| Capability Node 1 `neutral-executor-contract` | **deferred** — status toggle only |
| Capability Nodes 2–5 | **pending** until Sab accepts |
| Ready work subject for N2 proof | `job-state-consistency` (`ready` in graph) |
| Config delta | `local_subprocess` is first in `job-state-consistency.allowed_execution_modes`; committed and pushed in `gddp-config` (`4657c86`). |
| N2 attempt 0 (`n2-live-attempt-0/`) | **failed at the worker layer**: `pi` v0.82.1 emitted `session_id` to the Codex-compatible backend and got `Unsupported parameter: session_id`; transport produced a valid empty commit + ref but no work. Event `evt_n2_live_attempt_0_8c2f1a` preserved, job `job_20260726T04502048326609c51da5` marked `failed`, evidence intact. |
| N2 attempt 1 (`n2-live-attempt-1/`) | **success**: event `evt_n2_live_attempt_1_3f7b2e` → job `job_20260726T081330259c7d2af87dc3` → `awaiting_review`; result `pass` (criteria pass, integrity pass @ 0.95, intent + graph integrity preserved); result commit `6c0a4b2d…b5ff` (parent `665465e…`), ref `gddp/attempt-job_20260726T081330259c7d2af87dc3-attempt-0`. Live argv **identical to smoke argv**: `pi` + `clinepass/cline-pass/minimax-m3` (the proven model+provider). |
| Pinned worker for N2 | `pi` (Homebrew) + `clinepass/cline-pass/minimax-m3` (matching smoke); Codex-compatible backends (openai, openai-codex) are **out** until `pi` stops sending `session_id`. |
| Forbidden for real N2 | `GDDP_EXECUTOR_OVERRIDE` |
| Service state | `com.gddp.heartbeat` and `com.gddp.intake` both loaded; no eligible events; no active executor_sessions for `skchaudr/gddp-runtime`. |

Re-verify live before dispatch; this table is a pointer, not a substitute for a fresh check.

## Scope of this document

| Layer | Meaning |
|-------|---------|
| **Baseline** | All five capability nodes + closeout |
| **Active workstream** | **Node 2** real local round-trip |
| **Charted next** | Node 3 → 4 → 5 → close (not in flight until their gates open) |

For Nodes 3–5, the stated outcome and human entry/exit gates are durable intent. Their numbered tasks are the best current decomposition, not advance authorization to execute or a promise that the decomposition survives new evidence.

---

## Node 1 — `neutral-executor-contract`

**Done when:** node status is **deferred** (Sab-owned graph toggle).

No criterion map, adapter audit, or implementation list. Deferred does **not** block Node 2.

---

## Node 2 — real local executor round-trip (active)

**Capability intent:** prove a real ready node through local subprocess / worktree transport to human review, without override.

**Work subject:** `job-state-consistency` (ready).  
**Transport (target):** graph-selected `local_subprocess` → adapter → `local_agent_executor` + real agent argv → **worktree commit preserved under a per-attempt ref** → reconciler consumes that ref directly; diffs derived read-only from git afterward if needed. **Do not** use diff-on-stdout as the handoff, and **do not** reconstruct results in a second worktree (`git apply` from spooled text) on the local route — that pipeline is what N2-0 retires. Patch-apply remains only for remote/patch-only executors.  
**Stop:** job reaches `awaiting_review`. Sab decides accept / retry / revise.

### One active attempt record

Use one attempt directory for N2 rather than seven ceremonial packet files:

```text
.handoffs/artifacts/five-node-baseline/N2/<attempt-id>/
```

Before the first mutation, record runtime HEAD/status, target node/config hash and diff, blocking job/result/session IDs, selected agent argv (no secret values), heartbeat ownership, and the intended stop condition. Append command outcomes and identifiers as the attempt runs; close it with the archived receipt or a pivot record.

### Tasks (current route; re-check at every checkpoint)

| # | Task | Evidence / pivot condition |
|---|------|----------------------------|
| N2-0 | **CLOSED — Fix transport: commit-ref, not diff-emit** | Commit/ref transport, retained-worktree recovery, create-only refs, and ref-to-SHA verification landed in `f4c3b11`, `8fa4bd5`, and `b28125d`; 389 tests passed. |
| N2-1 | **CLOSED — Dispose stuck canary job** | Sab moved `job_20260724T010811130dd14802e579` from `awaiting_review` to `failed` through `gddp jobs set`; job evidence retained and graph truth untouched. |
| N2-2 | **CLOSED — Seal routing provenance** | `local_subprocess` is first for `job-state-consistency`; the one-line graph config delta is committed and pushed at `4657c86`. |
| N2-3 | **CLOSED — Pin env, secrets preflight, smoke exact route** | Smoke at ref `gddp/attempt-n2-smoke-0a7051c01ea3-attempt-0` → commit `b785375…` (parent `3d530ad`); 1 file, 1 insertion (`gddp-n2-smoke-marker`). **Smoke and attempt-1 live used the same argv including worker model** — `pi` + `clinepass/cline-pass/minimax-m3` (the proven provider+model). Earlier attempt-0 explored the Codex path (`openai-codex/gpt-5.6-sol`) and failed on `pi` sending `session_id`; the smoke proof and the attempt-1 live are on the clinepass path. Secrets preflight: direct `gpg --decrypt` (no `pass` under launchd); gpg rc=0 with no key on disk. |
| N2-4 | **CLOSED — Inject one tagged work event** | Event `evt_n2_live_attempt_1_3f7b2e` injected (in-tx, commit-only-on-validation); classified as `implementation_request` → node `job-state-consistency`; executor recommendation `local_subprocess`. No second event; no other eligible events; no active sessions touched. |
| N2-5 | **CLOSED — One controlled dispatch tick** | Runner rc=0; invariant `OK: N2-5 dispatch boundary holds`; blast-radius `OK: no unrelated rows changed`; one job, one `executor_session` (state `dispatched`), zero `results` rows. Selected executor `local_subprocess`; no `GDDP_EXECUTOR_OVERRIDE`. Receipt at `jobs/local-subprocess-spool/<session_id>/`. |
| N2-6 | **CLOSED — Collect → evaluate → `awaiting_review`** | Reconcile stdout: `1 active executor session(s) to poll … completed → evaluation: ok → verdict: pass → result commit 6c0a4b2d… → job → awaiting_review`. Verdict: criteria pass, integrity pass @ 0.95, intent preserved, graph integrity preserved. `evaluated_commit_sha` = `merge_commit_sha` = `6c0a4b2d…b5ff` (direct local, not a PR). Receipt at `verification-runtime-live/gddp-runtime/job-state-consistency/job_20260726T081330259c7d2af87dc3-attempt0.json`. |
| N2-7 | **Archive complete; two Sab decisions pending** | Archive at `.handoffs/artifacts/five-node-baseline/N2/n2-live-attempt-1/` (N2-5 dispatch, N2-6 reconcile, evaluator JSON receipt, four result-artifacts extracted from commit `6c0a4b2d…` with verified blob SHAs, n2-7-summary). Initial archive published in `6238452`; portable correction (result-artifacts + wording fixes) in `415e869`; current HEAD on `origin/main` discoverable via `git rev-parse origin/main`. **PENDING Sab decisions:** (1) Job/receipt — is attempt 1 valid real-round-trip evidence (accept / retry / revise)? (2) Capability node — accept / retry / revise / defer / abandon `direct-executor-round-trip` in the graph. (1) does not imply (2). |

**Parallel inside N2 (optional, isolation-safe):** N2-0 can proceed while N2-1 is prepared (code vs queue isolation). Once N2-0/N2-2/N2-3 checkpoint, prepare archive structure and run a read-only observer while the parent owns live ticks. No second control-plane actor or default audit swarm.

**N2 exit gate:** Sab’s decision on the real receipt. That opens Node 3 work.

---

## Node 3 — immediate evaluator round-trip

**Opens after:** Node 2 Sab decision (or explicit waiver).

| # | Task | Notes |
|---|------|--------|
| N3-1 | Map N3 criteria to the **existing N2 receipt** + evaluator code | Read-only |
| N3-2 | Fix only a demonstrated gap **or** record no-change | Isolated writer if code changes |
| N3-3 | Reuse N2 proof; rerun evaluation only for a **named** missing criterion | No full re-prove by default |
| N3-4 | Archive + **Sab** decision | |

**Parallel:** N3-1 can start as soon as N2 archive exists; N3-2 only if N3-1 finds a real gap.

---

## Node 4 — concurrent node flow

**Opens after:** Node 2 and Node 3 Sab decisions (or waivers).

| # | Task | Notes |
|---|------|--------|
| N4-1 | Implement capacity at **reservation/planning** (not post-hoc dispatch-only) | Path ownership: runner/reservation surface |
| N4-2 | Implement evaluation **claim** isolation | **Parallel with N4-1** — separate worktrees/paths |
| N4-3 | Integrate + pre-run gate for two real nodes | Parent integration |
| N4-4 | Live two-node run (+ read-only observer); prove overlap | One control-plane actor |
| N4-5 | If criterion still requires it: acceptance that unblocks downstream **while peer work continues** | Sab-gated |
| N4-6 | Archive + **Sab** decision | |

---

## Node 5 — graph frontier operations

**Opens after:** Node 3 and Node 4 Sab decisions (or waivers).

| # | Task | Notes |
|---|------|--------|
| N5-1 | Frontier prototype A | Isolated worktree |
| N5-2 | Frontier prototype B | **Parallel with N5-1** |
| N5-3 | Select, integrate, derived-state check | |
| N5-4 | Before/after report around **Sab** acceptance of a named review item | |
| N5-5 | Archive + **Sab** decision | |

---

## Baseline close

**Opens after:** Nodes 1–5 each have an explicit Sab disposition (deferred counts for N1).

| # | Task | Notes |
|---|------|--------|
| C-1 | Manifest of receipts, hashes, decisions | Read-only assembly |
| C-2 | Final runtime/config/health snapshot | Validation only; no silent repair |
| C-3 | **Sab** baseline decision + final graph hash | |

---

## What we refuse (pace / theater)

- Stale validator contracts blocking an intentional design (Factory failure mode)
- Snapshot/smoke “milestones” that delay the real loop without new proof
- Triple-audit or multi-agent review as a default tax (use when high-stakes or disputed)
- Treating tests, green suites, or `awaiting_review` as node acceptance
- Deleting or resetting evidence to “clear” a job
- Auto-completing past human review

## Pi execution posture (when using helpers)

- **Parent Pi** owns the live control plane for dispatch ticks and evidence synthesis.
- **Subagents** for bounded recon, isolated implementation, or review — load-bearing results stay parent-owned; children are not a black box you abandon mid-flight when you need the outcome this turn.
- **Multiagent / visible peers** when Sab wants more visibility and control (bus, panes, separate sessions).
- **Jobs ≠ nodes.** Jobs: read/write via interactive menu and `gddp jobs …` (including non-interactive set). Nodes: read interactive + shell; **write interactive only** (no non-interactive graph status set). Job dispose is a jobs operation; never a node-status write.

## Exact resume (now)

1. **N2-7 — archive complete; two Sab decisions pending** on `.handoffs/artifacts/five-node-baseline/N2/n2-live-attempt-1/` (initial archive `6238452`; portable correction `415e869` adds result-artifacts and wording fixes):
   (1) accept/retry/revise this attempt as real-round-trip evidence;
   (2) accept/retry/revise/defer/abandon `direct-executor-round-trip` in the graph.
2. Node 3 opens only after the N2 capability-node decision (or an explicit waiver).

## Related artifacts

- Machine ledger (historical, superseded as binding choreography): `docs/pi-native-five-node-baseline-ledger.yaml`  
- Prior review notes: `docs/pi-native-five-node-baseline-review.md`  
- Node 2 preflight (config + dispatch):  
  `.pi-subagents/artifacts/outputs/023beec1-3443-4d0a-b914-4c057152883f/n2-preflight-config.md`  
  `.pi-subagents/artifacts/outputs/023beec1-3443-4d0a-b914-4c057152883f/n2-preflight-dispatch.md`  
- Factory 12h forensic: `~/.pi/agent/observability/factory/shadow/3efe69ab-0dc5/factory-last-12h-analysis.md`
