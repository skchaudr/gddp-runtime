# Pi-Native Five-Node Baseline Plan

**Plan ID:** `gddp-five-node-new-baseline`  
**Schema:** `pi.node-packet-ledger.v1`  
**Status:** draft for Sab activation (not started)  
**Machine ledger:** [`pi-native-five-node-baseline-ledger.yaml`](./pi-native-five-node-baseline-ledger.yaml)  
**Adversarial review:** [`pi-native-five-node-baseline-review.md`](./pi-native-five-node-baseline-review.md)

## Goal

Finish the five-node GDDP capability spine baseline with Pi-native multiagent orchestration (parent Pi + subagents + Codex/Claude via agent-bus). Preserve Sab-owned graph truth. Reuse Factory/052/053 evidence. Do not resume Factory mission `3efe69ab` unless Sab chooses it as executor.

## Current truth (E0)

| Surface | State |
|---------|-------|
| Runtime | `main@35b41a1` clean; 379 tests pass |
| Production intake | BROKEN — launchd registered, not running; critical count to re-measure in N00-W01A |
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
7. **Graph epochs** — freeze config hashes for one proof epoch; intentional Sab edits open a successor epoch.
8. **Reuse, don’t re-prove** — Factory M1 + 052/053 carry forward; Node2 real receipt doubles as Node3 when complete.
9. **Concurrent writers only with isolation** — worktrees/branches/paths; parent owns integration.

## Milestone spine (M0–M6)

| Milestone | Outcome | Key packets |
|-----------|---------|-------------|
| **M0** Control plane | Freeze truth, capability, five-definition authority into E0 | N00-W01A…W03A |
| **M1** Node1 | Retain deferred policy or re-scope with criterion evidence | N01-W01A…W04A |
| **M2** Node2 real dispatch | One real `job-state-consistency` round-trip → `awaiting_review`, no override | N02-W01A…W04A |
| **M3** Node3 evaluator | Criterion + canonical-context; reuse Node2 receipt | N03-W01A…W04A |
| **M4** Concurrency | Two isolated writers + two-real-node live proof | N04-W01A…W07A |
| **M5** Frontier | Dual prototypes → selected report → before/after Sab acceptance | N05-W01A…W04A |
| **M6** Baseline close | Manifest, validation, retirement inventory, Sab baseline hash | N99-W01A…W03A |

**Counts:** 45 packets · 7 milestones · 34 waves · DAG acyclic · roots `N00-W01A`, `N00-W01C`.

## Ready frontier (now)

**Run now (read-only, parallel):**
- `N00-W01A` — current snapshot (runtime/config/DB/launchd/worktrees)
- `N00-W01C` — Pi-subagent + agent-bus capability smoke

**Held:**
- `N00-W01B` — intake restore (needs Sab live-service auth + snapshot)
- `N00-W02A` — five-definition review (needs snapshot)
- `N00-W03A` — Sab graph-definition + Node1 dependency policy (Sab-only)

**Exact resume:** start N00-W01A + N00-W01C → then N00-W01B (if authorized) + N00-W02A → stop for N00-W03A before any Node1/2 execution.

## Critical path (human gates)

```
N00-W03A (Sab defs/epoch)
  → N01-W04A (Sab Node1 policy)
    → N02-W01C (Sab live dispatch gate)
      → N02-W02A real dispatch + N02-W02B observer
        → N02-W04A (Sab Node2)
          → N03-W04A (Sab Node3)
            → N04 two-writer → live two-node → N04-W07A (Sab)
              → N05 prototypes → live before/after → N05-W04A (Sab)
                → N99-W03A (Sab baseline)
```

## Parallelism that matters

| Wave | What runs together | Isolation rule |
|------|--------------------|----------------|
| W00 | N00-W01A + N00-W01C | Read-only, separate evidence files |
| W10 | N02 actor + observer | Observer never control-plane |
| W20 | N04 capacity writer + claim writer | Separate worktrees/paths/tests |
| W22 | N04 live actor + observer | Same as W10 |
| W26 | N05 prototype A + B | Separate worktrees/branches |
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

## Known corrections before/at activation

From adversarial review (see review file for full text). Apply these before treating the ledger as frozen:

| Sev | Finding | Fix |
|-----|---------|-----|
| Blocker | N04 capacity assigned to `dispatcher.py` (too late / no DB) | Move ownership to reservation/planning in `runner.py` |
| Blocker | N04 never proves `acceptance-unblocks-downstream` | Add Sab-gated acceptance-during-overlap packet inside two-job window |
| High | Epochs hash only `project.yaml` | Epoch = manifest hash of project.yaml + all node YAMLs |
| High | N00-W01B blocks all definition work | Drop N00-W01B from N00-W03A deps; attach health only to live packets |
| High | Checkpoints are prose, not executable | Materialize min-contract packet files with commands + expected assertions |
| Medium | N04-W06A bundles assemble+audit | Split bundle / audits / reconcile |
| Medium | N05 prototypes share one packet status | Split A/B packets + selection packet |
| Medium | “4 intake criticals” unverified | Re-measure in N00-W01A; do not treat count as frozen |

## What this plan deliberately does not do

- Resume Factory mission `3efe69ab` (paused; stale-contract theater)
- Infer node acceptance from tests/executor/evaluator
- Allow agent graph writes
- Reset/delete evidence or force-cleanup worktrees as part of packets

## Activation

Say **go** (or name a subset) to start W00: `N00-W01A` + `N00-W01C` in parallel.  
Say **apply review fixes** to revise the ledger YAML before activation.  
Say **land corrections** if you want the blocker/high fixes folded into the machine ledger first.
