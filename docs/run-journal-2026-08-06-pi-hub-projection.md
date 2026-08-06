# Run journal — pi-hub-projection (2026-08-06, sab-mini)

One droid mission, diamond graph (01 → {02, 04} → 03), executor droid.
Overseer: Pi (kimi-k3), hands-off unless fire; watchers in /tmp/pi-hub-watch.{sh,log}.

## Timeline

- 11:47 — dispatch events for all 4 nodes; planner correctly dispatched only
  node-01 (rest dep-blocked). Frontier math validated.
- 11:49 — tick claimed node-01-sqlite-projection, attempt 0, droid pid 67367.

## Findings + hardening (in run)

1. **Split-brain executor config (fixed in-run).** The launchd heartbeat plist
   embeds a *snapshot* of GDDP_* vars rendered at arm time
   (`render_plist` in deploy/mini-heartbeat/bin/common.sh). Editing
   `env/gddp.env` alone does nothing for ticks until re-arm. I pinned the
   droid model id in the env file pre-run; node-01 still dispatched with the
   old `-m grok-4.5`. Working (alive, generating), so left to finish;
   re-armed via kit (`MINI_HEARTBEAT_ARM=1 arm.sh` — designed for this:
   "Re-render in case env changed"). Verified new plist carries
   `custom:Grok-4.5-sub-(Hermes)-0`; nodes 02+ will use it. **Rule: env
   edits require re-arm.**
2. **No liveness signal in spool.** 8+ min into the droid run, attempt-dir
   stdout/stderr are 0 bytes (droid writes on exit); `ps` is the only proof
   of life. Reconcile polls durable exit state, so a hung droid looks
   identical to a working one until it exits. Noted for executor
   wall-clock timeout work (postmortem action #10) and for the projection
   graph itself (liveness is an observability input).
3. Python 3.9 (Xcode framework) runs local_agent_executor — stdlib-only
   constraint is load-bearing; keep it.
