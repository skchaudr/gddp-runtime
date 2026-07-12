# Live dispatch checklist

Gates for intent → planning → execution. See `TOPOLOGY.md` for hosts and URLs.

---

## 1. Intent (before anyone writes a plan)

- [ ] **Which graph node** is this work for?
- [ ] **Which machine owns the queue** for this job? (Tailscale name, e.g. `sab-mini`)
- [ ] **Will this job still be open tomorrow?** If yes, intake and webhooks need durable services (launchd + funnel), not a terminal session.
- [ ] **Where will the return-path webhook land?** Same machine as the queue row.
- [ ] **`TOPOLOGY.md`** — production host and public webhook URL noted.

Don't proceed if the job and webhooks are on different machines without an explicit plan for that.

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

**Production intake:**

- [ ] launchd (`MINI_HEARTBEAT_ARM=1`), not bare `python3 scripts/intake_server.py` in a shell.
- [ ] Public URL via **Tailscale Funnel** (or equivalent service), not a one-off cloudflared PID.
- [ ] One control plane — disarm old host before arming new.

**GitHub webhooks (repoint or new hook):**

- [ ] PATCH with JSON `config` body (`url`, `content_type`, `secret`) — `gh -f url=` alone does not work.
- [ ] Ping or delivery log shows **200** to the expected URL.

**Return path:**

- [ ] **GitHub redelivery** of a signed event, or saved payload with valid HMAC.
- [ ] New row in `events`; receipt path completes.

**When finished:**

- [ ] Temporary tunnels stopped; temporary hooks deactivated.
- [ ] Handoff: target machine, `git log -1`, intake up/down, webhook URL, job id.
- [ ] **`accept_node`** is human-only (verdict ≠ acceptance).

---

## Related

- `TOPOLOGY.md` — hosts, paths, URLs
- `deploy/mini-heartbeat/CUTOVER.md` — migration steps
- `docs/postmortem-canary-scope-2026-07-12.md` — Jul 12 incident
- `AGENTS.md` — agent session workflow