# VM Mission Host Plan (khoj-38)

**Status:** recon + version parity done; docker image not built yet.
**Date:** 2026-08-08 · Host: khoj-38 (sab-mini@khoj-38)

## Recon snapshot

| Item | Result |
|---|---|
| droid (local pin) | 0.189.0 |
| droid (VM before) | 0.188.0 |
| droid (VM after) | **0.189.0** (`droid update` succeeded) |
| Docker CLI/daemon | **not installed** (no binary, no `docker.service`) |
| docker group | user `sab-mini` is already in `docker` group |
| Disk `/` | 99G total, 40G used, **55G free** (42%) |
| RAM | **23 GB** total, ~18 GB free |
| gddp-runtime | `main` @ `efa449a`, clean, matches origin |
| gddp-config | `main` @ `cd1246e`, clean, matches origin |
| heartbeat timer | user systemd `gddp-heartbeat.timer` **enabled/active** (300s) |
| pytest | **517 passed** (fresh `.venv` + flask/pyyaml/pytest/pydantic) |

Auto-shutdown timers (8h hard + 6h idle + 12h boot) were disabled earlier this session — host can now hold long missions.

## Dockerization plan (one page)

### Base image
- **`ubuntu:24.04`** (or `ubuntu:22.04` if a pinned LTS is preferred).
- Install: `git`, `curl`, `ca-certificates`, `python3`, `python3-venv`, `python3-pip`.
- Install **droid CLI pinned to 0.189.0** via Factory’s install/update script at image build time; record the exact version in an image label (`org.gddp.droid.version=0.189.0`).
- Do **not** bake API keys. Auth mounts in at runtime (see below).

### Baked in vs mounted

| Baked into image | Mounted at runtime |
|---|---|
| droid 0.189.0 binary + deps | `~/gddp-runtime` (read/write worktrees under it) |
| python3 + venv tooling | `~/gddp-config` (graph YAML, read-mostly) |
| git | `~/.factory` — sessions, missions, settings (state) |
| ca-certs / git config defaults | `~/.pi` or host-settings only if a mission needs them |
| | droid/Factory auth material (read-only bind, never in image) |

### How a mission launches

**Recommended v1:** container as **isolation boundary**, host (or heartbeat) still owns the launch command:

```text
docker run --rm \
  -v ~/gddp-runtime:/work/gddp-runtime \
  -v ~/gddp-config:/work/gddp-config \
  -v ~/.factory:/home/agent/.factory \
  -v <auth>:/home/agent/.factory/auth:ro \
  -w /work/gddp-runtime \
  gddp-droid:0.189.0 \
  droid exec --mission --auto high -w gddp/<engagement-id> -f /path/to/mission.md
```

- Matches the settled doctrine: **GDDP launches at engagement level** (heartbeat/dispatch path), then only **observes** `~/.factory/missions/` + git refs.
- `--skip-permissions-unsafe` is legitimate **only inside this disposable container** (Factory’s own guidance) — use it for mission isolation, not on the bare host.
- Alternative later: long-lived container with `droid daemon` inside; not needed for v1.

### Evidence flow out of the container

Because `~/.factory` and the repo worktrees are **bind-mounted**, evidence never stays trapped in the container:

1. **Mission directory** — `~/.factory/missions/<uuid>/` (features.json, progress_log.jsonl, handoffs/, state.json) written on the host mount.
2. **Worktree / branch commits** — droid `-w` worktrees under the mounted runtime repo; per-feature commits with `GDDP-Node-Id` trailers land on the engagement branch.
3. **GDDP collect path** — host-side `factory_mission` adapter (post-mission) reads mission dir + verifies git ancestry on the host checkout; evaluator builds detached worktrees at result SHAs as today.
4. **No copy step** — mounts are the contract; container exit must not delete host-mounted state (`--rm` removes only the container layer).

### Build/order of operations (when authorized)

1. Install Docker Engine on khoj-38 (user already in `docker` group).
2. Add `deploy/mission-host/Dockerfile` + pin script for droid 0.189.0.
3. Build/tag `gddp-droid:0.189.0`; smoke: `droid --version` inside container.
4. One throwaway headless mission in-container against a scratch worktree; confirm mission dir + commits visible on host.
5. Wire heartbeat/dispatch to prefer containerized launch on this host only.

### Residual risks
- Docker not installed yet — plan only.
- Auth/key mounting path must stay out of git and out of image layers.
- droid auto-update inside containers should stay **off** so the pin holds.
- Resource: 23 GB RAM is ample; keep mission concurrency low until observed.

## Report line
Version 0.188.0 → **0.189.0**; docker **absent**; gddp clean + heartbeat timer active + **517 tests passed**; this plan file.

- 2026-08-08: docker installed + verified on khoj-38 — Docker version 26.1.5+dfsg1 (docker.io via apt), daemon active/enabled, hello-world OK via sg docker, docker ps clean.
