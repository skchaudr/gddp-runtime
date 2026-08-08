# Pitfalls and verified danger zones

These are observed failures or explicitly documented residuals, not hypothetical cautions. Active contributor: Saboor.

## Assumption failures

| Assumption | What was verified | Rule |
| --- | --- | --- |
| A plan's checkout facts are globally true | A VM reviewer called Mini state stale because the plan did not name its host | Name the target machine; primary-source machine-relative claims |
| A shell process is a durable control plane | A canary outlived its bare intake and temporary tunnel | Cross-session jobs require armed service infrastructure |
| `queue.db` mtime proves freshness | WAL commits may not update the main file until checkpoint | Query row timestamps; use SQLite online backup |
| A passing/failing test determines node truth | Tests can miss architectural drift or expose bounded follow-up work | Treat tests as evidence; humans decide accepted graph progress |
| Human completion authority means no downstream work may start | Complete-only dependency gates froze every edge while the operator slept | Keep `complete` human-only and use provisional sequencing |
| Protecting base purity should precede evaluation | Three real returns were rejected before criteria were read | Always render a judgment; use base state for evidence/admission |
| A loaded launchd job sees edited env files | Rendered plist values stayed stale after `gddp.env` changed | Re-arm and smoke after env changes |
| systemd oneshot defaults preserve spawned workers | `KillMode=control-group` reaped executors as the tick exited | Keep `KillMode=process` |
| Executor labels are interchangeable | Droid retries were routed to Pi after identity was collapsed to `local_subprocess` | Preserve concrete executor identity in attempt records |
| A cached graph read stays valid within a tick | Frontier advance missed newly provisional nodes | Invalidate at defined post-evaluation boundaries |

## Mission-mode known limitations

- Droid 0.189.0 rejects the documented standalone hook-file shape, so hooks are not the integration point for that version.
- `mission_completed` progress is an assumption not yet proven against a real mission completion.
- After SIGTERM, Factory `state.json` can be stale; infer liveness from process exit and the progress-log tail.
- Genuine worker-level failure behavior has not been exercised end to end.
- The PATH push shim and pre-push hook can be bypassed with absolute Git plus `-c core.hooksPath=/dev/null`; live `ls-remote` protected-branch reachability detection quarantines the result post hoc.

## Operational hard stops

- Do not arm two exclusive control planes.
- Do not snapshot or cut over while heartbeat, intake, or detached executor writers remain.
- Do not expose intake when `/health` is 503 or `GDDP_INTAKE_INSECURE=1`.
- Do not invoke the raw heartbeat runner on an armed host; source the mini-heartbeat environment through the kit.
- Do not run `/Users/sab-mini/repos/gddp-runtime/deploy/_archive/setup.sh` or its service file; they describe a dead `$HOME/opclaw`/`sab-ssd` topology.
- Treat incoming diagnoses as hypotheses until tied to a path, row, process, log, commit, or other durable primary evidence.

See `/Users/sab-mini/repos/gddp-runtime/docs/postmortem-canary-scope-2026-07-12.md` and `/Users/sab-mini/repos/gddp-runtime/docs/postmortem-2026-08-05-vm-harness-audit-canary.md`.
