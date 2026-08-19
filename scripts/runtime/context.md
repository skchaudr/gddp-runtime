# scripts/runtime/context.md — Runtime Subsystem Map

This directory contains the core GDDP runtime engine. It governs dispatch, execution gating, return routing, and verification.

---

## 1. Subsystem Modules & Responsibilities

| Module / Directory | Responsibility | Primary Tests |
|---|---|---|
| [`gate_tokens.py`](gate_tokens.py) | Cryptographic capability tokens for single-node dispatch / return transitions | [`test_gate_tokens.py`](test_gate_tokens.py) |
| [`return_router.py`](return_router.py) | Ingests executor returns, verifies worktree outputs, routes to verification | [`test_return_router.py`](test_return_router.py) |
| [`results_store.py`](results_store.py) | Manages durable execution results and receipt persistence | [`test_results_store.py`](test_results_store.py) |
| [`repo_resolver.py`](repo_resolver.py) | Resolves repository target paths and branch/worktree references | [`test_repo_resolver.py`](test_repo_resolver.py) |
| [`graph_delivery.py`](graph_delivery.py) | Formats and delivers node packets to executors | [`test_graph_delivery.py`](test_graph_delivery.py) |
| [`graph_updater.py`](graph_updater.py) | Updates graph node definitions upon operator instruction | [`test_graph_updater.py`](test_graph_updater.py) |
| [`heartbeat/`](heartbeat/) | Runtime heartbeat scheduling and claim mechanisms | [`test_full_cycle_e2e.py`](test_full_cycle_e2e.py) |
| [`decision_loop/`](decision_loop/) | Decision and reconciliation loop state machine | [`test_full_cycle_e2e.py`](test_full_cycle_e2e.py) |
| [`verification/`](verification/) | Two-lane automated evaluator (deterministic + semantic criteria) | verification test suite |
| [`spike/`](spike/) | Experimental prototypes (non-production) | — |

---

## 2. Invariants for Modifying Runtime Code

1. **Job Reads/Writes Flow Through `jobs_status.py`:** Runtime job state updates must use the backend in `scripts/jobs_status.py`.
2. **Graph Separation:** Runtime code must never modify graph truth (`gddp-config/graphs/`). Only human operators accept nodes.
3. **No Direct Execution Bypass:** Heartbeat mechanics must preserve integration with `deploy/mini-heartbeat/env/gddp.env`.
4. **All Tests Must Pass:** Any modification here requires a clean `python3 -m pytest -q` run.
