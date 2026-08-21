# PROBE-1 results: headless Factory mission mode

## Setup actually used

- Probe date/time from artifacts: 2026-08-07 UTC; Droid CLI `0.189.0`.
- Scratch repository: `/Users/sab-mini/probe-gddp-mission/repo`.
- Mission worktree created by top-level `-w probe-alpha-beta`: `/Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta`.
- Baseline commit: `48ecdb67a696dc85256f005d8393cd24815cfcca`.
- Invocation was exactly the requested no-TTY shape (`stdin </dev/null`, stdout/stderr redirected); all supplied mission flags were accepted. There were **no flag rejections**.
- Factory-home isolation **worked**, but the supported variable is `FACTORY_HOME_OVERRIDE`, not `FACTORY_HOME`. Exact bundle inspection found 7 occurrences of `FACTORY_HOME` only as part of `FACTORY_HOME_OVERRIDE`, zero `DROID_HOME`, zero `FACTORY_CONFIG_DIR`, and unrelated `XDG_CONFIG_HOME` use for WezTerm/git dependencies. The bundle resolver is `function p9(){return l8R()||WQn()}` with `l8R()` returning `process.env.FACTORY_HOME_OVERRIDE`. The invocation used `FACTORY_HOME_OVERRIDE=/Users/sab-mini/probe-gddp-mission/factory-home`, and all mission/session/log state landed below `/Users/sab-mini/probe-gddp-mission/factory-home/.factory/`.
- Only `auth.v2.file`, `auth.v2.key`, minimal `settings.json`, and probe `hooks.json` were copied/created in the isolated home before launch. The real `~/.factory/missions/` was not used.
- Settings requested `missionModelSettings.skipScrutiny=true` and `skipUserTesting=true`. The mission's persisted `model-settings.json` records both as `true`; progress records `validation-skipped-probe`, and no scrutiny or user-testing feature was added. The orchestrator nevertheless ran a separate final 28-assertion verification recorded in `validation-state.json`, so these settings skip the named milestone validator feature types, not all final verification.

> **CLEANUP UUID: `e708b834-7b3b-4524-a6af-21c514549f44`**  
> Isolated mission directory: `/Users/sab-mini/probe-gddp-mission/factory-home/.factory/missions/e708b834-7b3b-4524-a6af-21c514549f44`.

## Q1 1:1 mapping

**VERDICT: YES IN THIS PROBE — the orchestrator honored the dictated exact 1:1 mapping.**

Verbatim `features.json` ID list, in file order:

```json
["node-alpha", "node-beta"]
```

There are exactly 2 features: `node-alpha` and `node-beta`, both under milestone string `probe`; both completed. No setup, validation, cleanup, or other feature appeared. Dispatch was serial and in demanded order: alpha selected/started/completed, then beta selected/started/completed. `features.json` has no structured dependency or milestone collection at all (only a `features` array, and each feature has a `milestone` string); neither feature object has `dependencies`/`dependsOn`. Therefore the observed ordering is proven by `progress_log.jsonl`, not by a persisted dependency edge in `features.json`.

Full event sequence (full JSON lines are in `probe1-raw/progress_log.jsonl`):

- `2026-08-07T20:57:48.896Z` `mission_accepted`
- `2026-08-07T21:06:56.950Z` `mission_run_started`
- `2026-08-07T21:06:58.589Z` `worker_selected_feature` — feature `node-alpha`, worker `d67d078e-580b-4c1c-8fe7-dbe425b37164`
- `2026-08-07T21:06:58.594Z` `worker_started` — feature `node-alpha`, worker `d67d078e-580b-4c1c-8fe7-dbe425b37164`
- `2026-08-07T21:08:34.914Z` `worker_completed` — feature `node-alpha`, worker `d67d078e-580b-4c1c-8fe7-dbe425b37164`, state `success`
- `2026-08-07T21:08:36.362Z` `worker_selected_feature` — feature `node-beta`, worker `f3921f8f-71a0-4794-974a-420042721781`
- `2026-08-07T21:08:36.363Z` `worker_started` — feature `node-beta`, worker `f3921f8f-71a0-4794-974a-420042721781`
- `2026-08-07T21:10:21.137Z` `worker_completed` — feature `node-beta`, worker `f3921f8f-71a0-4794-974a-420042721781`, state `success`
- `2026-08-07T21:10:21.146Z` `milestone_validation_triggered` — feature `validation-skipped-probe`, worker `None`

