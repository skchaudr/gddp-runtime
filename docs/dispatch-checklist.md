# Live dispatch checklist

Gates for intent → planning → execution. See `TOPOLOGY.md` for hosts and URLs.

---

## 1. Intent (before anyone writes a plan)

- [ ] **Which graph node** is this work for?
- [ ] **Which machine holds `db/queue.db` for this job?** (Tailscale name, e.g. `sab-mini`) — the job row, `events`, and heartbeat all live on that host.
- [ ] **Will this job still be open after the current session ends?**
- [ ] **Which URL will GitHub call for the return path?** Must reach intake on the **same host** as that queue DB.
- [ ] **`TOPOLOGY.md`** — production host and public webhook URL noted.

**If job host ≠ webhook target:** GitHub delivers fine, but the event lands in a different queue (or gets ignored). The job stays stuck waiting. Jul 12 canary: job on mini, merge webhook hit pi-big — pi-big correctly ignored it; mini's tunnel was already dead.

---

## 2. Planning (before merge, dispatch, or arm)

First line of the plan:

```text
Target machine: sab-mini
```

Then:

- [ ] **Node constraint** quoted from `gddp-config` (copy/paste).
- [ ] **Claims checked on the target machine** via SSH, or marked unverified.
- [ ] Plan premises treated as unverified until checked on that host (git state, dirty files, handoff age).
- [ ] Reviewer on another machine: worktree claims about the target need SSH to confirm.
- [ ] **Webhook URL + hook id** noted if return path uses GitHub delivery.
- [ ] **Temporary** tunnel or hook: note what gets torn down when done.

---

## 3. Executing (before and during the run)

**Before starting intake / pointing webhooks:**

- [ ] `bash deploy/mini-heartbeat/bin/smoke.sh` passes on the target host.
- [ ] `curl -s http://127.0.0.1:5050/health` → ok with webhook verification enabled.
- [ ] Bad HMAC on `/webhook` → **401**.
- [ ] Job row in **`db/queue.db` on the same host** as intake.

**Intake and public URL (jobs that may outlive this session):**

You can run `arm.sh` and `tailscale funnel` from a shell — that's fine. What matters is **what keeps running after the shell exits**.

- [ ] **Intake via launchd** (`MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh`)
  - *Effect:* macOS owns the process. Agent disconnects → intake stays up. Reboot → launchd restarts it (if configured).
  - *vs bare `python3 scripts/intake_server.py`:* process is a child of the session. Session ends → intake stops → GitHub POSTs to a URL nothing is listening on.

- [ ] **Public URL via Tailscale Funnel** (`tailscale funnel --bg --https=443 5050` on mini)
  - *Effect:* stable hostname (`sab-mini.<tailnet>.ts.net`). GitHub hook URL stays valid across sessions.
  - *vs trycloudflare one-liner:* new random URL each run; URL dies when that `cloudflared` process dies. Jul 11: webhook still pointed at dead trycloudflare URL → **502**, while `job_*` row still sat in mini's queue waiting.

- [ ] **One control plane armed** — disarm old host before arming new (two intakes + two heartbeats = duplicate dispatch risk).

**GitHub webhooks (repoint or new hook):**

- [ ] PATCH with JSON `config` body (`url`, `content_type`, `secret`)
  - *Why:* `gh api … -f url=` does not update hook config; API returns 200 but URL unchanged. Jul 12 cutover looked done until we re-checked and all 12 still pointed at pi-big.
- [ ] Ping or delivery log shows **200** to the expected URL.

**Return path:**

- [ ] **GitHub redelivery** of a signed event, or saved payload with valid HMAC
  - *Why:* proves GitHub → funnel → intake → HMAC verify → `events` row. Skipping that chain only proves you can write to sqlite locally.
- [ ] New row in `events`; receipt path completes.

**When finished (temporary tunnel/hook only):**

- [ ] Tunnel process stopped; temporary hook deactivated
  - *Why:* GitHub keeps retrying the configured URL. A hook left pointing at a torn-down tunnel generates 502s and false "production is broken" signals.

**Handoff:**

- [ ] Target machine, `git log -1`, intake running (launchd label), webhook URL, job id.
- [ ] **`accept_node`** is human-only — evaluator verdict does not flip graph status.

---

## Related

- `TOPOLOGY.md` — hosts, paths, URLs
- `deploy/mini-heartbeat/CUTOVER.md` — migration steps
- `docs/postmortem-canary-scope-2026-07-12.md` — Jul 12 incident
- `AGENTS.md` — agent session workflow