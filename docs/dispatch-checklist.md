# Live dispatch checklist

A reference guide for when you want to run the loop.

Three stages covered: intent → planning → execution. See `TOPOLOGY.md` for hosts and URLs.

---

## 1. Intent (before planning begins)

- [ ] **Have bounded work worth preserving as intent** — the reason to open the loop at all
- [ ] **Work maps to one node in the schema format** — `gddp-config/schemas/v1/node.yaml`; draft with the node CLI (`gddp.py node rapid`), check with `gddp.py node validate`
- [ ] **Know which node** — it lives in the project's own repo at `gddp/nodes/<node>.yaml`; the repo owns its graph, gddp-config is not its warehouse
- [ ] **Know which host holds `db/queue.db`** — `TOPOLOGY.md`; production queue on `sab-mini` today
- [ ] **Know the return-path URL GitHub will call** — same host as that queue; exact URL in `TOPOLOGY.md`
- [ ] **If the job outlasts your session, arm intake + funnel before you leave** — `deploy/mini-heartbeat/bin/arm.sh` (see §3)

### When the queue host and the webhook host differ

GitHub delivers to the URL on the hook. A different host than your job's queue means the event never joins your job. Jul 12 canary: job on mini, merge webhook hit pi-big, mini's tunnel already dead.

---

## 2. Planning (before merge, dispatch, or arm)

Merge, dispatch, and arm are the usual gates — same checklist if you are reviewing a plan, repointing webhooks, or picking up a multi-day job.

Plan premises are claims, not facts. A stale handoff or a dirty worktree on the target quietly invalidates them — check on the host itself, not from your own checkout.

### First line of the plan

```text
Target machine: sab-mini
```

- [ ] **Constraint quoted verbatim from the node spec**
- [ ] **Claims about the target machine checked via SSH, or marked unverified**
- [ ] **Git state, dirty files, and handoff age checked on that host**
- [ ] **If you review from another machine, you SSH to the target to confirm worktree claims**
- [ ] **Webhook URL and hook id listed when the return path uses GitHub**
- [ ] **Temporary tunnel or hook: teardown listed for when the work is done**

---

## 3. Execution (before and during the run)

On the machine that owns the queue (`sab-mini` today).

### Before intake or webhooks

Prove the queue host is healthy before any public URL points at it.

- [ ] **Smoke passed** — `bash deploy/mini-heartbeat/bin/smoke.sh`
- [ ] **Health ok** — `curl -s http://127.0.0.1:5050/health`, webhook verification enabled
- [ ] **HMAC enforced** — bad signature on `/webhook` returns **401**
- [ ] **Job row in that host's `db/queue.db`**

### Intake and public URL

What matters is not that you can start these, but that they keep running after your shell or session ends.

- [ ] **Intake on launchd** — `MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh`; survives after you disconnect. Session-started intake dies with the session; GitHub POSTs into 502s.
- [ ] **Public URL on funnel** — `tailscale funnel --bg --https=443 5050`; stable hostname for the 12 hooks. Ephemeral trycloudflare URLs die with the process.
- [ ] **One control plane** — old host disarmed before new host armed

### GitHub webhooks

A cutover can look done and not be. On Jul 12 all 12 hooks still pointed at pi-big until we re-read each one.

- [ ] **PATCH uses JSON `config`** — `url`, `content_type`, `secret`; flat `gh -f url=` leaves the old URL in place
- [ ] **Delivery shows 200** — ping or recent delivery in GitHub's hook UI

### Return path

You are proving the whole chain: GitHub signs → funnel → intake verifies HMAC → row in `events` → receipt.

- [ ] **Signed delivery** — GitHub redelivery or replay with valid HMAC; proves GitHub → funnel → intake → `events` row
- [ ] **Receipt completes** for that job

### Temporary tunnel or hook

- [ ] **Tunnel stopped and temporary hook deactivated when done** — GitHub keeps retrying; dead URL shows 502s in the log

### Handoff

- [ ] **Target machine, `git log -1`, intake under launchd, webhook URL, job id**
- [ ] **`accept_node` is yours** — verdict alone does not change graph status

---

## Related

- `TOPOLOGY.md` — hosts, paths, URLs
- `deploy/mini-heartbeat/CUTOVER.md` — migration steps
- `docs/postmortem-canary-scope-2026-07-12.md` — Jul 12 incident
- `AGENTS.md` — agent session workflow