## Q2 worktree and commit landing

**VERDICT: ONE SHARED NAMED WORKTREE/BRANCH; BOTH WORKERS COMMITTED THERE; MAIN WAS UNTOUCHED.**

Both handoffs name the same `repoPath`, `/Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta`, and both receipts independently observed that same git top-level and branch `probe-alpha-beta`. No per-worker worktrees or branches appeared.

Main checkout HEAD remained the baseline and was clean:

```text
48ecdb67a696dc85256f005d8393cd24815cfcca
## main
```

The preserved mission worktree ended at beta's commit and had only generated untracked Python cache:

```text
674c78e5ae4c837746c87dc4ceb84c50ae594630
## probe-alpha-beta
?? __pycache__/
```

Full graph:

```text
* 674c78e (probe-alpha-beta) node-beta: add multiply to calc
* 5111d16 node-alpha: add subtract to calc
* 48ecdb6 (HEAD -> main) probe: establish calculator baseline
```

Branches:

```text
* main             48ecdb6 probe: establish calculator baseline
+ probe-alpha-beta 674c78e (/Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta) node-beta: add multiply to calc
```

Worktrees:

```text
worktree /Users/sab-mini/probe-gddp-mission/repo
HEAD 48ecdb67a696dc85256f005d8393cd24815cfcca
branch refs/heads/main

worktree /Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta
HEAD 674c78e5ae4c837746c87dc4ceb84c50ae594630
branch refs/heads/probe-alpha-beta
```

Commit metadata/trailers:

```text
COMMIT=48ecdb67a696dc85256f005d8393cd24815cfcca
PARENTS=
REFS=main
SUBJECT=probe: establish calculator baseline
BODY=
---
COMMIT=5111d16ec89a295e7d9f78fa22ee056b456efc86
PARENTS=48ecdb67a696dc85256f005d8393cd24815cfcca
REFS=
SUBJECT=node-alpha: add subtract to calc
BODY=GDDP-Node-Id: node-alpha

---
COMMIT=674c78e5ae4c837746c87dc4ceb84c50ae594630
PARENTS=5111d16ec89a295e7d9f78fa22ee056b456efc86
REFS=HEAD -> probe-alpha-beta
SUBJECT=node-beta: add multiply to calc
BODY=GDDP-Node-Id: node-beta

---
```

Only `calc.py` and `test_calc.py` differ from baseline. There are no remotes and no tags.

Handoffs:

| featureId | workerSessionId | commitId | repoPath | successState | returnToOrchestrator |
|---|---|---|---|---|---|
| `node-alpha` | `d67d078e-580b-4c1c-8fe7-dbe425b37164` | `5111d16ec89a295e7d9f78fa22ee056b456efc86` | `/Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta` | `success` | `False` |
| `node-beta` | `f3921f8f-71a0-4794-974a-420042721781` | `674c78e5ae4c837746c87dc4ceb84c50ae594630` | `/Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta` | `success` | `False` |

Both handoffs carry `commitId`, `repoPath`, and `successState: success`; neither contains a structured base SHA.

## Q3 receipt CLI compliance

**VERDICT: YES — exactly once per feature, with a correct contiguous SHA chain.**

There are exactly two JSONL records. Alpha recorded baseline → alpha commit; beta recorded alpha commit → beta commit. In each record, the independently sampled `git_head` equals the supplied result, the branch is `probe-alpha-beta`, and the sampled top-level is the shared mission worktree. Timestamps are alpha `2026-08-07T21:08:04.846593+00:00`, beta `2026-08-07T21:09:33.026503+00:00`.

Verbatim `receipts.jsonl`:

