# Pi-Native Five-Node Baseline Plan

**Plan ID:** `gddp-five-node-baseline`  
**Revision:** v3  
**Status:** active map (pivot when reality changes)  
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
| Runtime | `main` with minimal local worktree wrapper (`local_agent_executor`); suite green at last check |
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

---

## Node 1 — `neutral-executor-contract`

**Done when:** node status is **deferred** (Sab-owned graph toggle).

No criterion map, adapter audit, or implementation list. Deferred does **not** block Node 2.

---

## Node 2 — real local executor round-trip (active)

**Capability intent:** prove a real ready node through local subprocess / worktree transport to human review, without override.

**Work subject:** `job-state-consistency` (ready).  
**Transport:** graph-selected `local_subprocess` → adapter → `local_agent_executor` + real agent argv.  
**Stop:** job reaches `awaiting_review`. Sab decides accept / retry / revise.

### Tasks (all required unless Sab waives)

| # | Task | Notes |
|---|------|--------|
| N2-1 | **Dispose stuck canary job** | Mark the blocking job **failed** (human disposition). Keep receipt, DB rows, refs, patch. **Do not delete/reset.** Prefer an honest job-dispose path; do not misuse graph “node status” UI/CLI for job janitor work. |
| N2-2 | **Seal routing provenance** | Commit dirty `local_subprocess` first on `job-state-consistency` as Sab-owned graph config (or explicit Sab waiver to run dirty-only). |
| N2-3 | **Pin run-scoped execution env** | Set `GDDP_LOCAL_SUBPROCESS_ARGV` (wrapper + agent) and spool dir; **unset** override; keep automatic heartbeat from firing a bad env (manual ticks or unload for the window). |
| N2-4 | **Inject one tagged work event** | One `issue.opened` (or equivalent intake path) tagged `node: job-state-consistency`. |
| N2-5 | **Manual dispatch tick** | One controlled heartbeat/runner tick: classify → reserve → dispatch. Observe session/agent. |
| N2-6 | **Collect → evaluate → `awaiting_review`** | Further controlled ticks: collect patch, reconcile, evaluate with real credentials as required. Stop at human review. |
| N2-7 | **Archive + Sab decision** | Packet, job/attempt/session/result IDs, spool metadata, diff/ref/SHA, lane status, pre/post config hashes. Then Sab accept / retry / revise. |

**Parallel inside N2 (optional, isolation-safe):** after N2-2/N2-3 are set, prepare archive layout while N2-4/N2-5 run; read-only observer on logs/DB during live ticks if desired. No second control-plane actor.

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
2. Execute **N2-1 → N2-7** (Node 2 list).  
3. Stop for Sab on the real N2 receipt.  
4. Only then open Node 3.

## Related artifacts

- Machine ledger (historical, superseded as binding choreography): `docs/pi-native-five-node-baseline-ledger.yaml`  
- Prior review notes: `docs/pi-native-five-node-baseline-review.md`  
- Node 2 preflight (config + dispatch):  
  `.pi-subagents/artifacts/outputs/023beec1-3443-4d0a-b914-4c057152883f/n2-preflight-config.md`  
  `.pi-subagents/artifacts/outputs/023beec1-3443-4d0a-b914-4c057152883f/n2-preflight-dispatch.md`  
- Factory 12h forensic: `~/.pi/agent/observability/factory/shadow/3efe69ab-0dc5/factory-last-12h-analysis.md`
