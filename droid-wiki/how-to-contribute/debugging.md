# Debugging

Common failure modes, log locations, and the first questions to ask when `gddp-runtime` misbehaves. The emphasis is on durable evidence (spool files, SQLite rows, receipts) over ephemeral stdout.

## Where to look first

1. **Is the heartbeat armed?** On `sab-mini`, `launchctl list | grep gddp`. On Linux, `systemctl --user status gddp-heartbeat.timer gddp-heartbeat.service`.
2. **What does `jobs_status` say?** `python3 scripts/jobs_status.py show` gives the runtime view. If the job you care about is not in the DB, intake or dispatch never fired.
3. **Spool lifecycle files.** Each local/Droid adapter attempt writes to its spool dir (default under `jobs/` or `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR`). Look for `exit.json`, `packet.json`, stdout/stderr logs. A missing `exit.json` means the worker died before writing one.
4. **Mission session state.** `db/mission-sessions/` (or `GDDP_MISSION_SESSION_DIR`). Factory mission has its own durability trail.
5. **SQLite.** `db/queue.db` (WAL mode). Tables of interest: `events`, `jobs`, `queue_records`, `results`, `decision_results`, `executor_sessions`.

## Log locations

| Host | Where |
| --- | --- |
| `sab-mini` (macOS) | `~/Library/Logs/gddp-heartbeat/` (launchd stdout/stderr), intake log next to it |
| `sab-mini` (intake) | Same launchd log directory; the intake server runs under launchd alongside the heartbeat |
| Linux (mini-heartbeat systemd) | `journalctl --user -u gddp-heartbeat.service` and `gddp-intake.service`. Timer runs log under `gddp-heartbeat.timer`. |
| Runtime spool (all hosts) | `jobs/<job-id>/` per attempt — packet, logs, `exit.json` |
| Factory mission | `db/mission-sessions/` or `GDDP_MISSION_SESSION_DIR` |
| Factory mission state | `~/.factory/missions/` or `GDDP_FACTORY_MISSION_DIR` |

On Linux, journald is the canonical source. On macOS, the launchd plist writes stdout/stderr to the `Logs/` directory listed in the plist under `StandardOutPath` / `StandardErrorPath`.

## Common failure: missing `GDDP_LOCAL_SUBPROCESS_ARGV`

The local/Droid adapter launches its worker from the JSON-encoded argv in `GDDP_LOCAL_SUBPROCESS_ARGV`. If it is unset or malformed:

