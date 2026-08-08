# Plan to Be Ready — Droid `factory_mission` Run Tonight

Synthesized from 3 grok-4.5 scouts (2026-08-08), artifacts:
- `.pi-subagents/artifacts/outputs/3abca92f.../scout-1-graph-and-node.md`
- `.pi-subagents/artifacts/outputs/3abca92f.../scout-2-why-mission-ended-itself.md`
- `.pi-subagents/artifacts/outputs/3abca92f.../scout-3-plan-to-be-ready.md`

Host: khoj-38 · `gddp-runtime` main @ `40a6905` (= origin/main, clean).

## Reconciliation of the "ended itself" narrative

- **Confirmed live failure on this host:** `MappingProxyType` not JSON-serializable in
  `mission_projection._render_item`, crashing *before* `droid exec` launched. Fixed at
  `40a6905` (thaw + regression test). No `~/.factory/missions/` dir was ever created.
- **"Setup commands unmet → droid ended itself":** NOT evidenced on this host's disk
  (no mission dir, no engagement session, no in-mission stderr). Either from another
  host/session, or it is the *next* failure to pre-satisfy, not a recovered transcript.
- Treat `40a6905` as the fix for the confirmed crash; treat setup-commands as live risk.

## What's already green

- `factory_mission` adapter **fully merged on main** (`mission/milestone3` ⊆ main, empty
  diff; merge `63bdabe`; post-merge fix `40a6905`). Runnable from main (code path).
- Host: droid 0.189.0, docker 26.1.5 active, `xai/grok-4.5` auth READY, auto-shutdown off,
  55G free, 20Gi mem avail. Heartbeat timer active + sourcing `gddp.env` (correct kit path).
- Mission unit tests: 47 passed (projection/config/git-verify).

## Blockers to close before dispatch

1. **No `factory_mission` graph in `~/gddp-config`** (BLOCKER).
   Zero nodes have `allowed_execution_modes: [factory_mission]`. Classifier refuses routing
   otherwise. `vm-loop-smoke` ran via `local_subprocess` (done, provisional). The canonical
   5-node spine uses `jules_api`. **Human-owned:** Sab must author a small canary graph
   (2-3 nodes) with `allowed_execution_modes: [factory_mission]`,
   `default_executor: factory_mission`, `mission_engagement_size`, nodes in `ready`.
   Agents never author nodes (AGENTS.md).

2. **Model path droid will actually use** (BLOCKER / HIGH).
   - Hermes proxy `:8645` is **DOWN** (`curl` refused). `GDDP_DROID_SUBPROCESS_ARGV` pins
     `custom:Grok-4.5-sub-(Hermes)-0` → that proxy. **But** `MissionAdapter` does NOT pass
     `-m`, so `droid exec --mission` uses droid's **default** model, not the env argv.
   - Fix: start Hermes on :8645, OR repoint `~/.factory/settings.json` default model to a
     working upstream, OR teach `MissionAdapter` to honor `-m`/env
     (`scripts/adapters/mission_adapter.py:157-168`).

3. **Control plane idle — "No active projects"** (BLOCKER).
   `_active_projects` only wakes on events (received/claimed/ready/running/...) or sessions
   (dispatched/running/needs_operator/collected). Queue is 7× awaiting_review + 1× failed.
   Fix: inject ready/frontier events for the canary, or one-shot runner
   (`source deploy/mini-heartbeat/env/gddp.env && python3 -m scripts.runtime.heartbeat.runner
   --project <id> --repo <owner/repo> --config-path "$GDDP_CONFIG_PATH"`). Never call raw
   runner unsourced.

4. **Setup-commands preflight (the self-end guard)** (HIGH — the "ended itself" risk).
   droid mission mode requires: `services.yaml` (test/lint/typecheck + service start/stop),
   idempotent `init.sh`, QA one-command-start OR `skipUserTesting`/`skipScrutiny`, and explicit
   milestone-gate command confirmation. Currently:
   - `~/.factory/settings.json` has **no** `missionModelSettings` → QA/scrutiny **ON** by
     default. For a non-app repo (gddp-runtime), QA-on thrashes.
   - `project_mission` emits **no** setup/services/init/skip language.
   Fix: set `general.missionModelSettings.skipUserTesting=true` (+ `skipScrutiny=true`);
   extend `mission_projection` with an operational block (test cmd = `python3 -m pytest -q`,
   no service start, no user testing, validators read-only).

## Ordered steps → clean dispatch

1. Confirm `40a6905` fix in tree; do not re-dispatch until step 3 graph exists.
2. Bring the model path alive (Hermes up, or repoint default, or `-m` in adapter). Smoke:
   `droid exec --auto high -m <chosen> -q 'reply READY'`.
3. Sab authors a tiny `factory_mission` canary graph in `~/gddp-config/graphs/` (2-3 ready
   nodes, tight constraints). `git -C ~/gddp-config pull --ff-only` on host.
4. Edit `deploy/mini-heartbeat/env/gddp.env`: `GDDP_PROJECT_ID`/`GDDP_PROJECT_REPO` → canary.
   Keep `GDDP_LOCAL_*` on grok-4.5. Do NOT restore `.bak.vm-loop-smoke` (zai broken).
5. Set `skipUserTesting`/`skipScrutiny` in `~/.factory/settings.json`; extend `mission_projection`
   operational block.
6. Wake control plane: inject ready events or one-shot kit-sourced runner.
7. Preflight: `droid --version`, model smoke, `git status -sb` clean, `mkdir -p db/mission-sessions`,
   `PYTHONPATH=. python3 -c 'from adapters.mission_adapter import MissionAdapter'`.
8. Dispatch (timer tick or one-shot). Expect `db/mission-sessions/<id>/{mission.md,session.json,
   stdout,stderr}` + new `~/.factory/missions/<uuid>/`.
9. Observe/reconcile → evaluator → **awaiting_review**. Human accepts nodes only.

## Biggest risk + guard

Risk: mission process starts and **immediately exits** — most likely wrong/down model backend
(Hermes :8645 down / default model unverified), secondarily an uncaught projection edge.
Guard: 30s model smoke before dispatch; tiny 2-node canary so a self-exit is cheap and stderr
is inspectable; do NOT confuse single-node `GDDP_DROID_SUBPROCESS_ARGV` success with mission mode
(different argv path).

## Known adapter limits still in effect (AGENTS.md)
- Hooks unusable on droid 0.189.0 (standalone hook-file shape rejected).
- `mission_completed` event unverified.
- Crash/resume only partially observed; worker-level failure untested live.
- Push-guard bypass closed post-hoc (absolute git + hooksPath) via ls-remote quarantine.
