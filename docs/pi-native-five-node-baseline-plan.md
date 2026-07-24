# Pi-Native Five-Node Baseline Plan

**Plan ID:** `gddp-five-node-baseline`  
**Revision:** v3.1  
**Status:** active map (pivot when reality changes)  
**v3.1:** N2-0 commit-ref transport; N2-1 `mark_job_failed`; secrets preflight (`gpg`, not `pass` under launchd).  
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
| Runtime | `main` with worktree wrapper (`local_agent_executor`); suite green at last check. **Known landmine:** current wrapper still emits worktree **diff on stdout** — fix to **commit-ref handoff** before live dispatch (N2-0). |
| Factory | Mission ended; ignore stale wrapper-validator loops |
| Capability Node 1 `neutral-executor-contract` | **deferred** — status toggle only |
| Capability Nodes 2–5 | **pending** until Sab accepts |
| Ready work subject for N2 proof | `job-state-consistency` (`ready` in graph) |
| Config delta | Dirty `+local_subprocess` first in that node’s `allowed_execution_modes` (local FS load sees it; commit seals provenance) |
| Live queue | Historical canary job on that node may sit `awaiting_review` and block a new job until **job-disposed** (failed), with all evidence kept |
| Forbidden for real N2 | `GDDP_EXECUTOR_OVERRIDE` |

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
**Transport (target):** graph-selected `local_subprocess` → adapter → `local_agent_executor` + real agent argv → **worktree commit + ref/SHA on the handoff** → adapter `collect` takes the ref; diffs derived from git afterward if needed. **Do not** use diff-on-stdout as the production handoff (current code still does that until N2-0 lands).  
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
| N2-0 | **Fix transport: commit-ref, not diff-emit** | Bounded code change **before** live dispatch. Wrapper commits in the worktree and surfaces **ref/SHA**; adapter `collect` picks up the ref; any diff is derived from git afterward. Replace stdout patch-as-handoff (`emit_diff` path). Focused tests green. Route failure here is engineering, not a node verdict. |
| N2-1 | **Dispose stuck canary job** | Sab confirms the preserved `awaiting_review` evidence is not being accepted. Fail the **job** via existing `state_recorder.mark_job_failed` (same mechanism `scripts/runtime/replay.py` uses) + durable reason/receipt. Keep DB rows, refs, patch. **Do not** delete/reset; **do not** use graph “node status” tooling for job disposal. Graph truth untouched. |
| N2-2 | **Seal routing provenance** | Sab decides whether to commit/push the known one-line `local_subprocess`-first config delta or explicitly authorize the dirty epoch. Record the exact config hash used by the attempt. Do not broaden the graph edit. |
| N2-3 | **Pin env, secrets preflight, smoke exact route** | Choose post-N2-0 `local_agent_executor` + one non-interactive real-agent argv; set spool dir; **unset** override. **Secrets:** any GDDP key/cmd used in this window must use direct `gpg --decrypt` (or equivalent non-hanging decrypt) — **not** `pass` under launchd/agent, which can hang. Run one disposable no-DB smoke on the exact argv/packet contract (commit-ref handoff). Use the identical argv for the live attempt; route failure is a route problem, not a node failure. Record whether launchd is unloaded or manual execution has sole heartbeat ownership. |
| N2-4 | **Inject one tagged work event** | One `issue.opened` (or equivalent intake path) tagged `node: job-state-consistency`. Preserve the exact payload/INSERT and resulting event row. A second event or wrong node classification stops the route. |
| N2-5 | **One controlled dispatch tick** | Only after N2-0 is landed. Immediately before the tick, re-check HEAD, config hash, event ID, required env names, absent override, secrets preflight, and single control-plane ownership. Record selected executor and job/attempt/session IDs. Stop before retry if selection is not `local_subprocess`. |
| N2-6 | **Collect → evaluate → `awaiting_review`** | Further controlled ticks: collect **ref**, reconcile, evaluate with real credentials (same secrets rule as N2-3). Join packet → attempt → session → result commit/ref → evaluator receipt. Independently verify artifacts for this attempt; pre-existing files do not count. If provenance is wrong or duplicate evaluation appears, preserve and pivot. Stop at human review. |
| N2-7 | **Archive + Sab decision** | Archive packet, event/job/attempt/session/result IDs, spool metadata, **result ref/SHA** (and derived diff if useful), artifact-provenance check, lane status, command log, and pre/post config hashes. Sab then accepts, retries, revises, defers, or abandons the capability node. |

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
- **Job dispose ≠ graph node toggle.** Keep those surfaces honest.

## Exact resume (now)

1. Confirm Node 1 remains **deferred** (status only).  
2. **N2-0** transport fix (commit-ref) in parallel with **N2-1** job dispose when useful.  
3. **N2-2 → N2-3** (seal config, pin env + secrets preflight + smoke).  
4. **N2-4 → N2-7** live loop; stop for Sab on the real receipt.  
5. Only then open Node 3.

## Related artifacts

- Machine ledger (historical, superseded as binding choreography): `docs/pi-native-five-node-baseline-ledger.yaml`  
- Prior review notes: `docs/pi-native-five-node-baseline-review.md`  
- Node 2 preflight (config + dispatch):  
  `.pi-subagents/artifacts/outputs/023beec1-3443-4d0a-b914-4c057152883f/n2-preflight-config.md`  
  `.pi-subagents/artifacts/outputs/023beec1-3443-4d0a-b914-4c057152883f/n2-preflight-dispatch.md`  
- Factory 12h forensic: `~/.pi/agent/observability/factory/shadow/3efe69ab-0dc5/factory-last-12h-analysis.md`