- The dispatcher creates a job row and attempts to launch.
- The adapter fails before exec-ing the worker.
- The job lands in a failed state with a spool that has no `exit.json` (because nothing ever exec'd).

This is the classic "failed job before any executor launches" failure. It almost always means the operator ran `python -m scripts.runtime.heartbeat.runner` directly instead of using [`deploy/mini-heartbeat/bin/arm.sh`](../../deploy/mini-heartbeat/bin/arm.sh), which sources `deploy/mini-heartbeat/env/gddp.env` and sets the argv.

**Fix:** arm via the kit. If you must run the runner directly for debugging, source the env first:

```bash
source deploy/mini-heartbeat/env/gddp.env
source deploy/mini-heartbeat/bin/common.sh
python3 -m scripts.runtime.heartbeat.runner --project ... --repo ... --config-path ...
```

## Common failure: `KillMode` on systemd

The mini-heartbeat systemd units use `KillMode=process`. This is not optional. The oneshot tick spawns the runner which in turn dispatches long-running workers. If `KillMode` were `control-group` (the systemd default), stopping the timer's tick unit would `SIGTERM` the entire process group, including the worker that was just launched. The worker dies mid-flight, the reconciler never sees a clean exit, and the job is stuck.

If you see workers dying exactly when the tick ends, check:

```bash
systemctl --user cat gddp-heartbeat.service
# Confirm KillMode=process is set
```

On macOS launchd this is not an issue because launchd uses different process-group semantics.

## Common failure: scope blocked by `awaiting_review`

The dispatcher will not dispatch a second job for a node that already has an active or `awaiting_review` job. If a node appears stuck:

1. `python3 scripts/jobs_status.py show` — look for the node in `awaiting_review` or `executing` state.
2. If the job is genuinely abandoned (e.g., the executor died and no receipt exists), the human must decide: accept, retry, block, or defer.
3. Do not silently re-dispatch from outside the review path. The reconciler and completion discipline assume one active attempt per node.

## Common failure: HMAC 401 on intake

Intake validates the webhook signature against `GITHUB_WEBHOOK_SECRET`. A 401 means:

- The secret on the armed host does not match the secret GitHub is signing with.
- The request is not actually from GitHub (replay or probe).
- The request body was truncated or modified in transit.

To diagnose:

1. Confirm `GITHUB_WEBHOOK_SECRET` is set and matches the value configured in the GitHub webhook settings for the repo.
2. Check the intake log for the raw signature and the computed signature. If you have `GDDP_INTAKE_INSECURE=1` set in dev, the check is skipped — but do not run that in production.
3. Rotate the secret in both GitHub and the deploy env, then restart intake.

## Common failure: spool lifecycle files

The local adapter writes spool artifacts under `jobs/<job-id>/`:

- `packet.json` — the `NodePacket` sent to the worker (written before launch).
- stdout/stderr logs.
- `exit.json` — written by the worker (or the adapter on its behalf) with the exit status.
- `result.json` — adapter-collected return (commit ref, patch, etc.).

If `exit.json` is missing but the worker process is gone, the worker crashed before cleanup. Check stderr for the real failure. If `packet.json` is missing, dispatch never reached the adapter — the issue is upstream (classifier, scope, dispatcher).

If spool files persist across retries, the reconciler uses the latest attempt. Do not manually delete spool files to "clean up"; they are evidence.

## Common failure: scope blocked awaiting_review

This overlaps with the previous section but is worth calling out as its own failure:

- The classifier requires an explicit `node: <id>` tag. If an event arrives without one, it is parked, not dispatched.
- The scope checker blocks duplicate work for the same node while an attempt is active or awaiting review.
- The reconciler treats `awaiting_review` as active.

When a node appears blocked, check `jobs_status` for the live attempt. The fix is almost always a human review action, not a re-dispatch.

## Common failure: mission push-guard bypass

The Factory mission adapter detects when a feature branch result is reachable from a protected branch (i.e., someone pushed to `main` or the feature branch was merged before the adapter could quarantine). The guard is post-hoc: it runs `ls-remote` to get the live tip and quarantines if the commit is reachable.

If you see a mission result flagged as `quarantined` unexpectedly:

1. Confirm the live `ls-remote` tip is what you expect.
2. Check `scripts/adapters/test_mission_push_guard.py` for the expected quarantine behavior.
3. The absolute `git` binary + `-c core.hooksPath=/dev/null` bypasses PATH shims and pre-push hooks; the post-hoc detection in `mission_evidence._protected_branch_push_reasons` is the active safeguard.

## Debugging the heartbeat runner

For local debugging (never as the production entrypoint):

```bash
source deploy/mini-heartbeat/env/gddp.env
source deploy/mini-heartbeat/bin/common.sh
python3 -m scripts.runtime.heartbeat.runner \
  --project <project-id> \
  --repo <owner/repo> \
  --config-path /path/to/gddp-config
```

The runner logs each tick phase: reconcile, frontier, claim, plan, dispatch, record. Look for the phase where it stops or errors.

If the runner hangs, it is almost always a SQLite lock. Check for other writers with `lsof db/queue.db` or `fuser db/queue.db`. The coordinator uses `BEGIN IMMEDIATE` for reservations; if another writer is mid-transaction, the runner waits.

## Debugging the evaluator

The evaluator runs two lanes: deterministic criteria floor + semantic + integrity, combined worst-of into a `VerdictReceipt`.

- Criteria lane failures surface as specific criterion failures in the receipt. Read the receipt JSON.
- Integrity lane can only preserve or worsen the criteria verdict. If integrity is the only failure, the criteria lane must have passed.
- Evaluator-triggered retries must cite a concrete repo path, graph node id, or canonical document. If a retry was triggered without citation, the evaluator has a bug.

The evaluator deliberately excludes `AGENTS.md` from its context. It reads README, project brief, foundational node, and DAG neighbors. If an evaluator verdict cites `AGENTS.md`, something is wrong with the context assembly.

## Related

- [Testing](testing.md) — what to run before claiming done
- [Tooling](tooling.md) — `init_db`, `replay`, `rollback`, smoke/arm/disarm
- [Development workflow](development-workflow.md) — definition of done
- [Patterns and conventions](patterns-and-conventions.md) — hard boundaries
- [Deployment](../deployment/index.md) — production topology and log paths
- [Overview — architecture](../overview/architecture.md) — component map
