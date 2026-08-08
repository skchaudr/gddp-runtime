# How to monitor GDDP

Use the deployment kit and operator surfaces; do not infer health from one process or one file timestamp.

## Start with smoke

```bash
cd /Users/sab-mini/repos/gddp-runtime
bash deploy/mini-heartbeat/bin/smoke.sh
```

Smoke verifies runtime/config paths, project YAML, DeepSeek and webhook secret resolution without printing values, optional GitHub/Pi availability, launchd registration and rendered-env drift, intake health and invalid-HMAC rejection when listening, and one heartbeat tick. A stopped intake is a warning during dormant setup; it is a failure condition for an armed production plane.

## Services and logs

On `sab-mini`:

```bash
launchctl print "gui/$(id -u)/com.gddp.intake"
launchctl print "gui/$(id -u)/com.gddp.heartbeat"
tail -n 100 ~/Library/Logs/gddp-intake.log
tail -n 100 ~/Library/Logs/gddp-intake.err.log
tail -n 100 ~/Library/Logs/gddp-heartbeat.log
tail -n 100 ~/Library/Logs/gddp-heartbeat.err.log
```

The heartbeat interval is 300 seconds, so allow one cadence before declaring a queued event stuck. On Linux use:

```bash
systemctl --user status gddp-heartbeat.timer gddp-heartbeat.service
journalctl --user -u gddp-heartbeat.service -n 100 --no-pager
```

## Intake health

```bash
curl -s http://127.0.0.1:5050/health
```

Healthy production output has `status: ok` and webhook verification enabled. A 503 with `webhook_secret_unresolved` is a security failure, not an availability-only warning. Test invalid HMAC through `smoke.sh`; do not handcraft a real secret into shell history.

## Queue and WAL freshness

The queue is `/Users/sab-mini/repos/gddp-runtime/db/queue.db` on this checkout and `~/repos/gddp-runtime/db/queue.db` on production. It uses SQLite WAL. The main database mtime may move only at checkpoint, while committed rows continue accumulating in `queue.db-wal`; main-file mtime is therefore not a reliable freshness signal. Query application timestamps such as `events.received_at`, `jobs.created_at`, and `executor_sessions.updated_at`.

Do not copy only `queue.db` to inspect or migrate a live plane. Use SQLite's online `.backup`, which includes committed WAL content.

## Spool lifecycle

The default direct-executor spool is `jobs/local-subprocess-spool/<session-id>/`. Markers accumulate in this order:

| Marker | Meaning |
| --- | --- |
| `command.json`, `packet.json` | Attempt and immutable packet were persisted |
| `supervisor.pid` | Detached supervisor was launched |
| `pid` | Worker process was started |
| `stdout`, `stderr` | Durable worker output |
| `exit.json` | Terminal return code/cancellation state was persisted |

Only `command.json`, `packet.json`, and `supervisor.pid` with no `exit.json` can indicate an executor reaped before durable exit. This exact shape exposed the wrong systemd `KillMode`. Check whether PIDs are live before classifying the attempt.

## Operator state surfaces

The supported operator command is `gddp`; its runtime job backend is `/Users/sab-mini/repos/gddp-runtime/scripts/jobs_status.py`.

```bash
gddp jobs list
gddp jobs show <job-id-or-unique-node-id>
gddp node show <node-id>
python3 /Users/sab-mini/repos/gddp-runtime/scripts/jobs_status.py results
```

`jobs show` combines evaluator output, job state, executor-session records, result/base SHAs, errors, timestamps, and a read-only local spool probe. Compare:

- graph node state from `gddp node`,
- runtime job/queue state from `gddp jobs`,
- durable executor state in the spool.

They are distinct kinds of truth. A result can be `awaiting_review` or a node can be `provisional` without being human-accepted `complete`. `jobs_status.py` may update runtime rows but never graph/node status.