```jsonl
{"base": "48ecdb67a696dc85256f005d8393cd24815cfcca", "git_branch": "probe-alpha-beta", "git_head": "5111d16ec89a295e7d9f78fa22ee056b456efc86", "git_toplevel": "/Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta", "node_id": "node-alpha", "relevant_env": {"FACTORY_API_BASE_URL": "https://api.factory.ai", "FACTORY_DEPLOYMENT_ENV": "production", "FACTORY_DISABLE_SETTINGS_PERSISTENCE": "true", "FACTORY_DROID_AUTO_UPDATE_ENABLED": "false", "FACTORY_ENV": "production", "FACTORY_EXEC_TARGET_AUTONOMY": "auto-high", "FACTORY_HOME_OVERRIDE": "/Users/sab-mini/probe-gddp-mission/factory-home", "FACTORY_OTEL_ENABLED": "true", "FACTORY_RUNTIME_SETTINGS_PATH": "/Users/sab-mini/probe-gddp-mission/factory-home/.factory/missions/e708b834-7b3b-4524-a6af-21c514549f44/runtime-custom-models.json", "FACTORY_UPSTREAM_CLIENT_TYPE": "cli", "STARSHIP_SESSION_KEY": "4163213942089183"}, "result": "5111d16ec89a295e7d9f78fa22ee056b456efc86", "timestamp_utc": "2026-08-07T21:08:04.846593+00:00"}
{"base": "5111d16ec89a295e7d9f78fa22ee056b456efc86", "git_branch": "probe-alpha-beta", "git_head": "674c78e5ae4c837746c87dc4ceb84c50ae594630", "git_toplevel": "/Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta", "node_id": "node-beta", "relevant_env": {"FACTORY_API_BASE_URL": "https://api.factory.ai", "FACTORY_DEPLOYMENT_ENV": "production", "FACTORY_DISABLE_SETTINGS_PERSISTENCE": "true", "FACTORY_DROID_AUTO_UPDATE_ENABLED": "false", "FACTORY_ENV": "production", "FACTORY_EXEC_TARGET_AUTONOMY": "auto-high", "FACTORY_HOME_OVERRIDE": "/Users/sab-mini/probe-gddp-mission/factory-home", "FACTORY_OTEL_ENABLED": "true", "FACTORY_RUNTIME_SETTINGS_PATH": "/Users/sab-mini/probe-gddp-mission/factory-home/.factory/missions/e708b834-7b3b-4524-a6af-21c514549f44/runtime-custom-models.json", "FACTORY_UPSTREAM_CLIENT_TYPE": "cli", "STARSHIP_SESSION_KEY": "4163213942089183"}, "result": "674c78e5ae4c837746c87dc4ceb84c50ae594630", "timestamp_utc": "2026-08-07T21:09:33.026503+00:00"}
```

## Q4 per-worker hooks

**VERDICT: UNPROBED — the documented isolated hook configuration was rejected before hooks could fire, so no claim about per-worker lifecycle behavior is justified.**

`/Users/sab-mini/mission-recon-gddp/docs-raw/hooks.md` says standalone `hooks.json` uses a top-level `{"hooks": {...events...}}` object. That exact documented form was placed at `/Users/sab-mini/probe-gddp-mission/factory-home/.factory/hooks.json`. Droid `0.189.0` logged:

```text
[2026-08-07T20:56:26.949Z] WARN: Ignoring unknown hook event keys | Context: {"path":"/Users/sab-mini/probe-gddp-mission/factory-home/.factory/hooks.json","name":"hooks.json","keys":["hooks"],"tags":{"clientType":"cli","platform":"darwin","environment":"production","version":"0.189.0","os":"darwin 25.5.0","terminal":"dumb","subcommand":"exec","isDroidExec":"true","isStreamJsonRpcWorker":"false","callingSessionIdPresent":"false","isInteractiveTty":"false","droidInstallationId":"439ff0d8-10bc-458b-a549-b9dea4e4ea16","hostId":"9ced4786-2d61-4514-9762-11533ff2452f"}}
```

No `/Users/sab-mini/probe-gddp-mission/hooks.jsonl` was created during the mission. A post-mission isolated ordinary `droid exec` control session (`c51f5caf-3655-43cb-ad4b-7076d2d45b9c`) also exited 0 but produced zero hook records, confirming this was loader/config rejection rather than evidence that only mission workers suppress hooks. Bundle inspection indicates standalone `hooks.json` expects direct event keys while the documented outer `hooks` key applies when hooks are embedded in `settings.json`. Because the actual probe launched with the rejected shape, SessionStart/SessionEnd/Stop/SubagentStop/PreToolUse/PostToolUse counts are all zero and worker-vs-orchestrator hook behavior remains unanswered. `probe1-raw/hooks.jsonl` is intentionally empty; `probe1-raw/hooks-loader-warning.txt` preserves the failure.

