# Entity: Heartbeat

The **heartbeat** is the periodic control plane dispatch mechanism that claims ready nodes from the queue, packages them into node packets, and launches them onto isolated executor sessions.

---

## Invariants & Critical Safety Rules

- **Entrypoint Rule:** NEVER invoke heartbeat runner scripts directly. Use ONLY the mini-heartbeat kit:
  - Arming / Manual invocation: `deploy/mini-heartbeat/bin/arm.sh`
  - Smoke validation: `deploy/mini-heartbeat/bin/smoke.sh`
  - Automated daemon: launchd `com.gddp.heartbeat`
- **Environment Dependency:** The heartbeat requires `deploy/mini-heartbeat/env/gddp.env` via `common.sh`. Direct execution skips `GDDP_LOCAL_SUBPROCESS_ARGV` and causes failed jobs before executor launch.
- **Production Host:** Production heartbeat runs exclusively on `sab-mini`. `pi-big` is disarmed.

---

## Entity Map

| Aspect | Location / Reference |
|---|---|
| **Operating Loop Step** | Step 2 (Dispatch) in [`docs/proposals/LOOP.md`](../docs/proposals/LOOP.md) |
| **Authorized Entrypoints** | [`deploy/mini-heartbeat/bin/arm.sh`](../deploy/mini-heartbeat/bin/arm.sh) · [`deploy/mini-heartbeat/bin/smoke.sh`](../deploy/mini-heartbeat/bin/smoke.sh) |
| **Launchd Service** | `~/Library/LaunchAgents/com.gddp.heartbeat.plist` on `sab-mini` |
| **Runtime Implementation** | [`scripts/runtime/heartbeat/`](../scripts/runtime/heartbeat/) |
| **Capability Gates** | [`scripts/runtime/gate_tokens.py`](../scripts/runtime/gate_tokens.py) |
| **Telemetry Events** | [`events/`](../events/) · [`events/context.md`](../events/context.md) |
| **Host Topology** | [`TOPOLOGY.md`](../TOPOLOGY.md) · [`deploy/context.md`](../deploy/context.md) |
