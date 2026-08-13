# GDDP Runtime Readiness Report — 2026-07-18

Generated for `gddp-runtime` on `sab-mini`. This report reads the working tree,
SQLite queue, receipts, and launchd state to answer whether the runtime can
safely move the next set of nodes through the loop.

## Executive Summary

| Area | Status | Notes |
|---|---|---|
| Code health | ✅ Ready | 325 tests pass; no uncommitted changes |
| Production services | ✅ Loaded | `com.gddp.intake` and `com.gddp.heartbeat` loaded in user domain |
| Evaluator + receipts | ✅ Ready | 3 receipts for gddp-runtime; 2 verdicts are `pass` |
| Human review backlog | ⚠️ Attention | 3 nodes awaiting review; 2 failed jobs need triage |
| Event ingestion | ⚠️ Attention | 6 unprocessed `received` events + 4 `scope_blocked` events |
| Graph freshness | ✅ Minor drift | Graph built from `d066728`; current HEAD `0a95a29` (README edits only) |
| Capability spine | 🟡 In progress | `neutral-executor-contract` implementation complete; acceptance criteria still draft/unchecked |
| Next canary | 🟡 Ready to run | Direct Jules CLI round trip is the pending validation (handoff 047) |

## 1. Repository State

- **Branch:** `main`
- **HEAD:** `0a95a29` — "Personal README edits for portfolio prep"
- **Origin sync:** clean (`main...origin/main` shows no divergence)
- **Uncommitted changes:** none
- **Untracked files:** `.agent/`, `.remember/`, `.venv/`, `db/`, `jobs/`, `events/`, `graphify-out/` (all expected runtime state or ignored)

## 2. Test & Validation Health

```bash
python3 -m pytest -q
```

- **Result:** `325 passed in 4.38s`
- **Coverage includes:** intake, heartbeat, return router, receipt sink, verification/orchestrator, decision loop, graph updater, and the new executor-neutral session lifecycle.
- **No lint configured** (per `AGENTS.md`).

## 3. Production Control Plane (sab-mini)

| Service | PID/State | Notes |
|---|---|---|
| `com.gddp.intake` | loaded, exit code `0` | User-domain launchd job. No running process currently attached; activated on demand by webhook traffic. |
| `com.gddp.heartbeat` | loaded, exit code `0` | User-domain launchd job. Runs on schedule; no stuck process observed. |

Last topology verification: 2026-07-12 (`TOPOLOGY.md`).
- Intake endpoint: `127.0.0.1:5050` (Tailscale Funnel → `https://sab-mini.tail02ac6f.ts.net/webhook`)
- Queue DB: `~/repos/gddp-runtime/db/queue.db`

## 4. Queue / Job Readiness

### State counts

| queue_state | count |
|---|---|
| running | 4 |
| awaiting_review | 3 |
| failed | 2 |

### Event counts

| status | count |
|---|---|
| mapped | 11 |
| ignored | 7 |
| received | 6 |
| scope_blocked | 4 |

### Running jobs (need reconciliation / poll attention)

| Job | Node | Attempt | Since |
|---|---|---|---|
| `job_20260716T102119061b92648235b8` | `heartbeat-crash-recovery` | 0/3 | 2026-07-16 |
| `job_20260716T102119065a2b7cac66cc` | `job-state-consistency` | 0/3 | 2026-07-16 |
| `job_20260711T16542651` | `canary-retry-proof` | 0/3 | 2026-07-11 |
| `job_20260711T16540416` | `pi-evaluator-harness` | 0/3 | 2026-07-11 |

Two of these are from 2026-07-11 and may be orphaned sessions that need the new reconciler to poll/collect/cancel. The heartbeat reconciler (added in handoff 047) is designed for this.

### Failed jobs (need triage)

| Job | Node | Since |
|---|---|---|
| `job_20260715T2001279833f8635f6a99` | `heartbeat-crash-recovery` | 2026-07-15 |
| `job_20260715T20012798349941effd21` | `job-state-consistency` | 2026-07-15 |

These have no evaluator results in the DB summary; they likely failed at dispatch or collection. They are candidates for retry or corrective nodes.

### Awaiting human review