## Q5 headless viability

**VERDICT: YES — fully headless completion, exit code 0.**

The command accepted redirected `/dev/null` stdin, never requested input, completed in roughly 16 minutes, and wrote exit code `0`. Stdout remained empty during orchestration and then emitted a polished Markdown completion report at the end; it is not a live progress/event stream. Stderr contained only worktree lifecycle notices. No flag was rejected.

Full stdout:

```text
**Mission complete.** Both graph nodes executed successfully and the end-of-mission gate is open: **28/28 assertions passed**.

## Graph mapping — strict 1:1 preserved

```
node-alpha ──▶ 5111d16e…fc86  [GDDP-Node-Id: node-alpha]  ──▶ receipt line 1
node-beta  ──▶ 674c78e5…4630  [GDDP-Node-Id: node-beta ]  ──▶ receipt line 2
```

- **Exactly two features**, IDs exactly `node-alpha` and `node-beta` — no renaming, no decomposition, no added setup/validation/docs/cleanup features.
- **Exactly one milestone**, `probe`, containing both.
- **Exactly two commits** above baseline `48ecdb6`, strictly linear, alpha-then-beta, each carrying its exact trailer (verified with git's trailer parser across `--all`, not substring grep).
- **Exactly two receipt records**, forming an unbroken chain `48ecdb67 → 5111d16e → 674c78e5 = HEAD`.
- **No push, no remote, no tags, no new branches**, only `calc.py` and `test_calc.py` touched, `3 passed`.

## Notable verification findings

The ordering guarantee was proven at the *protocol* level, not just via commit ancestry. Alpha's receipt landed ~75s **before** beta's commit was even created (`alpha.ts 21:08:04 < beta commit 21:09:19 < beta.ts 21:09:33`), which rules out the batched "both commits, then both receipts" pattern that ancestry alone cannot exclude. Each receipt's ambient `git_head` (captured by the CLI, not supplied by the worker) equals its own commit SHA, proving each receipt ran *after* its commit rather than being fabricated.

A contract review pass before execution caught two issues worth flagging: an assertion that would have **failed a fully compliant run** (`__pycache__/` is unavoidably untracked, and the only "fixes" — a `.gitignore` — would themselves have violated the no-new-files rule), and a gap where nothing proved the temporal half of the protocol. Both were corrected pre-flight.

## One deliberate deviation to flag

I did **not** perform the usual end-of-mission README update. Doing so would have required a third commit and a modification outside `calc.py`/`test_calc.py`, directly violating the probe's exact-two-node mapping and breaking `VAL-CROSS-002`, `VAL-CROSS-006`, and `VAL-CROSS-008` — all of which currently pass. The mission's explicit constraints took precedence. Say the word if you'd like a README change made as separate, clearly out-of-band work.

Artifacts are in `…/missions/e708b834-7b3b-4524-a6af-21c514549f44/` (`architecture.md`, `validation-contract.md`, `validation-state.json`, `features.json`, `AGENTS.md`, `skills/probe-node-worker/`, `services.yaml`, `init.sh`, `library/`).
```

Full stderr:

```text
Created worktree at /Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta (branch: probe-alpha-beta)
Worktree preserved at /Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta (has uncommitted changes).
```

## Boundary reconstruction comparison

