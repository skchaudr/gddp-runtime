# Pi-Native Five-Node Baseline Plan

## Operating rewrite (r2) — verified surfaces, manual parent, suggested topology

**Status:** prepended after design critique. This section is the binding operating posture for execution. Sections below remain historical plan material (ledger spine, milestones, review corrections). Where they conflict with this rewrite, **this rewrite wins** until jointly revised.

### Binding invariants (keep)

- Same wave means **eligible**, not automatically launched.
- Concurrent writers require isolated worktrees and disjoint ownership.
- One live DB/control-plane actor; observers remain read-only.
- Children return evidence; **parent** verifies and integrates.
- Human packets stop for Sab.
- Provider failure / peer silence → **blocked-capability**, not a node verdict.
- Failed work blocks dependents; isolated siblings may continue.

### What this rewrite drops as binding choreography

Ledger `run:` strings, fixed worktree names, triple-audit-everywhere, auto “ready-set scheduler,” per-packet epoch YAML materialization as ceremony, and invented launch syntax are **suggestions or legacy labels**. They do not authorize a route. Each activated NTP chooses its actual route from live evidence at activation time.

### Verified Pi surfaces (checked live at r2 write)

| Surface | How it actually works | Verified |
|---------|----------------------|----------|
| Parent Pi tools | `read` / `bash` / `edit` / `write` / `grep` / `find` in this session | yes — primary loop |
| `subagent` single | `subagent({ agent, task, async, context, cwd, output, acceptance })` | yes — used this mission |
| `subagent` parallel | `subagent({ tasks: [{agent,task,...}], concurrency })` | config allows maxTasks 8 / concurrency 4 |
| `subagent` chain array | Load `~/.pi/agent/chains/<name>.chain.json`, interpolate `{task}`, pass **array** as `subagent({ chain: [...] })`. Tool does **not** run saved chains by name string | yes — docs + chain files present |
| Named agents | `scout`, `reviewer`, `delegate`, `planner`, `worker`, … via `subagent({ action: "list" })` | package live |
| Agent-bus | `bus ask` / `bus send` / `bus history`; `bus whoami` → `agent-sab-mini` @ `:8765`; client/server 2.0.0 | yes |
| Codex / Claude peers | Reachable only if they poll the bus; silence = unavailable, not approval. Prior ASKs 610/611 had no replies at last check | transport yes; peer liveness per-call |
| `pi-brief` | Separate Pi sessions per brief step; `pi-brief validate\|step\|run` | binary present; `gddp-node2-prep.brief.json` exists |
| Herdr | `herdr` CLI present; visible panes via harness `spawn` when used | binary present |
| Worktrees | `git worktree add` under repo; one writer per worktree | git standard |
| Evidence root | `.handoffs/artifacts/five-node-baseline/` (create on first write) | path convention |

**Config fact (not doctrine):** `maxSubagentDepth: 1`, `asyncByDefault: true`, global concurrency 8. Treat as current machine settings to re-check, not sacred law.

### Manual parent operating loop

Parent Pi is the only orchestrator. No auto-dispatcher.

1. **Pick next work with Sab** — name packet id(s) from the ledger DAG and ready frontier; confirm gates.
2. **Preflight the route** — for that packet only: confirm agent/bus/worktree/cwd; one known-good smoke if the surface is cold.
3. **Choose topology from live evidence** — pick among verified surfaces above; record the choice in the packet receipt (`route_used`).
4. **Dispatch** — launch child(ren); if results are load-bearing for the next human decision, parent depends on them (parallel is fine; “walk away async” is not automatic).
5. **Verify** — parent re-checks evidence paths, commands, hashes; write receipt under evidence root.
6. **Update frontier by hand** — mark packet checkpointed/blocked; list what becomes eligible; stop for human packets.
7. **Escalate** — scope breach, isolation conflict, or missing capability → stop that line, preserve evidence, ask Sab.

Session note: async run ids are session-local. A new parent session re-reads evidence + ledger status; it does not resume invisible scheduler state.

### Suggested topology per wave (non-binding)

Activate one wave at a time. Re-validate routes when the wave opens.

| Wave | Packets | Suggested topology | Why suggested |
|------|---------|--------------------|---------------|
| W00 | N00-W01A, N00-W01C | Parent-dependent parallel: two routes — (A) `scout` or loaded `contract-scout` chain array; (C) same plus `bus ask` codex + claude if peers alive | Freeze shared truth + prove peer lanes before definition/live work |
| W01 | N00-W01B, N00-W02A | B: parent/direct or visible live pane after Sab auth; A: review agents / bus auditors after snapshot | Service restore separate from definition review |
| W02 | N00-W03A | Human only | Graph epoch / def policy |
| W03–W06 | N01 recon → optional fix → audit → Sab | Recon: scout; fix: worker in isolated worktree if gap proven; audit: reviewer (+ peers if useful) | Node1 policy evidence |
| W07–W13 | N02 lineage → smoke → live gate → actor+observer → archive → audit → Sab | Smoke/fix in worktree; live actor parent-visible; observer separate read-only child; peers optional on audit | Real round-trip evidence |
| W14–W17 | N03 | Prefer receipt reuse; writer only if named gap; Sab decision | Avoid re-prove |
| W20 | N04-W02A ∥ N04-W02B | **Required dual writer:** two worktrees, two worker sessions, path-disjoint; parent integrates later | Concurrency implementation |
| W22 | N04-W05A ∥ N04-W05B | One live actor + read-only observer | Live concurrency proof |
| W22b | N04-W05C | Human acceptance during overlap; parent captures | acceptance-unblocks-downstream |
| W23 / W23b | bundle then audit | Parent/scout bundle; then review agents (peers optional, not mandatory triple) | Evidence then challenge |
| W26 / W26b | N05-W01B ∥ N05-W01C → selection | Two isolated prototype writers; then bakeoff packet | Dual prototype |
| W31 | N99 manifest / validation / inventory | Parallel read-only where isolation holds | Closeout evidence |

