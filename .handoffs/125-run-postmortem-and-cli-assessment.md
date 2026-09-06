# 125 — aa-hub-create / orchestrator-smoke run postmortem, Jules CLI branches assessed

------------------------------------------------ Agent Section START

Date: 2026-09-06
Worktree: /home/sab-mini/gddp-runtime (+ /home/sab-mini/gddp-config, /home/sab-mini/aa-cli) on khoj-38-west
Branch: main (all three)

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

The 2026-09-05 run produced zero graph-governed node results: `nav-input-repair` had two cancelled cursor_cli jobs (09:51Z, 12:25Z), the node's actual work landed on aa-cli main as `def9f82` at 11:44Z (Grok 4.6 via Cursor, no GDDP attempt ref), and `smoke-alpha` was deferred by the operator with reason "complete abandonment of governance led to the smoke passing". Sab's follow-up `2275f81` (turn timeout 1800→18000) carried a `18000.0.0` typo that broke `main` at import; the systemd heartbeat on this VM failed every tick from 05:53Z until this session's `38ccf2b`. Jules's two gddp-config CLI branches are unmerged: `ad7e61d` is an empty commit (tree == parent), `6489d94` sits on a 12-day-stale base and its live pieces (multi-spool watch, steer capability refusal, cursor_cli mode) already exist on main via Sab's own commits.

### Scope touched (One file per line, +/- for only what was changed)

~ scripts/adapters/cursor_cli_adapter.py (`18000.0.0` → `18000.0`, one token)

### Constrained areas touched (none / list + justification)

none. Graph untouched; no job or node state changed; no gddp-config or aa-cli edits.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

gddp-runtime main == origin/main at 38ccf2b + this handoff. gddp-config main == origin/main at f34a8f3 (clean). aa-cli main clean.

### Artifacts (Filepath - Description, 1 line max per artifact)

- node_status_history/aa-hub-create/nav-input-repair.jsonl - ready→pending 11:33Z "infra failure" (only ledger record; node is `ready` in config via hand edit, rule keeps it inert)
- node_status_history/orchestrator-smoke/*.jsonl - alpha provisional→deferred, beta/gamma ready→pending, 11:32Z
- aa-cli def9f82 - the node-0 work, on main, outside the graph
- gddp-config origin/fix-gddp-cli-ergonomics-10837814615865469817 (ad7e61d) - empty Jules commit
- gddp-config origin/jules-7527605291157963530-dfb36d52 (6489d94) - stale-base Jules commit; unique content: dead `[f]/[v]/[q]` watch keys (`terminal.cbreak` is absent, `hasattr` guard skips them), `rapid_add --validate` prompt, one test
- jobs/job_20260906T*/ - 35 empty dirs created by the `--all-active` VM heartbeat tonight (every tick, per active project, before executor preflight defers on missing GDDP_PI_RPC_MODEL)
- db/queue.db events `evt_frontier_20260906T060450_nav-input-repair_9f1cbe` - VM heartbeat injected a cursor_cli dispatch for `nav-input-repair` at 06:04:50Z once main imported again; every tick since claims it then crashes at `state_recorder.insert_job` (`jobs` lacks `expected_base_commit_sha`; VM db is behind the 5-column migration handoff 123 applied on the Mac). The schema crash is the only thing between this VM and a second, unintended attempt on a node whose work already sits on aa-cli main. Left untouched on purpose: migrating the db or stopping the timer is an operator call.

### Session 2 addendum (07:40–08:00Z)

Added `gddp timeline <project> [node]` in gddp-config (73beec7 module + wiring, eba48ce tests; 11 new tests pass; 2 pre-existing `test_gddp.py` failures reproduce on the parent commit). Read-only: graph file + git authorship, ledger, queue.db jobs + heartbeat events, spool attempts, evaluator receipts, target-repo commits (agent-authored without a `result(job=`/`accept(` marker flagged OUTSIDE GDDP), systemd/launchd heartbeat health, plus "what this host cannot see". Against aa-hub-create it reports the four Sep 5 facts (hand-edit vs ledger, claimed dispatch with no job, ungoverned `def9f82` et al., failing heartbeat) in 12 lines. Operator rulings this session: the interactive menu is the human's channel into graph truth and stays; positional dispatch untouched; VM `gddp-heartbeat.timer` stopped by Sab (inactive). `verification/pi-harness-execution/evaluations.yaml` and `verification/vault-doctor/auth-node.json` in gddp-config were rewritten by the 07:46Z heartbeat tick and are left uncommitted for Sab to judge. Jules branches untouched.

### Session 2, menu cut (08:00–08:10Z)

gddp-config a3e3128: `gddp` opens on the graph picker (six-group front page removed; Esc → heartbeat/config controls page); the graph hub prints graph status, last 8 timeline entries, and "what is wrong" above its unchanged n/d/w/m keys. `interactive_graphs` deleted (folded into `interactive_menu`). Menu path to act on a node is now picker → hub(truth) → nodes → node; was front page → g → picker → hub → n → node. gddp-config suite: 313 passed, same 2 pre-existing failures. Sab's ruling stands: the operator menu is the human channel into graph truth; simplify, never add.

### Session 2, hub fit (08:30–08:50Z)

Sab caught that the first hub cut pushed header + statuses off screen with no scroll keys. Walked the real TUI via pexpect+pyte (`/tmp/gddp_walk.py`, kept out of repo) at 100x24/104x40/120x30/120x50: picker → hub → nodes → node. gddp-config 10959ae: hub block is one row per line (ellipsis), warnings before history, history sized to leftover rows, footer line `N events · M things unseen · full story: gddp timeline <p>`. Seen and UNCHANGED: nodes page (table + 5 keys), node page (7 actions + prev/next/back/quit; `e evaluation`, `v evaluator`, `m more` are three doors to evidence). Next cut belongs to Sab's call.

### Session 2 close (08:57Z) — operator verdict

Sab's verdict on this session's CLI work: the hub "what happened" block is useless and buried; the approach was "unique fixes" where "basics are best" was wanted. Landed on gddp-config main and left in place for the next agent to keep or revert as a unit: 73beec7 timeline module, eba48ce tests, a3e3128 front page removed, 10959ae hub fit, a9c2a5a live restored on the plane page. Revert path: `git revert a9c2a5a 10959ae a3e3128 eba48ce 73beec7`. Still broken and untouched: heartbeat page is launchd-only (blind on Linux hosts; the deploy kit `common.sh:94` refuses non-Darwin), so the menu can neither see nor stop a systemd timer. Basics Sab asked for, in his words: observability first (live, across graphs, on the first screen), fewer pages, no new mechanisms.

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Validation: 965 passed, 10 failed/deselected all `flask` missing on this host (intake server, frozen). Operator decisions pending: (a) whether `def9f82` is adopted via `jobs adopt` or `nav-input-repair` is re-attempted on top of it; (b) whether the Jules branches are closed (recommended: both — nothing in them survives a rebase onto main worth keeping beyond the `--validate` flag); (c) whether the VM heartbeat keeps `--all-active` given it defers 7 events and writes 6 empty job dirs per tick. CLI simplification proposal is in the session's final response, not yet a node.

------------------------------------------------ Agent Section END

------------------------ Do NOT edit this file past this point

## Narrative / Trajectory (SAB ONLY)

### Intent going into/at start of session

### Interpretation of how the session went

### Friction experienced or anticipated

### What's Next (Momentum or Lack Thereof)
