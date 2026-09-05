# Live dispatch checklist

Gates for intent → planning → execution under the GDDP runtime (`pi_rpc` persistent orchestrator and local heartbeat loop). See `TOPOLOGY.md` for host mappings.

---

## 1. Intent (before planning begins)

- [ ] **Bounded work as graph node** — work maps to exactly one node defined in `gddp-config/graphs/<project>/nodes/<node_id>.yaml`.
- [ ] **Schema validation** — node YAML validates via `gddp.py node validate`.
- [ ] **Queue host identified** — `sab-mini` owns `db/queue.db` for production.
- [ ] **Execution path chosen**:
  - **`pi_rpc` (primary)** — persistent per-project session (`z-ai/glm-5.2`), 12h idle timeout, single session worktree.
  - **`jobs adopt`** — out-of-runtime work adopted directly into heartbeat queue.
  - **Remote / webhook (legacy)** — only if using external GitHub runner (requires intake + funnel; see Legacy Webhook Track below).

---

## 2. Planning (before merge, dispatch, or arm)

First line of the plan:

```text
Target machine: sab-mini
```

### Pre-dispatch checks

- [ ] **Node constraint** quoted verbatim from `gddp-config`.
- [ ] **Claims checked on target host** via SSH or local inspection (never assumed without verification).
- [ ] **Git state & worktree** verified on target host:
  - Repository branch and upstream clean (`git status --short --branch`).
  - Session worktree clean and pointed at target project base.
- [ ] **Environment & model configuration**:
  - `GDDP_PI_RPC_MODEL="z-ai/glm-5.2"` (session orchestrator).
  - Worker subagents: `xai/grok-4.6` (concurrent cap: up to 5).
  - Watcher subagent: `deepseek/deepseek-v4-flash` (state polling; no sleep/spin loops).
  - Reviewers: single logical review pass (`deepseek-v4-pro` + `xai/grok-4.6` parallel with explicit focus, `openai-codex/gpt-5.6-sol`, `google/gemini-3.1-pro`), max one fix dispatch before evaluator handoff.

---

## 3. Execution & Monitoring (during the run)

### Heartbeat & runtime state

- [ ] **Heartbeat active** — launchd `com.gddp.heartbeat` loaded (or run manually via `deploy/mini-heartbeat/bin/smoke.sh`).
- [ ] **Job record present** — job row created in `db/queue.db` on target machine.
- [ ] **Spool directory healthy** — session directory initialized under `GDDP_ATTEMPT_SPOOL_DIR` (default `jobs/local-subprocess-spool/`).

### Invariants during execution

- [ ] **Orchestrator role boundaries**:
  - Session orchestrator oversees, synthesizes, and dispatches workers; does not edit code directly.
  - Worker subagents execute tasks inside the session worktree.
  - Workers do NOT commit or push; the runtime persists the result commit upon turn completion.
  - No live steering (`gddp steer` is operator-only).
- [ ] **Observability & stuck detection**:
  - Check event freshness: `stat <spool>/<session>/events.jsonl` (staleness > 30m with living PID = suspected stuck).
  - Check process liveness: `kill -0 <pid>`.
  - Check turn termination: presence of `exit.json` and `result.json`.
- [ ] **Lifecycle safety & cancellation**:
  - Never run `gddp jobs set <job> failed` on a live executor (causes late-result resurrection).
  - Aborting requires writing `cancel.requested` to the session spool.

### Ingest & Review

- [ ] **Local result collected** — commit SHA, cache report (`prompt_cache_report.json`), and exit status harvested from session worktree.
- [ ] **Evaluator receipt minted** — two-lane verification verdict in `gddp-config/verification/<project>/`.
- [ ] **Human acceptance gate** — `accept_node` is strictly operator-owned; verdicts are evidence, never automatic graph truth.

---

## Legacy Webhook Track (External / GitHub Webhook Only)

Use only when running remote runners that return via public GitHub webhooks:

- [ ] **Intake on launchd** — `MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh` (`127.0.0.1:5050/health` ok).
- [ ] **HMAC verified** — bad signature returns **401**.
- [ ] **Public funnel** — `tailscale funnel --bg --https=443 5050`.
- [ ] **Webhook config** — GitHub hook configured via JSON PATCH (`url`, `content_type`, `secret`).
- [ ] **Signed delivery** — delivery log shows **200**; event row added to `events`.
- [ ] **Teardown** — temporary tunnels and hooks deactivated after run.

---

## Related

- `TOPOLOGY.md` — hosts, paths, URLs
- `LOOP.md` — canonical 5-step operating loop
- `deploy/orchestrator/doctrine.md` — Pi orchestrator doctrine & steering boundaries
- `deploy/orchestrator/ADDENDUM-piobs.md` — session observability
- `docs/learning/postmortem-canary-scope-2026-07-12.md` — Jul 12 incident postmortem
- `AGENTS.md` — agent session workflow and co-authoring rules