**Audits:** use multi-lane review when the packet is high-stakes or disputed; default is parent + one reviewer. Codex/Claude are optional evidence lanes when bus peers respond.

### Per-NTP activation rule

When a packet starts:

1. Read its outcome, boundary, depends_on, checkpoint from the ledger.
2. Ignore ledger `run:` as a hard command; treat it as a hint.
3. From verified surfaces + current peer/worktree state, write `route_used` into the attempt receipt.
4. Execute that route only.

### Immediate intent of W00 (why two read-only packets)

W00 exists to put one shared baseline under the long path above (M0→M6, human gates, dual-writer and live actor/observer waves later). N00-W01A freezes runtime/config/DB/launchd/worktree truth (including measuring intake criticals). N00-W01C proves whether Pi children and bus peers can return correlated receipts **now**. Neither mutates the project. After both checkpoint: optional N00-W01B (Sab live auth), N00-W02A definition review, then hard stop at N00-W03A.

---

# Pi-Native Five-Node Baseline Plan (ledger body)

**Plan ID:** `gddp-five-node-new-baseline`  
**Schema:** `pi.node-packet-ledger.v1`  
**Status:** r1 review corrections landed — **paused** (not started)  
**Revision:** `r1-review-corrections`  
**Machine ledger:** [`pi-native-five-node-baseline-ledger.yaml`](./pi-native-five-node-baseline-ledger.yaml)  
**Adversarial review:** [`pi-native-five-node-baseline-review.md`](./pi-native-five-node-baseline-review.md)

## Goal

Finish the five-node GDDP capability spine baseline with Pi-native multiagent orchestration (parent Pi + subagents + Codex/Claude via agent-bus). Preserve Sab-owned graph truth. Reuse Factory/052/053 evidence. Do not resume Factory mission `3efe69ab` unless Sab chooses it as executor.

## Current truth (E0)

| Surface | State |
|---------|-------|
| Runtime | `main@35b41a1` clean; 379 tests pass |
| Production intake | BROKEN — launchd registered, not running; critical count **unverified** until N00-W01A measures it |
| Graph statuses | Node1 `deferred`; Nodes2–5 `pending` (zero accepted) |
| Config dirty | `job-state-consistency.yaml` adds `local_subprocess` first in `allowed_execution_modes` — Sab-owned disposition |
| Node2 evidence | Synthetic + real evaluator receipt preserved (052/053); **no real ready-node dispatch yet** |
| Factory | Mission paused (stale wrapper asserts + 429); archive/wrapper commits are evidence only |

## Authority

| Domain | Owner |
|--------|-------|
| Graph definitions/status/acceptance/completion | **Sab only** |
| Live production dispatch / launchd / credentials | **Sab authorizes windows** |
| Packet dispatch, topology, evidence synthesis | Parent Pi |
| Codex / Claude | Advisors only — silence ≠ approval; outputs are evidence |

**Invariant:** Packet success, tests, executor success, and evaluator verdicts are evidence, never completion.

## Operating model (Factory lessons baked in)

1. **Contract/version co-evolution** — definition rewrite + validator assertions = one transaction; superseded contracts are historical only.
2. **Async steering** — dispatch returns; parent stays alive; interrupt pauses worker only.
3. **Worker handoff receipts** — every worker returns structured handoff (commands, issues, leftover work).
4. **Typed progress log** — append-only reconstructable log; chat is not the log.
5. **Scoped gates + env baselining** — gate only packet-owned surface; pre-existing reds are baseline.
6. **No false semantic verdicts** — 429 / peer silence / harness crash = blocked-capability, not node fail/pass.
7. **Graph epochs** — freeze `epoch_manifest_sha256` over `project.yaml` + all node YAMLs for one proof epoch; intentional Sab edits open a successor epoch.
8. **Reuse, don’t re-prove** — Factory M1 + 052/053 carry forward; Node2 real receipt doubles as Node3 when complete.
9. **Concurrent writers only with isolation** — worktrees/branches/paths; parent owns integration.

## Milestone spine (M0–M6)