| Job | Node | Verdict | Note |
|---|---|---|---|
| `job_20260711T17104259` | `canary-retry-proof` | **pass** | Retry succeeded; evaluator says "Proceed to accept_node" |
| `job_20260711T16020485` | `verdict-confidence-split` | **pass** | Evaluator says "Proceed to accept_node" |
| `job_dry_001` | `auth-boundary` | — | Synthetic dry-run; receipt exists but no real verdict |

## 5. Evaluator / Receipt Readiness

- **Receipts on disk:** 3 in `/Users/sab-mini/repos/gddp-config/verification-runtime-live/gddp-runtime/`
- **Exported evaluations:** `evaluations.yaml` exists for `gddp-runtime` and `test-project`
- **Latest gddp-runtime verdict:** `pass` for `canary-retry-proof` (2026-07-12)
- **Evaluator lanes:** criteria + integrity lanes operational; worst-of combination producing verdict receipts
- **Grade:** ready to evaluate returned work; no evaluator blockers observed

## 6. Graph / Capability Readiness

The canonical capability spine is documented in `docs/Neutral Executor Graph Plan` (draft; acceptance criteria unchecked).

| Capability Node | Status | Evidence |
|---|---|---|
| `neutral-executor-contract` | 🟡 Implemented, not yet formally accepted | Executor protocol + `JulesCliAdapter` + session lifecycle + 13 new tests (handoff 047) |
| `direct-jules-round-trip` | 🟡 Not yet validated with real Jules CLI session | Adapter is readied; next canary is a real dispatch → poll → collect → commit → evaluate |
| `immediate-evaluator-round-trip` | ✅ Working | Multiple `pass` receipts exist; automatic evaluation on returned evidence |
| `concurrent-node-flow` | 🟡 Partial | Multiple jobs exist in queue, but not yet proven as independent real-node round trips |
| `graph-frontier-operations` | 🟡 Partial | `node_status.py` shows queue state; full frontier unlock logic still draft |

## 7. Risk Flags

1. **Orphaned running jobs from 2026-07-11** — the new reconciler must be exercised to prove it can poll/collect/cancel them safely. Until then, they consume capacity and may confuse state.
2. **Unprocessed `received` events (6)** — intake is collecting events faster than heartbeat is classifying/dispatching. This is expected if heartbeat is idle, but it should be monitored so the queue does not age out.
3. **Failed jobs without evaluator results** — need triage to decide if they are retry attempts or corrective-node candidates.
4. **Graph still draft** — the five capability nodes have unchecked acceptance criteria. Real progress exists, but graph truth has not been formally advanced by human acceptance.
5. **Graph slightly stale** — `graphify-out` was built from `d066728`; current HEAD is `0a95a29` (README edits only, so low risk). Run `graphify update .` if README structure is expected to affect graph navigation.

## 8. Recommended Next Actions

1. **Reconcile the 4 running jobs** — run the heartbeat reconciler (or a manual poll/collect pass) to determine which are truly active and which are orphaned.
2. **Triage the 2 failed jobs** — inspect their artifacts; decide retry vs. corrective node.
3. **Accept or reject the 2 `pass` nodes** — `canary-retry-proof` and `verdict-confidence-split` have evaluator "Proceed to accept_node" guidance; only human acceptance changes graph truth.
4. **Run the direct Jules CLI canary** — dispatch a small real node through `JulesCliAdapter` to validate the `direct-jules-round-trip` capability.
5. **Process the 6 `received` events** — let heartbeat classify/map them, or decide to ignore/scope-block them deliberately.
6. **Update graphify** after the next meaningful code change to keep graph navigation fresh.

## 9. Readiness Verdict

The runtime is **operationally ready** for the next canary: the test suite is green, the evaluator produces receipts, the intake/heartbeat services are loaded, and the executor-neutral session lifecycle is implemented and tested. The main blockers are **human review backlog** and **unreconciled running jobs**, not technical failures. The system is in a healthy state to attempt the first real `direct-jules-round-trip` through the CLI adapter.

---
*Report generated by Droid on 2026-07-18. All data sourced from the local working tree, `db/queue.db`, and launchd.*
