# Live dispatch checklist

A reference guide for when you want to run the loop.

Three stages covered: intent → planning → execution. See `TOPOLOGY.md` for hosts and URLs.

---

## 1. Intent (before planning begins)

Before anyone writes a plan, nail down where the work lives and how long it will run. These are the decisions that prevent a job on one machine from waiting on a webhook that hits another.

### Questions to answer

- [ ] **Which graph node is this work for?**
- [ ] **Which machine holds `db/queue.db` for this job?** Use the Tailscale name (e.g. `sab-mini`). The job row, `events` table, and heartbeat all live on that host.
- [ ] **Will this job still be open after the current session ends?** If yes, intake and the public URL need to outlive the session — see section 3.
- [ ] **Which URL will GitHub call for the return path?** That URL must reach intake on the same host as the queue DB.
- [ ] **Have you read `TOPOLOGY.md` for the current production host and public webhook URL?**

### When the queue host and the webhook host differ

GitHub will still deliver the event. It just lands in the wrong place — a different `db/queue.db`, or a host that ignores it because there is no matching job row. The job you care about stays stuck waiting for an event that never joins its queue.

That is what happened on Jul 12 with the canary: the job lived in mini's queue, the merged PR webhook hit pi-big (which correctly ignored it), and mini's tunnel was already dead anyway.

---

## 2. Planning (before merge, dispatch, or arm)

The plan should make the target machine obvious and leave unverified claims labeled as unverified.

### First line of the plan

```text
Target machine: sab-mini
```

### Before you merge, dispatch, or arm

- [ ] **The node constraint is quoted from `gddp-config`** — copy/paste, not paraphrase.
- [ ] **Claims about the target machine were checked via SSH**, or explicitly marked unverified in the plan.
- [ ] **Plan premises are treated as unverified** until checked on that host (git state, dirty files, handoff age).
- [ ] **If the reviewer is on a different machine**, worktree claims about the target require SSH to confirm — not inference from the reviewer's own checkout.
- [ ] **If the return path uses GitHub delivery**, the plan notes the webhook URL and hook id.
- [ ] **If the plan uses a temporary tunnel or hook**, it says what gets torn down when the work is done.

---

## 3. Executing (before and during the run)

### Before starting intake or pointing webhooks

These checks run on the machine that will own the queue. Today that is `sab-mini`.

- [ ] `bash deploy/mini-heartbeat/bin/smoke.sh` passes on the target host.
- [ ] `curl -s http://127.0.0.1:5050/health` returns ok with webhook verification enabled.
- [ ] A POST to `/webhook` with a bad HMAC signature returns **401** — intake is verifying signatures, not accepting everything.
- [ ] The job row you care about is in `db/queue.db` on the same host as intake.

### Intake and public URL

You start launchd and funnel from a shell. That is normal. What matters is what keeps running after the shell or agent session ends.

- [ ] **Intake is registered with launchd** — `MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh`
  - macOS keeps `com.gddp.intake` running after you disconnect. After a reboot, launchd can restart it.
  - A bare `python3 scripts/intake_server.py` in a session only lives as long as that session's process tree. When the session ends, intake stops. GitHub still POSTs to the hook URL, but nothing is listening — deliveries fail in GitHub's log as 502 or connection errors.

- [ ] **The public URL is Tailscale Funnel** — `tailscale funnel --bg --https=443 5050` on mini
  - The 12 production hooks point at a stable hostname: `https://sab-mini.tail02ac6f.ts.net/webhook`.
  - A trycloudflare one-liner gives a random URL tied to one `cloudflared` process. When that process dies, the URL dies. On Jul 11 the hook still pointed at a dead trycloudflare URL while the job row was still sitting in mini's queue.

- [ ] **Only one control plane is armed** — disarm the old host before arming the new one, so two intakes and two heartbeats are not dispatching in parallel.

### GitHub webhooks

When you repoint or create a hook, send a JSON body for the `config` block. The flat `gh -f url=` form does not update the URL even when the API response looks fine. On Jul 12 the cutover looked complete until we re-read all 12 hooks and found they still pointed at pi-big.

- [ ] The PATCH includes `url`, `content_type`, and `secret` inside `config` (JSON body).
- [ ] A ping or a recent delivery in GitHub's hook UI shows **200** to the URL you expect.

### Return path

You are proving this chain: GitHub signs a payload → funnel → intake verifies HMAC → a row lands in `events` → heartbeat and the router finish the job.

- [ ] You used **GitHub redelivery** of a real signed event, or replayed a saved payload with a valid HMAC — not a hand-inserted sqlite row.
- [ ] A new row shows up in `events`, and the receipt path completes for that job.

### When you used a temporary tunnel or hook

If the run used a one-off tunnel or a canary-only hook — not the 12 production hooks — tear those down when the work is done.

- [ ] The temporary tunnel process is stopped and the temporary hook is deactivated.
  - GitHub keeps retrying whatever URL is configured. A hook left pointing at a torn-down tunnel shows 502s in the delivery log and looks like production is broken when it is really stale config.

### Handoff

Leave the next session enough context that nobody has to re-discover the machine, the URL, or the job id.

- [ ] The handoff names the target machine (Tailscale name), `git log -1`, whether intake is running under launchd, the webhook URL, and the job id.
- [ ] **`accept_node` remains human-only** — an evaluator verdict does not change graph status.

---

## Related

- `TOPOLOGY.md` — hosts, paths, URLs
- `deploy/mini-heartbeat/CUTOVER.md` — migration steps
- `docs/postmortem-canary-scope-2026-07-12.md` — Jul 12 incident
- `AGENTS.md` — agent session workflow