| Milestone | Outcome | Key packets |
|-----------|---------|-------------|
| **M0** Control plane | Freeze truth, capability, five-definition authority into E0 | N00-W01A…W03A |
| **M1** Node1 | Retain deferred policy or re-scope with criterion evidence | N01-W01A…W04A |
| **M2** Node2 real dispatch | One real `job-state-consistency` round-trip → `awaiting_review`, no override | N02-W01A…W04A |
| **M3** Node3 evaluator | Criterion + canonical-context; reuse Node2 receipt | N03-W01A…W04A |
| **M4** Concurrency | Capacity at runner reservation + claim writer; two-real-node live proof; **acceptance-during-overlap** | N04-W01A…W07A (incl. W05C, W06A/B) |
| **M5** Frontier | Dual prototypes (separate packets) → selection → before/after Sab acceptance | N05-W01A…W04A (incl. W01B/C/D) |
| **M6** Baseline close | Manifest, validation, retirement inventory, Sab baseline hash | N99-W01A…W03A |

**Counts:** 49 packets · 7 milestones · waves W00–W33 (+ W22b/W23b/W26b) · DAG acyclic · roots `N00-W01A`, `N00-W01C`.

## Ready frontier (now)

**Run now (read-only, parallel):**
- `N00-W01A` — current snapshot (runtime/config/DB/launchd/worktrees)
- `N00-W01C` — Pi-subagent + agent-bus capability smoke

**Held:**
- `N00-W01B` — intake restore (needs Sab live-service auth + snapshot); **does not block definition work**
- `N00-W02A` — five-definition review (needs snapshot)
- `N00-W03A` — Sab graph-definition + Node1 dependency policy (depends on N00-W02A only)

**Exact resume:** start N00-W01A + N00-W01C → then N00-W01B (if authorized) + N00-W02A → stop for N00-W03A before any Node1/2 execution.

## Critical path (human gates)

```
N00-W03A (Sab defs/epoch; not gated on intake)
  → N01-W04A (Sab Node1 policy)
    → N02-W01C (Sab live gate; requires N00-W01B disposition)
      → N02-W02A real dispatch + N02-W02B observer
        → N02-W04A (Sab Node2)
          → N03-W04A (Sab Node3)
            → N04 two-writer → live two-node → N04-W05C acceptance-overlap
              → W06A bundle → W06B audits → N04-W07A (Sab)
                → N05-W01B/C prototypes → W01D selection → before/after → N05-W04A
                  → N99-W03A (Sab baseline)
```

## Parallelism that matters

| Wave | What runs together | Isolation rule |
|------|--------------------|----------------|
| W00 | N00-W01A + N00-W01C | Read-only, separate evidence files |
| W10 | N02 actor + observer | Observer never control-plane |
| W20 | N04 capacity (`runner.py` reservation) + claim writer | Separate worktrees/paths/tests |
| W22 | N04 live actor + observer | Same as W10 |
| W22b | N04-W05C acceptance during overlap | Sab-gated; peer still active |
| W23 / W23b | Bundle then triple audit | Separate packets |
| W26 / W26b | N05 prototypes A+B then selection | Separate packet checkpoints |
| W31 | Manifest + validation + retirement inventory | Separate evidence outputs |

## Primary live proof target

**Node:** `job-state-consistency`  
**Path:** minimal worktree-only `local_agent_executor`  
**Forbidden:** `GDDP_EXECUTOR_OVERRIDE`, manual DB repair/reset/delete, auto-complete past `awaiting_review`

## Evidence root

```
/Users/sab-mini/repos/gddp-runtime/.handoffs/artifacts/five-node-baseline/
```

Every packet writes an immutable attempt receipt before its worktree may be retired.

## Review corrections (r1 — landed)

| Sev | Finding | Status in ledger |
|-----|---------|------------------|
| Blocker | N04 capacity on `dispatcher.py` | **Fixed** — N04-W02A owns `runner.py` reservation/planning |
| Blocker | No `acceptance-unblocks-downstream` proof | **Fixed** — N04-W05C Sab-gated acceptance-during-overlap |
| High | Epochs = project.yaml only | **Fixed** — `epoch_manifest_sha256` over project + all node YAMLs |
| High | N00-W01B blocked definitions | **Fixed** — N00-W03A depends on N00-W02A only; N02-W01C requires N00-W01B |
| High | Checkpoints not executable | **Partial** — `packet_contract` + default `verification` fields; per-packet files materialize at activation |
| Medium | N04-W06 composite | **Fixed** — W06A bundle / W06B triple audit |
| Medium | N05 shared prototype checkpoint | **Fixed** — W01B / W01C / W01D selection |
| Medium | 4 intake criticals | **Fixed** — marked `unverified`; measure in N00-W01A |

## What this plan deliberately does not do

- Resume Factory mission `3efe69ab` (paused; stale-contract theater)
- Infer node acceptance from tests/executor/evaluator
- Allow agent graph writes
- Reset/delete evidence or force-cleanup worktrees as part of packets

## Activation

**Paused after r1 corrections.** Say **go** (or name a subset) to start W00: `N00-W01A` + `N00-W01C` in parallel.
