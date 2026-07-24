# Pi-Native Five-Node Baseline Plan

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
