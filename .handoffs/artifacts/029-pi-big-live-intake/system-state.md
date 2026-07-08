# 029 Artifact — Pi-Big Live Intake: System State & Runbook

Snapshot date: 2026-07-07. Everything below was verified live, not assumed.

## Event flow (end to end)

```
GitHub (12 repos, signed webhooks: issues, pull_request, issue_comment)
  → https://pi-big.tail02ac6f.ts.net/webhook   (tailscale funnel, public)
  → gddp-intake.service                        (Flask, 127.0.0.1:5050, HMAC sha256 verify)
  → raw payload saved under events/raw/ + row in db/queue.db events table (status=received)
  → heartbeat cron (*/5 min) classifies/routes pending events, computes ready nodes
  → dispatch → executor (Jules) → return path → two-lane evaluator (criteria + integrity,
    worst-of combiner) → verdict receipt → human accept_node (acceptance is NEVER automatic)
```

## Host topology

- **pi-big** (`tailscale ssh sab-ssd@pi-big`, hostname `big-ssd`) runs EVERYTHING: intake service, heartbeat cron, funnel, queue.db. Single source of truth.
- **pi-small**: legacy `opclaw-intake.service` stopped + disabled 2026-07-07. Nothing GDDP runs there.
- Repos on pi-big at `/home/sab-ssd/repos/gddp-runtime` (@ 33c0982) and `/home/sab-ssd/repos/gddp-config` (@ 81a197e), both on branch `run-main` tracking origin/main (local `main` had diverged; left intact, do not reset it). Pre-existing local dirs preserved at `graphify-out.pi-local-backup` and `~/pi-local-backups/gddp-config/`.

## Pieces

### gddp-intake.service (systemd)
`/etc/systemd/system/gddp-intake.service` — User=sab-ssd, WorkingDirectory=~/repos/gddp-runtime, ExecStart `python3 scripts/intake_server.py`, Restart=always. Server binds 127.0.0.1:5050; routes: `POST /webhook`, `GET /health`.

Secret resolution (`scripts/intake_server.py::_resolve_webhook_secret`): env `GITHUB_WEBHOOK_SECRET` if set, else runs `GDDP_WEBHOOK_SECRET_CMD` (default `pass show gddp/webhook-secret`). If nothing resolves, verification is **fail-open** and startup prints a loud WARNING — after any restart, check the journal has no "no webhook secret resolved" line before trusting it.

### Heartbeat (cron on pi-big)
```
*/5 * * * * cd /home/sab-ssd/repos/gddp-runtime && /usr/bin/python3 -m scripts.runtime.heartbeat.runner --project gddp-runtime --repo skchaudr/gddp-runtime --config-path /home/sab-ssd/repos/gddp-config >> /home/sab-ssd/heartbeat.log 2>&1
```
Single-tick design; log at `~/heartbeat.log`. Healthy tick reads: ready nodes list → "No pending events." → "Heartbeat complete."

### Tailscale funnel
`sudo tailscale funnel --bg --https=443 5050` → public at `https://pi-big.tail02ac6f.ts.net`. Kill switch: `sudo tailscale funnel --https=443 off`. Note: public URL gets scanner-bot probes (/.env, /.aws/credentials, …) within minutes — all 404, expected noise; the HMAC check on /webhook is the actual gate. **Never run the funnel while intake is in fail-open state.**

## Secrets architecture (pass + GPG on pi-big)

- Store `~/.password-store`; both root and `gddp/` `.gpg-id` = `saboor` + `F0928E218506BB29`.
- **F0928E218506BB29** = `gddp-automation (pi-big headless)`, ed25519/cv25519, **passphrase-less, no expiry** — deliberately, so cron/systemd decrypt with a cold agent (reboot-safe). Machine-local only; protection tier = disk + user perms.
- **8E02F7F88E59CD19** (`saboor`) = passphrase-protected human key, second recipient on everything → Sab can always decrypt interactively.
- **9A275F40FCF626F4** (`sabor (pi-big)`) = EXPIRED, passphrase lost. Dead — never key anything to it.
- Entries: `gddp/webhook-secret` (64-hex, minted 2026-07-07, matches all 12 GitHub hooks), `api/deepseek` (re-inserted by Sab 2026-07-07). Both verified decrypting after `gpgconf --kill gpg-agent` (proves no cache dependency).
- New secret: `pass insert -e -f <path>` on pi-big → auto-encrypts to both keys. **Never print secret values; verify with `| wc -c` only.**
- Gotcha history: passphrase-protected keys only decrypt headlessly via gpg-agent's 8h cache — looks fine after an ssh session, silently dies overnight. That is why the automation key exists.

## GitHub webhooks (all owner `skchaudr`)

Config per hook: url `https://pi-big.tail02ac6f.ts.net/webhook`, content_type json, secret from pass, events `issues, pull_request, issue_comment`. Created via `gh api repos/skchaudr/<repo>/hooks` on pi-big (gh authed as skchaudr; secret flowed pass→gh, never displayed).

| repo | hook id | ping |
|---|---|---|
| aa-cli | 650468775 | 200 |
| Automating-Selling-Random-Valuables | 650468776 | 200 |
| bonny-doon-retreat | 650468779 | 200 |
| gddp-config | 650468784 | 200 |
| gddp-runtime | 650468787 | 200 |
| MyAPI | 650468789 | 200 |
| Pi-Coding-Agent | 650468790 | 200 |
| aqua-stone-studio | 650468792 | 200 |
| socialxp | 650468794 | 200 |
| dev-journal | 650468796 | 200 |
| sc-landscape-lead-intel-system | 650468797 | 200 |
| saboorkc.dev | 650468798 | 200 (after one transient 504) |

Forged/unsigned POST to /webhook → 401 (verified). Note `intake_server.py` maps events beyond those subscribed (push, workflow_run, check_suite) — hooks can be broadened later by PATCHing events, no code change.

## Health check (run this first when picking up)

```bash
tailscale ssh sab-ssd@pi-big '
  systemctl is-active gddp-intake;
  curl -s -o /dev/null -w "health %{http_code}\n" http://127.0.0.1:5050/health;
  tail -3 ~/heartbeat.log;
  gpgconf --kill gpg-agent; pass show gddp/webhook-secret | wc -c;  # expect 65
  sudo journalctl -u gddp-intake -b | grep -c "no webhook secret" # expect 0
'
curl -s -o /dev/null -w "funnel %{http_code}\n" https://pi-big.tail02ac6f.ts.net/health
```

Agent-environment gotchas: sandboxed Bash breaks `tailscale ssh` (hangs, exit 144) — needs sandbox disabled; plain `ssh sab-ssd@pi-big` fails host-key verification, use `tailscale ssh`; zsh aborts compound commands on failed globs.

## Not yet done / next

1. **X1 shakedown**: real issue/PR on a covered repo → confirm row lands in events table and heartbeat picks it up. The live path has never carried a real event.
2. Live-fire integrity lane (`--integrity on` real run), reconciliation pass (GDAD→Deprecated), set `retry_budget` in a project.yaml, integrity-lane subprocess timeout.
3. Standing rules: acceptance is human-only (`accept_node`); worst-of integrity combiner is SETTLED doctrine — do not weaken.
