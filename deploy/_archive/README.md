# deploy/_archive — dead-topology artifacts, preserved for history

Archived 2026-08-05. These files describe the retired Big Pi / `~/opclaw`
topology and must not be run on any host:

- `setup.sh` — defaults `RUNTIME_ROOT` to `$HOME/opclaw`, which
  `BIGPI_RUNBOOK.md` itself declares retired. Running it on a fresh host
  stands the host up into a dead tree.
- `gddp-intake.service` — hardcodes `User=sab-ssd` and
  `/home/sab-ssd/repos/gddp-runtime`.
- `BIGPI_RUNBOOK.md` — mix of host-agnostic doctrine and a topology that
  no longer exists (pi-big is down; its artifacts do not work).

The living stand-up path is `deploy/mini-heartbeat/FRESH-HOST-STANDUP.md`
— captured from the first verified fresh-host port (khoj-38, 2026-08-05).
