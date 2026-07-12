# Live dispatch checklist

A reference guide for when you want to run the loop.

Three stages covered: intent → planning → execution. See `TOPOLOGY.md` for hosts and URLs.

---

## 1. Intent (before planning begins)

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

### Before starting intake or pointing webhooks

These checks happen on the machine that will own the queue — today that is `sab-mini`.

- [ ] `bash deploy/mini-heartbeat/bin/smoke.sh` passes on the target host.
- [ ] `curl -s http://127.0.0.1:5050/health` returns ok with webhook verification enabled.
- [ ] A POST to `/webhook` with a bad HMAC signature returns **401** (intake is verifying, not open).
- [ ] The job row you care about is in `db/queue.db` on **that same host** as intake.

### Intake and public URL

You start launchd and funnel from a shell — that is normal. The question is what still runs after you close the shell or the agent session ends.

- [ ] **Intake is registered with launchd** — `MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh`
  - macOS keeps `com.gddp.intake` running after disconnect. On reboot, launchd can restart it.
  - A bare `python3 scripts/intake_server.py` in a session is only alive while that session's process tree is alive. When the session ends, intake stops. GitHub still POSTs to the hook URL; nothing listens → delivery failures.

- [ ] **Public URL is Tailscale Funnel** — `tailscale funnel --bg --https=443 5050` on mini
  - GitHub hooks point at a stable hostname: `https://sab-mini.tail02ac6f.ts.net/webhook`.
  - A trycloudflare one-liner gives a random URL tied to one `cloudflared` process. When that process dies, the URL dies. Jul 11: the hook still pointed at a dead trycloudflare URL (502) while the job row was still waiting in mini's queue.

- [ ] **Only one control plane is armed** — disarm the old host before arming the new one, so you do not get two intakes and two heartbeats dispatching against each other.

### GitHub webhooks

When you repoint or create a hook, use a JSON body for the `config` block. The flat `gh -f url=` form does not update the URL even when the API looks successful — Jul 12 cutover appeared done until we re-read all 12 hooks and they still pointed at pi-big.

- [ ] PATCH includes `url`, `content_type`, and `secret` inside `config` (JSON body).
- [ ] Ping or a recent delivery in GitHub's hook UI shows **200** to the URL you expect.

### Return path

The return path is the chain you are actually trying to prove: GitHub signs a payload → funnel → intake verifies HMAC → row lands in `events` → heartbeat and router do their work.

- [ ] Use **GitHub redelivery** of a real signed event, or replay a saved payload with a valid HMAC — not a hand-inserted sqlite row.
- [ ] A new row shows up in `events`, and the receipt path completes for that job.

### When you used a temporary tunnel or hook

If the run used a one-off tunnel or a canary-only hook (not the 12 production hooks), tear those down explicitly when the work is done.

- [ ] Temporary tunnel process stopped; temporary hook deactivated.
  - GitHub keeps retrying whatever URL is configured. A hook left on a dead tunnel produces 502s in the delivery log and looks like production is broken when it is just stale config.

### Handoff

Leave the next session enough to avoid re-archaeology.

- [ ] Target machine (Tailscale name), `git log -1`, whether intake is running under launchd, webhook URL, job id.
- [ ] **`accept_node`** remains human-only — an evaluator verdict does not change graph status.

---

## Related

- `TOPOLOGY.md` — hosts, paths, URLs
- `deploy/mini-heartbeat/CUTOVER.md` — migration steps
- `docs/postmortem-canary-scope-2026-07-12.md` — Jul 12 incident
- `AGENTS.md` — agent session workflow