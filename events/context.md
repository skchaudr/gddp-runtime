# events/context.md — Operational Telemetry Map

This directory holds runtime event logs and telemetry streams emitted by heartbeat passes, webhooks, and executor sessions.

---

## 1. Event Telemetry & Purpose

- **Observability:** Telemetry events provide real-time visibility for operator tooling (`gddp watch`, live dashboards).
- **Non-Authoritative:** Event streams are informational; they do not dictate graph state or replace receipts.
- **Ephemeral State:** All event logs under `events/` are local runtime telemetry and are gitignored.

---

## 2. Invariants

1. **Never Commit Event Logs:** Telemetry files (`events/raw/`, `*.log`) must remain untracked.
2. **Graceful Degradation:** The control plane and operating loop must function even if `events/` is empty or wiped.
