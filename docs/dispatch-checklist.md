# Live dispatch checklist

Plain-language gates for intent → planning → execution. Read `TOPOLOGY.md`
for where things run. Lessons from Jul 11–12 canary / cutover.

---

## 1. Intent (before anyone writes a plan)

Answer these out loud or in a handoff — not in your head.

- [ ] **Which graph node** is this work for?
- [ ] **Which machine owns the queue** for this job? (Tailscale name, e.g. `sab-mini`)
- [ ] **Will this job still be open tomorrow?** If yes, intake and webhooks must be on **durable** services (launchd + funnel), not a terminal session.
- [ ] **Where will the return-path webhook land?** Same machine as the queue row.
- [ ] Read **`TOPOLOGY.md`** — confirm production host and public webhook URL.

Stop if intent spans machines without saying so (e.g. job on mini, webhooks on pi-big).

---

## 2. Planning (before merge, dispatch, or arm)

First line of the plan:

```text
Target machine: sab-mini
```

Then:

- [ ] **Quote the node constraint** from `gddp-config` — copy/paste, not paraphrase.
- [ ] **Verify claims on the target machine** — SSH there, or say explicitly that a claim is unverified.
- [ ] Treat plan premises as **hypotheses** until checked on that host (git state, dirty files, handoff age).
- [ ] **Reviewer on a different machine** cannot confirm the target's worktree — do not promote guesses to facts.
- [ ] Note **webhook URL + hook id** if the return path depends on GitHub delivery.
- [ ] If using a **temporary** tunnel or hook for a test: write down what gets torn down when done.

---

## 3. Executing (before and during the run)

**Before starting intake / pointing webhooks:**

- [ ] `bash deploy/mini-heartbeat/bin/smoke.sh` passes on the target host.
- [ ] `curl -s http://127.0.0.1:5050/health` → ok with webhook verification enabled.
- [ ] Bad HMAC on `/webhook` → **401** (not 200, not open intake).
- [ ] Job row exists in **`db/queue.db` on the same host** that intake uses.

**Production path (not a quick terminal test):**

- [ ] Intake via **launchd** (`MINI_HEARTBEAT_ARM=1`), not bare `python3 scripts/intake_server.py` left running in a shell.
- [ ] Public URL via **Tailscale Funnel** (or other service), not a one-off cloudflared PID.
- [ ] Only **one** control plane armed — disarm the old host before arming the new one.

**GitHub webhooks (repoint or new hook):**

- [ ] PATCH with JSON `config` body (`url`, `content_type`, `secret`) — `gh -f url=` alone does not work.
- [ ] Ping or delivery log shows **200** to the URL you expect.

**Return path / live proof:**

- [ ] Use **GitHub redelivery** of a real signed event, not a hand-rolled curl pretending to be GitHub.
- [ ] Confirm new row in `events` and receipt path completes.

**When finished:**

- [ ] Temporary tunnels stopped; temporary hooks deactivated.
- [ ] Handoff: target machine, `git log -1`, intake up/down, webhook URL, job id.
- [ ] Verdict is not acceptance — **`accept_node` is human-only**.

---

## Related

- `TOPOLOGY.md` — hosts, paths, URLs
- `deploy/mini-heartbeat/CUTOVER.md` — migration steps
- `docs/postmortem-canary-scope-2026-07-12.md` — what went wrong
- `AGENTS.md` — agent session workflow