1. **Receipts — strongest and exact for this run.** They explicitly state each worker's claimed starting SHA and result SHA, while independently sampling ambient HEAD, branch, and top-level after commit. They form the exact contiguous chain `48ecdb67a696dc85256f005d8393cd24815cfcca → 5111d16ec89a295e7d9f78fa22ee056b456efc86 → 674c78e5ae4c837746c87dc4ceb84c50ae594630`. Exact per-feature boundaries are directly reconstructable.
2. **Git trailers — strong identification, weaker start proof.** Trailer-bearing commits identify results exactly. Their parents reconstruct baseline→alpha and alpha→beta in this linear two-commit run. A trailer alone does not prove the worker's recorded start or exclude untrailed intermediate commits in a less constrained run, so it is less reliable than the receipt contract.
3. **Factory artifacts alone — result-capable, base-incomplete.** Each handoff gives exact `commitId`, `repoPath`, feature ID, session ID, and success. It has no base SHA. Factory-generated prose in feature preconditions mentions expected starting SHAs, but that is generated contract text, not a structured observation. Without consulting git parentage or external receipts, Factory artifacts cannot independently prove exact base→result boundaries.

Per feature:

| Feature | Receipt boundary | Trailer/git-parent boundary | Factory handoff |
|---|---|---|---|
| `node-alpha` | `48ecdb67…fcca → 5111d16e…fc86` | same | result `5111d16e…fc86`; no base |
| `node-beta` | `5111d16e…fc86 → 674c78e5…4630` | same | result `674c78e5…4630`; no base |

## Surprises and anomalies

- The exact dictated feature IDs and count survived decomposition, decisively answering Q1 for this probe.
- Mission setup was expensive relative to the two-line code change: acceptance at `20:57:48Z`, run start only at `21:06:56Z`; it generated `architecture.md`, `validation-contract.md`, mission `AGENTS.md`, a worker skill, service/init/library files, and validation state before dispatch.
- `features.json` does not persist an explicit dependency edge or a top-level milestone object. Correct serial order exists only in event history and resulting commit ancestry.
- Top-level `-w` creates one shared worktree and one shared branch, not worker-isolated worktrees. Both worker sessions used it sequentially.
- The requested `skipScrutiny`/`skipUserTesting` values were persisted and prevented validator features, but a final orchestrator-driven validation still populated 28 passed assertions using sessions `cd2fd62e-7ad6-4c57-89b4-300432451028`, `7fa7364c-691f-4e9f-8f67-b9b97ffe65e8`, and `00c199bd-69dc-40ad-b2cf-010656264e6e`.
- The mission emitted `milestone_validation_triggered` with synthetic feature ID `validation-skipped-probe`, despite no such object appearing in `features.json`.
- The project hook documentation and CLI `0.189.0` standalone hook-file parser disagree on the top-level shape. This invalidated Q4; no inference from zero hook lines is safe.
- Mission stdout provides no live progress until completion; durable progress must be polled from the isolated mission directory.
- Droid preserved the mission worktree because `__pycache__/` was left untracked. The main checkout stayed clean.
- The orchestrator explicitly declined its usual README update because that would have created an out-of-contract third commit; contract pressure successfully prevented it.
- No network git remote existed, no push occurred, and no CLI flags were rejected.

## Cleanup state

Nothing was deleted; all evidence remains intentionally.

- Scratch root: `/Users/sab-mini/probe-gddp-mission/`.
- Main repo: `/Users/sab-mini/probe-gddp-mission/repo` (clean `main` at baseline).
- Preserved mission worktree: `/Users/sab-mini/probe-gddp-mission/repo-wt-probe-alpha-beta` (`probe-alpha-beta` at beta result; untracked `__pycache__/`).
- Isolated Factory home: `/Users/sab-mini/probe-gddp-mission/factory-home/.factory/`.
- **Mission UUID/operator cleanup target: `e708b834-7b3b-4524-a6af-21c514549f44`** at `/Users/sab-mini/probe-gddp-mission/factory-home/.factory/missions/e708b834-7b3b-4524-a6af-21c514549f44`.
- Durable full mission snapshot: `/Users/sab-mini/probe-gddp-mission/mission-dir-snapshot/`.
- Raw requested evidence: `/Users/sab-mini/mission-recon-gddp/probe1-raw/`.
- Report: `/Users/sab-mini/mission-recon-gddp/04-probe1-results.md`.
- The separate hook-control session is isolated under the same scratch Factory home as session UUID `c51f5caf-3655-43cb-ad4b-7076d2d45b9c`.
- No directory under the operator's real `~/.factory/missions/` was created by this probe because `FACTORY_HOME_OVERRIDE` worked.
