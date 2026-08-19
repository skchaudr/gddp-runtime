# Current Architecture & Active State — GDDP Runtime

This document records the architectural contracts, host topologies, and runtime mechanisms active in production today.

---

## 1. Active Production Topology

Production operations run on the following verified topology (as documented in [`TOPOLOGY.md`](../../TOPOLOGY.md)):

| Component | Host / Location | Configuration | Status |
|---|---|---|---|
| **Control Plane Host** | `sab-mini` | Mac Mini (16GB RAM) via Tailscale | **Active Production** |
| **Intake Service** | `sab-mini:5050` | launchd `com.gddp.intake` (Tailscale Funnel `/webhook`) | **Frozen / Active** |
| **Heartbeat Daemon** | `sab-mini` | launchd `com.gddp.heartbeat` → `deploy/mini-heartbeat/bin/arm.sh` | **Active Production** |
| **Queue Database** | `sab-mini` | `~/repos/gddp-runtime/db/queue.db` (SQLite WAL) | **Active Production** |
| **Config Repository** | `sab-mini` | `~/repos/gddp-config` | **Active Production** |
| **Secondary Hosts** | `pi-big` | Standby offline copy (GPG keys migrated to mini) | **Disarmed** |
| **Session Hosts** | `sab-dev` | Agent session VM (dry-run queue only) | **Development** |

---

## 2. Active 5-Step Operating Loop

Runtime execution adheres strictly to the 5-step loop (derived from [`docs/proposals/LOOP.md`](../proposals/LOOP.md)):

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ 1.PACKET │ ──> │2.DISPATCH│ ──> │ 3.RETURN │ ──> │4.EVALUATE│ ──> │ 5. HUMAN │
└──────────┘     └──────────┘     └──────────┘     └──────────┘     └──────────┘
```

1. **Packet:** Node YAML in `gddp-config/graphs/<project>/nodes/` declares intent, constraints, and criteria. Authored/accepted solely by humans.
2. **Dispatch:** Armed heartbeat (`deploy/mini-heartbeat/bin/arm.sh`) claims unblocked ready nodes and allocates each to an isolated session.
3. **Return:** Executor completes execution in an isolated worktree. Receipts write to disk (`GDDP_RECEIPTS_PATH`); results index into `db/queue.db`.
4. **Evaluate:** Reconciler triggers the two-lane evaluator pass (deterministic + semantic + integrity). Emits a verdict receipt in `gddp-config/verification/<project>/`.
5. **Human Review:** Operator reviews receipts and verdict via `gddp node browse` and enters keyboard action (`c` accept, `r` reject, `d` defer).

---

## 3. Active Runtime Components

- **Heartbeat Dispatch:** [`scripts/runtime/heartbeat/`](../../scripts/runtime/heartbeat/)
- **Gate Tokens:** [`scripts/runtime/gate_tokens.py`](../../scripts/runtime/gate_tokens.py)
- **Return Routing:** [`scripts/runtime/return_router.py`](../../scripts/runtime/return_router.py)
- **Two-Lane Verification:** [`scripts/runtime/verification/`](../../scripts/runtime/verification/)
- **Queue Control Backend:** [`scripts/jobs_status.py`](../../scripts/jobs_status.py)
- **Node Receipt CLI:** [`scripts/gddp_node_receipt.py`](../../scripts/gddp_node_receipt.py)
