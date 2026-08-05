# Fresh-host GDDP stand-up — captured from the first real port

Provenance: this sequence was **executed, not theorized**, on khoj-38
(Linux x86_64) the night of 2026-08-04 → 05, and produced the first
fully autonomous droid run (vm-harness-audit, 5/5 provisional). It is the
only verified fresh-host record GDDP has. Big Pi's artifacts predate it
and do not work (see warning below).

> ⚠️ **Do not run `deploy/setup.sh` on a fresh host.** It defaults
> `RUNTIME_ROOT` to `$HOME/opclaw` — a tree `BIGPI_RUNBOOK.md` itself
> declares retired. `deploy/gddp-intake.service` hardcodes
> `User=sab-ssd` and `/home/sab-ssd/...`. All three artifacts describe a
> dead topology. This file is the living stand-up path.

## Prerequisites (were already present on khoj-38)

- Linux user with ssh + sudo-lite (`loginctl enable-linger` needs no root)
- git, python3.11+, tmux
- Executor CLI(s) you intend to route: `droid` 0.186.0 here (`droid --version`)
- Any model proxies your executor argv targets, running and listening —
  here: Hermes proxies in a tmux session (`hermes-proxies`), Grok on
  `127.0.0.1:8645`. Verify: `ss -ltnp | grep 864`

## Sequence as executed

1. **Checkouts at `$HOME` directly** (not `~/repos`):
   `git clone <gddp-runtime> ~/gddp-runtime && git clone <gddp-config> ~/gddp-config`
2. **Report repo per graph:** `git init ~/pi-harness-audit` (the graph's
   `project.yaml` `repo:` field + reports target).
3. **Python env for the gddp CLI:**
   `python3 -m venv ~/gddp-config/.venv && ~/gddp-config/.venv/bin/pip install flask pyyaml rich`
   — `bin/gddp` runs under that venv.
4. **Heartbeat env** at `~/gddp-runtime/deploy/mini-heartbeat/env/gddp.env`:
   VM-absolute paths (HOME-relative roots), `GDDP_DROID_SUBPROCESS_ARGV`
   with the executor model (`custom:Grok-4.5-sub-(Hermes)-0` here),
   `DEEPSEEK_API_KEY` for the evaluator's semantic lane. This file is
   sourced by every heartbeat path — never invoke the runner without it.
5. **systemd user units** (canonical copies upstreamed in
   `deploy/mini-heartbeat/systemd/`, commit `d45afaf`):
   install `gddp-heartbeat.service` + `gddp-heartbeat.timer` to
   `~/.config/systemd/user/`, then
   `loginctl enable-linger $USER && systemctl --user daemon-reload && systemctl --user enable --now gddp-heartbeat.timer`
   Cadence 300s. **`KillMode=process` is mandatory** — the default
   `control-group` reaps freshly-dispatched executors when the oneshot
   tick exits (cost us node-04 attempts 0–2 before diagnosis).
6. **Smoke before dispatch:** one manual tick sourced from the env
   (`bash deploy/mini-heartbeat/bin/smoke.sh` equivalent), confirm
   `db/queue.db` exists and the tick reports clean.
7. **First dispatch:** inject the first node's dispatch event (manual
   inject), then let `frontier_auto_advance` carry the rest. Confirm the
   spool advances to full lifecycle (`command.json`, `packet.json`,
   `supervisor.pid`, `pid`, `stdout`, `stderr`, `exit.json`).

## First-contact bugs this port surfaced (all fixed upstream)

| Defect | Fix |
|---|---|
| Verifier crash on non-string YAML items | `185e6fe` |
| Frontier check before evaluation finalize | `66f4ae5` |
| GraphReader cache stale at re-check | `9991c8e` |
| Droid sessions mislabeled → retries rerouted to pi | `727bb7a` |
| systemd `KillMode` reaping executors | `d45afaf` |

None were repeat bugs — they were first-contact with a real loop on a
real second host. Expect the next fresh host to find its own; that is
the point of porting early and often.
