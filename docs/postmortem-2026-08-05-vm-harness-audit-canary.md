# Post-mortem — vm-harness-audit canary (2026-08-04 → 05, khoj-38)

Scope: the first droid-executed graph (`vm-harness-audit`, 5 nodes) run on the
khoj-38 VM through the GDDP heartbeat, ~2026-08-05 00:40 → 02:37 UTC. Jobs
`job_20260805T0041205689e1ea55d405` (node-01) through
`job_20260805T0221253…` (node-05); receipts `res_ses_*` per node. In scope:
the automated dispatch → execution → evaluation → provisional/frontier path.
Out of scope (not exercised): human acceptance of any node; merge of any
result into `main`.

## Executive summary

The canary's purpose was to practice dispatch and autonomy, and the operator
deliberately chose full autonomy: armed timer, `frontier_auto_advance`,
provisional flow with human review trailing. That design executed as
intended — five nodes executed by droid, evaluated, and written
`provisional`, with the frontier injecting each dependent's dispatch and no
automated path writing `complete`. Human acceptance is the *next* phase by
design, not a gap in this one. Scheduler-driven dispatch ran automatically
between operator interventions over ~90 minutes; the interventions were
defect repairs, not autonomy corrections. The run exposed five defects
(four runtime, one platform), all diagnosed and patched during the window;
each fix is listed with its verification record below.

## Final state (verified 02:37 UTC)

- Node statuses: 01–05 all `provisional` (graph files, committed `d6051d1`).
- Jobs: node-01/02/03/05 jobs `awaiting_review`; node-04's first job `failed`
  (executor-label defect, below), second job `awaiting_review`.
- Heartbeat: idle, `No active projects` — correct terminal state with no
  pending work.
- Reports: `reports/01..05` exist on result refs, not `main`. `main` holds
  only report 01, from an executor-side double commit outside the worktree
  contract, not from any merge step.

## Timeline (UTC, evidence in parentheses)

1. 00:41 — node-01 dispatched via operator-injected event (event
   `evt_dispatch_…_1909f6`, `manual_inject`).
2. 00:44 — node-01 droid exec completes (~175s); report committed (commit
   `325c7f1` on main via executor double-commit; result ref `4345bd8`).
3. 00:45 — evaluation crashed: verifier `TypeError` on YAML-mapping
   constraint (tick journal; fix 1).
4. 01:10 — systemd user timer armed (`gddp-heartbeat.timer`, 300s cadence).
5. 01:13 — node-01 re-evaluated: verdict pass, provisional; frontier injected
   node-02 event (journal; event `evt_frontier_…_bdafc2`).
6. 01:22 — node-02 pass/provisional; node-03 **not** advanced (tick journal
   shows no frontier print; fixes 2–3).
7. 01:30 — node-03 injected + dispatched (journal).
8. 01:39 — node-03 pass/provisional; `frontier advanced after evaluation
   finalize` observed; node-04 event injected (journal).
9. 01:42 — node-04 dispatched **by timer**; executor died instantly
   ("exited without durable exit state"; spool had only `command.json`,
   `packet.json`, `supervisor.pid`). Cause: systemd `KillMode=control-group`
   reap (fix 5).
10. 01:53–01:59 — attempts 1–2 died identically (pre-fix dispatches);
    `KillMode=process` installed 01:54:31; attempt 3 survived the tick
    (spool advanced to full lifecycle incl. `exit.json`; systemd logged
    "Unit process … remains running after unit stopped").
11. 01:59 — attempt 3 exited 1: argv was **pi** (`/usr/bin/pi --model
    zai/glm-5.2`), not droid — retry redispatched from the session's
    `local_subprocess` label (spool `command.json`; fix 4). Pi failed on a
    macOS keychain reference in the VM's mirrored models.json.
12. 02:04 — job failed out (attempt budget); operator injected a fresh
    node-04 dispatch (`evt_dispatch_…_32bafb`).
13. 02:10 — fresh node-04 job dispatched; argv confirmed `droid exec`
    (spool `command.json`); completed `returncode 0` (`exit.json`).
14. 02:18 — node-04 pass/provisional; node-05 event injected (journal).
15. 02:21 — node-05 dispatched, base-chained on node-04 result (journal).
16. 02:28 — node-05 pass/provisional (journal). Loop idle thereafter.

## Contributing conditions (blameless)

- **YAML authoring ergonomics.** `Key:`-style constraint prefixes parse as
  mappings; the authoring validator accepted them, and the verifier was the
  first surface that objected — the most expensive place to learn.
- **Tick-phase ordering assumption.** The frontier check predated evaluation
  finalize, and the activity query reads only DB state — a project whose
  work settled mid-tick became invisible to later ticks.
- **Read-through caching without invalidation points.** The graph reader
  cache had no defined moment to refresh within a tick.
- **Module-level executor identity.** One label served two executors; the
  retry path trusted the label, so identity loss stayed latent until the
  first droid failure.
