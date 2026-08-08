# Production hosts

## sab-mini

`sab-mini` is the verified production control plane as of 2026-07-12.

| Surface | Value |
| --- | --- |
| Host | `sab-mini` Mac Mini, 16 GB; use its Tailscale name in plans |
| Intake | launchd `com.gddp.intake` on `127.0.0.1:5050` |
| Heartbeat | launchd `com.gddp.heartbeat`, 300-second interval |
| Public webhook | `https://sab-mini.tail02ac6f.ts.net/webhook` |
| Exposure | Tailscale Funnel to local port 5050 |
| Runtime checkout | `~/repos/gddp-runtime` |
| Config checkout | `~/repos/gddp-config` |
| Queue | `~/repos/gddp-runtime/db/queue.db` |
| GitHub | `gh` authenticated with SSH protocol |
| Webhooks | 12 `skchaudr/*` repositories sharing the canonical secret |

The host plan must always name `sab-mini` when describing checkout, queue, process, or webhook state. Those claims are machine-relative.

## Secrets

Production secrets live outside Git in `~/.password-store`, encrypted to GPG key `F0928E218506BB29`. The store and automation key were migrated from `pi-big` on 2026-07-13; the pi copy remains an offline backup only.

Although interactive commands can use `pass`, production launchd secret commands invoke `gpg --decrypt` directly where configured because `pass` can hang in a headless launchd context. Never print resolver output during checks; `/Users/sab-mini/repos/gddp-runtime/deploy/mini-heartbeat/bin/smoke.sh` reports only key length.

## Public intake

Tailscale Funnel provides the stable HTTPS endpoint while intake remains bound to localhost. Before exposing or repointing webhooks:

1. Confirm `/health` is 200 and reports webhook verification.
2. Confirm an invalid `X-Hub-Signature-256` receives 401 and creates no event.
3. Use one GitHub Ping or low-risk delivery before updating all webhooks.
4. Keep only one intake/control plane active.

Do not use a bare `cloudflared` or intake process for work that may outlive the shell session. The July 12 canary demonstrated that a multi-day job can outlive an ad-hoc tunnel and process.

## pi-big

`pi-big` is disarmed: intake is inactive and heartbeat cron is commented. It is not a queue host and production no longer depends on it. Its retained password store is recovery evidence, not an alternate live control plane.

Source of truth: `/Users/sab-mini/repos/gddp-runtime/TOPOLOGY.md`.
