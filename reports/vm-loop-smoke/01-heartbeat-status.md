# VM gddp heartbeat deployment status

- **Host:** khoj-38
- **Captured at:** 2026-08-08T02:42:26Z (UTC)
- **Node:** `node-01-heartbeat-status`
- **Job:** `job_20260808T02414846f023af51e6a4` (attempt 0)
- **Base commit:** `8ef04646f71887c3ea96146c7a835c2ef70b3e8e`
- **Runtime root:** `/home/sab-mini/gddp-runtime`
- **Unit files:** user systemd (`~/.config/systemd/user/`), mini-heartbeat Linux port

## Summary

The VM control plane heartbeat is alive:

| Surface | State |
| --- | --- |
| `gddp-heartbeat.timer` | **active (waiting)**, enabled; interval mirrors launchd 300s |
| `gddp-heartbeat.service` | oneshot tick; last run **exited 0/SUCCESS** at 02:41:48 UTC |
| Last tick work | dispatched this node job to `local_subprocess` for project `vm-loop-smoke` |
| `db/queue.db` | present (131072 bytes); 7 tables listed below |

## `systemctl --user status gddp-heartbeat.service`

```text
○ gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port)
     Loaded: loaded (/home/sab-mini/.config/systemd/user/gddp-heartbeat.service; static)
     Active: inactive (dead) since Sat 2026-08-08 02:41:48 UTC; 9s ago
 Invocation: fc4fd4df63e94d4786694834308fdc48
TriggeredBy: ● gddp-heartbeat.timer
    Process: 37352 ExecStart=/usr/bin/bash -lc source /home/sab-mini/gddp-runtime/deploy/mini-heartbeat/env/gddp.env && exec /usr/bin/python3 -m scripts.runtime.heartbeat.runner --all-active --config-path /home/sab-mini/gddp-config (code=exited, status=0/SUCCESS)
   Main PID: 37352 (code=exited, status=0/SUCCESS)
      Tasks: 38 (limit: 28746)
     Memory: 205.4M (peak: 212.9M)
        CPU: 4.279s
     CGroup: /user.slice/user-1001.slice/user@1001.service/app.slice/gddp-heartbeat.service
             ├─37359 /usr/bin/python3 -m adapters.local_subprocess_adapter --run-attempt /home/sab-mini/gddp-runtime/jobs/local-subprocess-spool/job_20260808T02414846f023af51e6a4-node-01-heartbeat-status-attempt-0-b24287c32f59434bb8d4e7c6cbe3ab87 --start-fd 6
             ├─37361 /usr/bin/python3 /home/sab-mini/gddp-runtime/scripts/local_agent_executor.py -- /usr/bin/pi --model xai/grok-4.5 ...
             └─37364 pi

Aug 08 02:41:48 khoj-38 bash[37352]: Found 1 pending event(s).
Aug 08 02:41:48 khoj-38 bash[37352]: Processing: evt_dispatch_20260808T023734_node-01-heartbeat-status_c00907 (issue.opened)
Aug 08 02:41:48 khoj-38 bash[37352]:   → job created: job_20260808T02414846f023af51e6a4
Aug 08 02:41:48 khoj-38 bash[37352]: Dispatching 1 job(s) in parallel.
Aug 08 02:41:48 khoj-38 bash[37352]: Recording: evt_dispatch_20260808T023734_node-01-heartbeat-status_c00907 (node-01-heartbeat-status)
Aug 08 02:41:48 khoj-38 bash[37352]:   → dispatched to local_subprocess
Aug 08 02:41:48 khoj-38 bash[37352]:   → executor session: local_subprocess/job_20260808T02414846f023af51e6a4-node-01-heartbeat-status-attempt-0-b24287c32f59434bb8d4e7c6cbe3ab87
Aug 08 02:41:48 khoj-38 bash[37352]: Heartbeat complete.
Aug 08 02:41:48 khoj-38 systemd[1471]: gddp-heartbeat.service: Unit process 37359 (python3) remains running after unit stopped.
Aug 08 02:41:48 khoj-38 systemd[1471]: Finished gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port).
```

Note: service is a timer-triggered oneshot; `inactive (dead)` after success is expected. Residual cgroup children are the in-flight `local_subprocess` attempt for this node (executor intentionally outlives the tick).

## `systemctl --user status gddp-heartbeat.timer`

```text
● gddp-heartbeat.timer - GDDP heartbeat timer (mirrors launchd StartInterval 300)
     Loaded: loaded (/home/sab-mini/.config/systemd/user/gddp-heartbeat.timer; enabled; preset: enabled)
     Active: active (waiting) since Fri 2026-08-07 22:22:55 UTC; 4h 19min ago
 Invocation: 3f2e6bc6d7514cfab713ae06bc3bac59
    Trigger: Sat 2026-08-08 02:46:48 UTC; 4min 50s left
   Triggers: ● gddp-heartbeat.service

Aug 07 22:22:55 khoj-38 systemd[1471]: Started gddp-heartbeat.timer - GDDP heartbeat timer (mirrors launchd StartInterval 300).
```

## `systemctl --user list-timers`

