# Live dispatch checklist

A reference guide for when you want to run the loop.

Three stages: intent, planning, execution. For hosts and URLs, see `TOPOLOGY.md`.

Each stage below follows the same shape: a short intro, then subsections with a line of context and a checklist.

---

## 1. Intent

Before anyone writes a plan, decide where the work lives, how long it will run, and where GitHub deliveries must land.

### Graph node and queue host

- [ ] **Graph node identified.** You know which node in `gddp-config` this work is for.
- [ ] **Queue host identified.** You know which machine holds `db/queue.db` for this job (Tailscale name, e.g. `sab-mini`). The job row, `events` table, and heartbeat all live on that host.
- [ ] **Job duration considered.** You know whether this job will still be open after the current session ends. If it will, intake and the public URL must outlive the session — see section 3.

### Return path and topology

- [ ] **Return-path URL identified.** You know which URL GitHub will call. That URL must reach intake on the same host as the queue DB.
- [ ] **Topology read.** You have read `TOPOLOGY.md` for the current production host and public webhook URL.

### Queue host and webhook host must match

GitHub will still deliver the event if the hosts differ. The event lands in the wrong `db/queue.db`, or on a host that ignores it because there is no matching job row. The job stays stuck waiting for an event that never joins its queue.

On Jul 12 with the canary, the job lived in mini's queue, the merged PR webhook hit pi-big (which correctly ignored it), and mini's tunnel was already dead.

---

## 2. Planning

Before merge, dispatch, or arm, the plan should name the target machine and leave unverified claims labeled as unverified.

### Target machine

```text
Target machine: sab-mini
```

### Plan contents

- [ ] **Constraint quoted.** The node constraint is copied from `gddp-config`, not paraphrased.
- [ ] **Claims verified or labeled.** Claims about the target machine were checked via SSH, or marked unverified in the plan.
- [ ] **Premises not assumed.** Git state, dirty files, and handoff age on the target host are checked before you treat plan premises as fact.
- [ ] **Cross-machine review bounded.** If the reviewer is on a different machine, worktree claims about the target require SSH — not inference from the reviewer's own checkout.
- [ ] **Webhook noted.** If the return path uses GitHub delivery, the plan includes the webhook URL and hook id.
- [ ] **Teardown noted.** If the plan uses a temporary tunnel or hook, it says what gets torn down when the work is done.

---

## 3. Execution

Before and during the run, confirm intake, the public URL, and webhooks on the machine that owns the queue. Today that is `sab-mini`.

### Pre-flight on the queue host

- [ ] **Smoke passed.** `bash deploy/mini-heartbeat/bin/smoke.sh` passes on the target host.
- [ ] **Health ok.** `curl -s http://127.0.0.1:5050/health` returns ok with webhook verification enabled.
- [ ] **HMAC enforced.** A POST to `/webhook` with a bad signature returns **401**.
- [ ] **Job on same host.** The job row is in `db/queue.db` on the same host as intake.

### Intake and public URL

You may start launchd and funnel from a shell. What matters is what keeps running after the shell or agent session ends.

- [ ] **Intake on launchd.** `MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh` — macOS keeps `com.gddp.intake` running after disconnect and can restart it after reboot. A bare `python3 scripts/intake_server.py` in a session dies with the session; GitHub still POSTs, nothing listens, deliveries show 502 or connection errors.

- [ ] **Public URL on funnel.** `tailscale funnel --bg --https=443 5050` on mini — the 12 production hooks use a stable hostname (`https://sab-mini.tail02ac6f.ts.net/webhook`). A trycloudflare one-liner ties the URL to one `cloudflared` process; when that process dies, the URL dies. On Jul 11 the hook still pointed at a dead trycloudflare URL while the job row waited in mini's queue.

- [ ] **Single control plane.** The old host is disarmed before the new one is armed, so two intakes and two heartbeats are not running in parallel.

### GitHub webhooks

Use a JSON body for the `config` block when you repoint or create a hook. The flat `gh -f url=` form does not update the URL even when the API response looks fine. On Jul 12 the cutover looked complete until we re-read all 12 hooks and found they still pointed at pi-big.

- [ ] **PATCH uses JSON config.** The request includes `url`, `content_type`, and `secret` inside `config`.
- [ ] **Delivery confirmed.** A ping or a recent delivery in GitHub's hook UI shows **200** to the expected URL.

### Return path

You are proving: GitHub signs a payload → funnel → intake verifies HMAC → a row lands in `events` → heartbeat and the router finish the job.

- [ ] **Signed delivery used.** GitHub redelivery of a real event, or replay of a saved payload with valid HMAC — not a hand-inserted sqlite row.
- [ ] **Receipt completed.** A new row appears in `events` and the receipt path completes for that job.

### Temporary tunnel or hook

If the run used a one-off tunnel or canary-only hook — not the 12 production hooks — tear it down when the work is done. GitHub keeps retrying the configured URL; a hook on a dead tunnel shows 502s and looks like production is broken when it is stale config.

- [ ] **Temporary infra removed.** Tunnel stopped; temporary hook deactivated.

### Handoff

- [ ] **Context recorded.** Target machine (Tailscale name), `git log -1`, intake running under launchd, webhook URL, job id.
- [ ] **Acceptance boundary clear.** `accept_node` is human-only; evaluator verdict does not change graph status.

---

## Related

- `TOPOLOGY.md` — hosts, paths, URLs
- `deploy/mini-heartbeat/CUTOVER.md` — migration steps
- `docs/postmortem-canary-scope-2026-07-12.md` — Jul 12 incident
- `AGENTS.md` — agent session workflow