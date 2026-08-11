# Archive inventory — `scripts/_archive/` and `deploy/_archive/`

Node: `node-02-archive-inventory`  
Job: `job_20260811T04565361e5157546e8c3` (attempt 0)  
Base: `450eca1cffe1113b3af15db0b2ab65b7c0eb5b61`  
Inventory date: 2026-08-11  
Scope: every file under `scripts/_archive/` and `deploy/_archive/` in this worktree.

## Method

Read-only listing of both archive trees. For each path, purpose is taken from the
nearest stated evidence: archive `README.md` (deploy), module docstring / leading
comment (Python/shell), or unit header (systemd). File list verified with
`find scripts/_archive deploy/_archive -type f`.

## `deploy/_archive/` — dead-topology artifacts

Archive README (`deploy/_archive/README.md`, archived 2026-08-05): these files
describe the retired Big Pi / `~/opclaw` topology and must not be run on any
host. Living stand-up path is `deploy/mini-heartbeat/FRESH-HOST-STANDUP.md`.

| Path | Stated purpose / evidence |
|---|---|
| `deploy/_archive/README.md` | Index for this archive: dead-topology artifacts preserved for history; lists why each peer file is unsafe to run. |
| `deploy/_archive/BIGPI_RUNBOOK.md` | Header: “operator runbook for the live Big Pi control plane.” README: mix of host-agnostic doctrine and a topology that no longer exists (pi-big down). |
| `deploy/_archive/gddp-intake.service` | Systemd unit `Description=GDDP Intake Server`; hardcodes `User=sab-ssd` and `WorkingDirectory`/`ExecStart` under `/home/sab-ssd/repos/gddp-runtime`. |
| `deploy/_archive/setup.sh` | Header: “Deploy gddp-runtime to Big Pi / Run once on a fresh Pi.” Defaults `RUNTIME_ROOT` to `$HOME/opclaw` (retired tree per README and `BIGPI_RUNBOOK.md`). |

## `scripts/_archive/` — retired modules and their tests

No archive-level README in this tree. Purposes from each file’s module docstring
or leading comment. Related archival commits in history include phase1 canaries/replay,
phase2b jules CLI adapter + tests, and Stage 1 (089) push-guard archive.

| Path | Stated purpose / evidence |
|---|---|
| `scripts/_archive/canary_local_executor.py` | Docstring: trivial `GDDP_LOCAL_SUBPROCESS_ARGV` target for Node 2 (direct-executor-round-trip) stabilization; prints a fixed unified diff creating `docs/canary-stabilization-marker.md`; not production dispatch. |
| `scripts/_archive/canary_local_executor_slow.py` | Docstring: deliberately slow variant of the canary executor; sleeps to exercise mid-execution interruption/retry (session reaches `failed`, not `completed`). |
| `scripts/_archive/canary_stabilization_reset.py` | Docstring: fresh-state reset for the Node 2 stabilization loop; deletes only the synthetic canary’s event/job/session/result rows for a given `job_id`. |
| `scripts/_archive/jules_cli_adapter.py` | Docstring: direct CLI dispatch adapter (`jules remote …`); GDDP-pure Jules path via executor-neutral protocol (`dispatch`/`status`/`collect`/`cancel`). |
| `scripts/_archive/test_jules_cli_adapter.py` | Docstring: “Archived with jules_cli_adapter.py — not collected (pytest norecursedirs). CLI-only tests moved out of the live suite in Phase 2B. Kept for reference.” |
| `scripts/_archive/mission_push_guard.py` | Docstring: “Enforce and audit mission worker pushes at the git executable boundary.” Installs PATH shim + pre-push hook; residual absolute-git bypass noted for post-hoc mission_evidence detection. |
| `scripts/_archive/test_mission_push_guard.py` | Companion tests for `mission_push_guard` (imports historically `scripts.adapters.mission_push_guard`); covers engagement-refspec allow and audit behavior. No separate module docstring beyond imports/tests. |
| `scripts/_archive/replay.py` | Docstring: replay failed or partial runtime steps from persisted state (`--result-id` re-runs return router; `--job-id` re-dispatches with operator confirmation). |
| `scripts/_archive/test_replay.py` | Docstring: “Tests for the replay logic.” Unit tests mocking DB connect / return_router / dispatcher. |

## Counts

- `deploy/_archive/`: 4 files  
- `scripts/_archive/`: 9 files  
- Total archived entries inventoried: **13**

## Validation

Ran in this worktree (read-only outside this report; flask absent on host PATH,
so intake/rig1 tests that import Flask fail — environment, not archive inventory):

```text
$ python3 -m pytest -q
...
4 failed, 622 passed in 36.32s
```

Pytest tail line (quoted): `4 failed, 622 passed in 36.32s`