```text
NEXT                            LEFT LAST                         PASSED UNIT                 ACTIVATES
Sat 2026-08-08 02:46:48 UTC 4min 50s Sat 2026-08-08 02:41:48 UTC 9s ago gddp-heartbeat.timer gddp-heartbeat.service

1 timers listed.
```

(Command: `systemctl --user list-timers 'gddp-heartbeat*' --all --no-pager`. Cadence ~300s matches the unit description.)

## Recent journal lines (`gddp-heartbeat.service`)

Command: `journalctl --user -u gddp-heartbeat.service -n 30 --no-pager`

```text
Aug 08 02:08:48 khoj-38 bash[33324]: No active projects.
Aug 08 02:08:48 khoj-38 systemd[1471]: Finished gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port).
Aug 08 02:14:18 khoj-38 systemd[1471]: Starting gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port)...
Aug 08 02:14:18 khoj-38 bash[33931]: No active projects.
Aug 08 02:14:18 khoj-38 systemd[1471]: Finished gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port).
Aug 08 02:19:48 khoj-38 systemd[1471]: Starting gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port)...
Aug 08 02:19:48 khoj-38 bash[34543]: No active projects.
Aug 08 02:19:48 khoj-38 systemd[1471]: Finished gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port).
Aug 08 02:25:18 khoj-38 systemd[1471]: Starting gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port)...
Aug 08 02:25:18 khoj-38 bash[35674]: No active projects.
Aug 08 02:25:18 khoj-38 systemd[1471]: Finished gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port).
Aug 08 02:30:48 khoj-38 systemd[1471]: Starting gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port)...
Aug 08 02:30:48 khoj-38 bash[36120]: No active projects.
Aug 08 02:30:48 khoj-38 systemd[1471]: Finished gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port).
Aug 08 02:36:18 khoj-38 systemd[1471]: Starting gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port)...
Aug 08 02:36:18 khoj-38 bash[36652]: No active projects.
Aug 08 02:36:18 khoj-38 systemd[1471]: Finished gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port).
Aug 08 02:41:48 khoj-38 systemd[1471]: Starting gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port)...
Aug 08 02:41:48 khoj-38 bash[37352]: Active projects: ['vm-loop-smoke']
Aug 08 02:41:48 khoj-38 bash[37352]: Ready nodes: ['node-01-heartbeat-status']
Aug 08 02:41:48 khoj-38 bash[37352]: Found 1 pending event(s).
Aug 08 02:41:48 khoj-38 bash[37352]: Processing: evt_dispatch_20260808T023734_node-01-heartbeat-status_c00907 (issue.opened)
Aug 08 02:41:48 khoj-38 bash[37352]:   → job created: job_20260808T02414846f023af51e6a4
Aug 08 02:41:48 khoj-38 bash[37352]: Dispatching 1 job(s) in parallel.
Aug 08 02:41:48 khoj-38 bash[37352]: Recording: evt_dispatch_20260808T023734_node-01-heartbeat-status_c00907 (node-01-heartbeat-status)
Aug 08 02:41:48 khoj-38 bash[37352]:   → dispatched to local_subprocess
Aug 08 02:41:48 khoj-38 bash[37352]:   → executor session: local_subprocess/job_20260808T02414846f023af51e6a4-node-01-heartbeat-status-attempt-0-b24287c32f59434bb8d4e7c6cbe3ab87
Aug 08 02:41:48 khoj-38 bash[37352]: Heartbeat complete.
Aug 08 02:41:48 khoj-38 systemd[1471]: gddp-heartbeat.service: Unit process 37359 (python3) remains running after unit stopped.
Aug 08 02:41:48 khoj-38 systemd[1471]: Finished gddp-heartbeat.service - GDDP heartbeat tick (mini-heartbeat Linux port).
```

Timer journal (boot continuity):

```text
Aug 07 22:22:55 khoj-38 systemd[1471]: Started gddp-heartbeat.timer - GDDP heartbeat timer (mirrors launchd StartInterval 300).
```

## `queue.db`

```text
$ ls -la /home/sab-mini/gddp-runtime/db/queue.db
-rw-r--r-- 1 sab-mini sab-mini 131072 Aug  8 02:41 /home/sab-mini/gddp-runtime/db/queue.db
```

`sqlite3` CLI is not installed on this host. Tables via read-only Python:

```text
$ python3 -c 'import sqlite3; c=sqlite3.connect("file:/home/sab-mini/gddp-runtime/db/queue.db?mode=ro", uri=True);
print(" ".join(t for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='"'"'table'"'"' ORDER BY name")))'
artifact_verifications decision_results events executor_sessions jobs queue_records results
```

Equivalent to `sqlite3 queue.db .tables`:

| table |
| --- |
| artifact_verifications |
| decision_results |
| events |
| executor_sessions |
| jobs |
| queue_records |
| results |

## Acceptance checklist

| id | criterion | met |
| --- | --- | --- |
| report-exists | this file exists and is non-empty | yes |
| units-documented | real `systemctl --user status` / `list-timers` for gddp-heartbeat quoted | yes |
| log-lines | recent journal lines for gddp-heartbeat quoted | yes |
| queue-db | `queue.db` exists; tables listed | yes |