- **Platform default mismatch.** systemd's default reaping assumes services
  own their cgroup; the heartbeat is a spawner whose children must outlive it.
- **Coordination mechanism.** Cross-pane assistance arrived via operator
  relay, which did not consistently preserve target environment, bounded
  scope, primary-evidence references, or a durable return artifact.
  Hypotheses reached the diagnosing session with uneven provenance; one
  correct diagnosis arrived unverifiable (cgroup reaping — later confirmed),
  and one reported fix could not be located in any checkout afterward.
  Consistent with action item 6 of `postmortem-canary-scope-2026-07-12`:
  incoming claims are uncorroborated until primary-sourced.

## What worked (evidence-tied)

- Verdicts are evidence, not truth: no automated path wrote `complete`;
  all five nodes remain `provisional` awaiting human acceptance (graph
  files, `d6051d1`).
- Frontier auto-advance + base-chaining operated as designed on provisional
  dependencies (journal lines for nodes 02–05).
- The retry doctrine held: redispatches re-attempted node-04 unchanged; the
  failure findings were the fix-list.
- The Linux heartbeat port (systemd units) is now documented kit
  infrastructure (`d45afaf`, `deploy/mini-heartbeat/systemd/`). All manual
  runner invocations on the VM sourced `gddp.env` first, preserving the
  kit's no-raw-runner intent.

## Evidence gaps (open)

- **The run's real miss was mine, not the system's: during execution I
  checked droid's reports for existence and verdicts, not substance.**
  Node-02's extension inventory and node-04's PTY capture were not
  corroborated against primary sources by anyone yet. That is precisely
  what the human review gate is for, and it hasn't happened — so nothing is
  late; but the operator's read of these two reports should treat them as
  unverified until checked (action A2).
- **Whether existing verification surfaces *could* have established those
  claims is undetermined.** Criteria, evaluator context, and supplied
  artifacts have not been audited for this gap (action A3).

## Verified recovery record

| Fix | Commit | Regression evidence | Deployed | Observed post-fix behavior |
|---|---|---|---|---|
| 1. Verifier crash on non-string YAML items | `185e6fe` | verification suite 216 passed; live repro of warning path | khoj-38 pull | node-01 re-evaluation passed |
| 2. Frontier re-check after finalize | `66f4ae5` | heartbeat suite 111 passed | khoj-38 pull | see fix 3 — joint behavior below |
| 3. Reader-cache invalidation | `9991c8e` | heartbeat suite 111 passed | khoj-38 pull | `frontier advanced after evaluation finalize` at 01:39, 02:18; node-04/05 events injected |
| 4. Executor label for retries | `727bb7a` | full suite 477 passed; attribute check (`droid`/`local_subprocess`) | khoj-38 pull | fresh node-04 dispatch argv = `droid exec` (spool `command.json`) |
| 5. systemd `KillMode=process` | unit on khoj-38; upstreamed `d45afaf` | attempt-3 spool full lifecycle; systemd "process remains running" log | khoj-38 daemon-reload | timer-dispatched node-04 completed `returncode 0` |

## Action items

| # | Bounded action | Owner | Completion evidence | Status |
|---|---|---|---|---|
| 1 | Content-audit node-02/node-04 reports against criteria + primary sources | human reviewer (assignee TBD) | quoted claims, corroboration refs, accept/revise/defer decision | open — acceptance pending |
| 2 | Determine why verification evidence didn't establish those claims; correct criteria/context only on reproduced gap | evaluator maintainer (operator approves contract changes) | path-cited reproduction + regression fixture | open investigation — no new reviewer role approved |
| 3 | `gddp project validate` rejects non-string criteria/constraints | validation maintainer | failing fixture → passing test + actionable error | proposed bounded correction |
| 4 | Pin retry-budget semantics for executor-failure redispatch (`retry_budget: 2` vs observed attempt count) | runtime maintainer | written semantics + ledger-backed test | open investigation |
| 5 | Verify droid streaming output before any spool change | executor maintainer | capability evidence, durability/redaction check | decision required — not authorized |
| 6 | Collaboration packet: target host, repro, scope, evidence requirements, return artifact; returned claims stay hypotheses until tied to durable refs | run lead (runbook) | one run using the packet, claims traceable | proposed runbook experiment |
| 7 | Per-node `executor_model` field (e.g. synthesis → Codex Sol) | operator decision first | proposal only — contract change | proposed, not approved |
| 8 | Run-2 candidate: same graph under `droid exec --mission` (orchestrator/worker/validator) | operator decision | packet-stdin semantics pre-check first | proposed, not approved |
| 9 | Rotate `DEEPSEEK_API_KEY` (appeared in transcripts during setup) | operator | new key issued, old revoked, VM env updated | open |
| 10 | Per-node/executor wall-clock timeout — nothing bounds a hung executor today | runtime maintainer (operator approves schema) | timeout field + executor-enforced kill + regression test | proposed, not approved |
