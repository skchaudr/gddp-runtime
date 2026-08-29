# Stateless supervision cycle for pi_rpc — design draft

**Status:** research / proposal only. No code changed.
**Date:** 2026-08-29
**Origin:** design exploration follow-up to `.handoffs/106-orchestrator-context-contract-gap.md` and `docs/current/Smart Supervisor vs. Dumb Orchestrator.md`.

**Inputs read:**
- `docs/current/Smart Supervisor vs. Dumb Orchestrator.md`
- `.handoffs/106-orchestrator-context-contract-gap.md`
- `docs/proposals/pure-orchestration-not-execution.md`
- `docs/proposals/LOOP.md` (note: not repo-root `LOOP.md`; that path does not exist)
- `scripts/adapters/pi_rpc_adapter.py` (full)
- `scripts/runtime/spike/pi_rpc_persistent_spike.py` + `pi_rpc_persistent_spike_results.json`
- `scripts/runtime/heartbeat/reconciler.py` (status poll path)
- `scripts/jobs_status.py` (executor attempt probe)
- `docs/current/dispatch-checklist.md` (operator stuck heuristic)
- `scripts/adapters/executor_protocol.py` (`SessionStatus`)
- `scripts/runtime/verification/semantic/context_builder.py` (evaluator pointer contract, for contrast)

Claim tags used below:
- **[VERIFIED]** — grounded in cited source in this repo.
- **[ASSUMPTION]** — design inference, not proven in source.
- **[GAP]** — essay/desired capability that current transport does not expose.

---

## 0. Problem restatement (from sources)

**[VERIFIED — handoff 106]** Live orchestrator sessions carried 120K–180K+ context because the model researched GDDP (`read`/`bash` dominate; `subagent` is minority). The orchestrator has behavioral prose (`_PACKET_PREAMBLE`) but no pointer contract, zone ordering, or coverage measurement — unlike the evaluator.

**[VERIFIED — essay]** Desired posture is a dumb supervisor: small state (expected workers, alive?, progressing?, waiting?, blocked?, intervention count), small actions (start / inspect / message / nudge / replace / escalate / nop), optionally a *stateless* cycle: desired set → actual sessions → compare → inspect → bounded act → exit.

**[VERIFIED — pure-orchestration proposal]** Observational lifecycle authority is safe today; safe cancel+redispatch is not. V1 should detect/report stalls, not mark live jobs failed.

**[VERIFIED — LOOP]** Graph nodes are intent; heartbeat dispatches packets; return → evaluate → human accepts. `gddp steer` is the operator mid-turn channel. Graph truth is human-only.

---

## 1. Inventory: what Pi RPC actually exposes (from source)

### 1.1 Process topology

**[VERIFIED — `pi_rpc_adapter.py` module docstring + `dispatch`/`run_orchestrator`]**
Fork A: **one long-lived `pi --mode rpc` process per project**, not per node. `dispatch()` enqueues attempt dirs under `spool/_orchestrators/<project_key>/inbox/` and either attaches to a live orchestrator PID or spawns `python -m adapters.pi_rpc_adapter --run-orchestrator <dir>`. That child owns the Pi process (stdin/stdout JSONL). One session worktree for the orchestrator's life.

**[VERIFIED]** Worker "subagents" are **not** separate GDDP-managed Pi RPC sessions. They are instructed via preamble (`subagent` tool, up to 5 workers + 1 watcher + reviewers). The adapter never lists, polls, or addresses worker sessions over RPC.

**[GAP vs essay]** Essay's "read actual Pi sessions" (plural worker sessions) does **not** match the current adapter. At the RPC layer GDDP sees **one** session: the project orchestrator. Worker persistence-as-substitute-for-orchestrator-context is therefore **aspirational** relative to this codebase unless workers become first-class RPC sessions.

**[VERIFIED]** RPC ownership is exclusive: only `run_orchestrator`'s `_RpcClient` holds Pi stdin. There is no attach/socket API for a second supervisor client. A "stateless cycle" that wants live RPC mid-turn must either (a) live *inside* that process, (b) use file side-channels (`steer.jsonl`, cancel markers, events on disk), or (c) spawn a *new* Pi process against `--session <sessionFile>` **[ASSUMPTION: concurrent second process against same session file is unsafe / untested here]**.

### 1.2 RPC methods / events used in production adapter

| Capability | How | Tag |
|---|---|---|
| Start Pi | `pi --mode rpc --model … --session-dir … --tools …` optional `--session` | **[VERIFIED]** |
| `prompt` | `{"type":"prompt","message":…}` then wait for `agent_end` | **[VERIFIED]** |
| `get_state` | once at bootstrap; reads `sessionFile` / `session_file` | **[VERIFIED]** |
| Mid-turn operator inject | `{"type":"steer","message":…}` while turn running | **[VERIFIED]** |
| Post-`agent_end` follow-up | `{"type":"prompt",…}` (comment: bare `prompt` mid-turn is **rejected**) | **[VERIFIED]** |
| Soft interrupt on turn error | `{"type":"abort"}` `wait_response=False` if process still alive | **[VERIFIED]** |
| Turn boundary | event `type`/`event.type` == `agent_end` | **[VERIFIED]** |
| Cancel packet | write `cancel.requested`; **no** per-packet RPC abort (shared process) | **[VERIFIED]** |
| Status for reconciler | **spool files only** (`exit.json`, `pid`, `supervisor.pid`) — **not** live `get_state` | **[VERIFIED]** |

Spike-only (in spike client, **not** called by production adapter loop after bootstrap):

| Method | Tag |
|---|---|
| `get_messages` | **[VERIFIED in spike]** |
| Resume via `--session <sessionFile>` after SIGKILL | **[VERIFIED in spike]** |
| Feasibility note suggesting cancel→abort/kill | **[VERIFIED as spike text]**; production cancel is file-marker only |

### 1.3 `get_state` observables (spike-recorded keys)

**[VERIFIED — `pi_rpc_persistent_spike_results.json` `state_keys`]**
`autoCompactionEnabled`, `followUpMode`, `isCompacting`, `isStreaming`, `messageCount`, `model`, `pendingMessageCount`, `sessionFile`, `sessionId`, `steeringMode`, `thinkingLevel`. Nested `model` includes `contextWindow`, provider, costs, etc.

**[VERIFIED]** Adapter uses only `sessionFile` / `session_file` from that payload.

**Not present in verified `get_state` keys:** worker/subagent inventory, idle boolean named `isIdle`, last-activity timestamp, tool hang state, "waiting for input" semantic, error classification beyond streaming/compacting flags.

**[ASSUMPTION]** `isStreaming==false` and `pendingMessageCount==0` after a prior `agent_end` ≈ session idle between turns. Not used by adapter today.

**[GAP]** Handoff 106's Pi harness `ctx.isIdle()` / `ctx.hasPendingMessages()` are extension APIs, **not** RPC methods in this adapter.

### 1.4 Event stream observables

**[VERIFIED — spike `event_types_observed`]**
`agent_start`, `agent_end`, `turn_start`, `turn_end`, `message_start`, `message_update`, `message_end`, `tool_execution_start`, `tool_execution_end`.

**[VERIFIED — adapter]** Events append to `attempt_dir/events.jsonl` (and briefly `orchestrator_dir/events.jsonl` at client create). Used today for cache-token extraction (`message_end` → `usage.cacheRead`), not for stall detection.

**[ASSUMPTION]** `tool_execution_*` payloads can identify tool name including `subagent`; this is **not** asserted or parsed in GDDP source. Without a verified schema, "count live workers from events" remains a **GAP**.

### 1.5 Adapter-level "idle" (not RPC)

**[VERIFIED]** `_DEFAULT_IDLE_TIMEOUT_S = 43200` (12h): after inbox drains, orchestrator polls inbox then exits, killing Pi and removing worktree. This is **process/inbox idle**, not model-turn idle.

**[VERIFIED]** Orchestrator dir `state` file: `busy` | `idle` | `exited` (written by `run_orchestrator`).

### 1.6 How worker subagents appear at the RPC layer

**[VERIFIED]** They appear only as model tool use inside the single orchestrator session (tools string includes `subagent`). GDDP does not open RPC to them, does not store their session ids, and does not map `node_id → worker session`.

**[VERIFIED — `_observability_env` comment]** Per-node OBS tags were dropped from the parent env because the parent spans many packets; comment claims worker subagent sessions can carry per-node identity — that is a **product/harness claim**, not something the adapter implements or queries.

---

## 2. Inventory: what currently tracks orchestrator/worker liveness

### 2.1 Spool (pi_rpc)

**Per attempt** (`spool/<session_id>/`):
`packet.json`, `command.json`, `supervisor.pid`, `pid` (Pi pid while turn active), `session_file`, `worktree_path`, `events.jsonl`, `steer.jsonl`, `steer.error.txt`, `cancel.requested`, `prompt_cache_report.json`, `result.json`, `exit.json`.

**Per project orchestrator** (`spool/_orchestrators/<project>/`):
`pid`, `lock`, `state`, `current_attempt`, `worktree_path`, `inbox/*`, `pi-session/`, `events.jsonl`, optional `get_state_error.txt`.

**[VERIFIED — `read_pi_rpc_status`]** States: `completed` / `failed` (from `exit.json`), `running` (attempt `pid` alive), `dispatched` (supervisor pid alive, turn not started), else failed "without durable exit state".

### 2.2 Runtime DB + heartbeat

**[VERIFIED]** `executor_sessions` + `jobs`; reconciler polls `adapter.status(session_ref)` each tick; for `running` only promotes DB state if needed; does **not** implement events-mtime stall logic.

**[VERIFIED]** `dispatching_stale_after` / `missing_stale_after` default 30m for reservation/missing-from-executor cases — not "events silent while PID alive."

### 2.3 `jobs_status.py`

**[VERIFIED]** Operator show path probes **`local_subprocess`** spool status only. **No `pi_rpc` probe** in `jobs_status.py`.

### 2.4 Operator checklist (human, not automated)

**[VERIFIED — `docs/current/dispatch-checklist.md`]** Suspected stuck: `events.jsonl` staleness > 30m **and** living PID; also check `exit.json` / `result.json`. Never `jobs set failed` on a live executor.

### 2.5 Desired "worker set" today

**[VERIFIED]** There is **no** runtime object "desired workers: node → session." Closest truth sources:

| Layer | What it knows | Tag |
|---|---|---|
| Graph + heartbeat | Ready nodes → planned jobs → `executor_sessions` rows | **[VERIFIED]** |
| Orchestrator inbox | Queued attempt_dirs waiting for a turn | **[VERIFIED]** |
| `current_attempt` + `state=busy` | Which attempt is mid-turn | **[VERIFIED]** |
| Preamble | Soft concurrent worker budget (≤5) as LLM instruction | **[VERIFIED]** |
| Subagent sessions | — | **[GAP]** |

---

## 3. Design draft: stateless supervision cycle

### Framing correction (required)

Treat the essay's cycle as two possible scopes:

1. **Attempt-level supervision (fits today's transport):** supervise **GDDP attempts / project orchestrator process** — desired running packets vs spool+DB+events.
2. **Worker-level supervision (essay's sketch):** supervise **subagent workers** — requires either RPC/session inventory **[GAP]** or a new architecture (one Pi RPC session per worker).

The draft below is **attempt-level first**, with an explicit worker-level extension only where gaps are named.

---

### (a) Desired worker / work set — source of truth

**v1 desired set (attempt-level) — recommendation:**

```
desired = {
 project_id,
 attempts: [
 { job_id, node_id, attempt_index, session_id, session_db_id,
 expected_state ∈ {dispatched, running} }
 ]
}
```

**Source of truth priority [VERIFIED pieces + recommendation]:**

1. **DB `executor_sessions` where state ∈ {dispatched, running}** for the project — authoritative for "runtime believes this attempt is live." **[VERIFIED table usage]**
2. **Cross-check spool** via `read_pi_rpc_status` — durable adapter view. **[VERIFIED]**
3. **Orchestrator inbox + `current_attempt`** — distinguishes queued vs mid-turn. **[VERIFIED]**
4. **Graph ready nodes** — explain *why* new work should exist; do **not** alone imply a live worker (dispatch may be capacity-gated). **[VERIFIED LOOP/heartbeat]**
5. **Node packet** — contract for the attempt when inspecting; not the census of live workers. **[VERIFIED]**

**Do not** treat preamble "up to 5 workers" as desired set. **[VERIFIED: prose only]**

**Worker-level desired set [GAP]:** cannot be sourced from DB/spool today. Would require either:

- **[ASSUMPTION]** parsing `tool_execution_*` for open `subagent` calls, or
- **[ASSUMPTION]** Pi listing subagent sessions via some unexposed API, or
- architecture change: spawn workers as separate `pi --mode rpc` processes with attempt spool dirs GDDP already knows how to status.

---

### (b) Observable facts Pi RPC / spool can provide (verified only)

**Per project orchestrator process (spool, no live RPC attach needed):**

| Fact | Source | Tag |
|---|---|---|
| Supervisor/orchestrator process alive | `_orchestrators/.../pid` + `kill(pid,0)` | **[VERIFIED]** |
| Orchestrator phase | `state` ∈ busy/idle/exited | **[VERIFIED]** |
| Current attempt path | `current_attempt` | **[VERIFIED]** |
| Inbox depth | count `inbox/` entries | **[VERIFIED]** |
| Session worktree path | `worktree_path` | **[VERIFIED]** |
| Session file path (if turn started) | attempt `session_file` | **[VERIFIED]** |

**Per attempt (spool):**

| Fact | Source | Tag |
|---|---|---|
| Coarse status | `read_pi_rpc_status` → dispatched/running/completed/failed | **[VERIFIED]** |
| Cancel requested | `cancel.requested` exists | **[VERIFIED]** |
| Terminal exit | `exit.json` (returncode, cancelled, plumbing, error) | **[VERIFIED]** |
| Result handoff | `result.json` | **[VERIFIED]** |
| Event stream growth | `events.jsonl` size/mtime | **[VERIFIED files exist; checklist uses mtime]** |
| Operator steer pending/errors | `steer.jsonl`, `steer.error.txt` | **[VERIFIED]** |

**If a cycle *owns* the RPC client mid-turn (inside `run_orchestrator` only):**

| Fact | Source | Tag |
|---|---|---|
| Streaming? | `get_state().isStreaming` | **[VERIFIED key exists; unused]** |
| Compacting? | `get_state().isCompacting` | **[VERIFIED key]** |
| Pending messages | `get_state().pendingMessageCount` | **[VERIFIED key]** |
| Message count | `get_state().messageCount` | **[VERIFIED key]** |
| Turn still open | no `agent_end` since last `prompt` | **[VERIFIED wait loop]** |

**Not available as verified RPC facts:** per-worker liveness, "waiting for input" semantic, last *meaningful* activity (tool vs babble), architectural correctness, graph readiness.

**Proxy for "last meaningful activity" (recommended, still heuristic):**

- Prefer **worktree git dirty/mtime or required-artifact mtime** **[ASSUMPTION — checklist mentions watch diffs; not automated in reconciler]**
- Secondary: `events.jsonl` mtime / last `tool_execution_end` timestamp **[ASSUMPTION on payload fields]**
- Do **not** treat `message_update` alone as progress (can be pure narration). **[ASSUMPTION]**

---

### (c) Compare / decide — stall & blockage rules (grounded)

All rules below are **observational**. Escalation = report to operator / write a receipt. No `jobs set failed` on live attempts **[VERIFIED — pure-orchestration + checklist]**.

**Rule C1 — Dead supervisor, live DB claim**
IF `executor_sessions.state ∈ {dispatched,running}` AND orchestrator `pid` missing/dead AND no `exit.json`
THEN classify plumbing death / orphaned attempt → escalate (reconciler already maps "no durable exit" to failed via status poll — ensure supervisor cycle doesn't double-mutate). **[VERIFIED status path]**

**Rule C2 — Running PID, silent events**
IF attempt status `running` AND `events.jsonl` mtime older than `STALL_EVENTS_S` (checklist suggests 30m) AND Pi pid alive
THEN `suspect_stall` → inspect (C-inspect) → escalate or nudge. **[VERIFIED checklist heuristic; not coded]**

**Rule C3 — Busy forever without agent_end**
IF `state=busy` AND wall time since `busy` write (need timestamp file — **[GAP: `state` has no mtime contract]**; use events mtime or add `busy_since`) > `turn_timeout_s` (default 1800s **[VERIFIED]**)
THEN plumbing-class turn timeout — adapter already raises `_PlumbingError` when *its* wait exceeds timeout; an external cycle catching this is redundant unless the wait loop is wedged. **[VERIFIED internal timeout]**

**Rule C4 — Queued but never claimed**
IF attempt `dispatched` (supervisor alive) AND age > `QUEUE_STALE_S` AND `current_attempt` never equals this attempt
THEN escalate "starved in inbox" (capacity / stuck busy sibling). **[ASSUMPTION thresholds]**

**Rule C5 — Cancel without terminalization**
IF `cancel.requested` AND still `running` past grace
THEN escalate: soft cancel may wait until turn boundary; no hard kill of shared Pi for one packet **[VERIFIED]**.

**Rule C6 — Research / role drift (context blowup)** — *optional, attempt-level*
IF last N events show high `read`/`bash` vs low `subagent` **[ASSUMPTION: tool names parseable]** OR `messageCount` / context from usage climbs past budget
THEN escalate "orchestrator doing executor work" (handoff 106 pattern). This is the dumb supervisor catching the smart orchestrator's failure mode **without** understanding the node.

**Rule C7 — Worker-level stall**
**[GAP]** Skip in v1 unless tool-event schema is verified.

**Default:** if no rule fires → **do nothing**.

---

### (d) Bounded intervention set → concrete mechanisms

Map essay vocabulary onto **what exists**. Authority ceiling from pure-orchestration: observe + report; terminate only where a real primitive exists.

| Essay action | Concrete mechanism today | Safe? | Tag |
|---|---|---|---|
| **start worker** | Cannot start a subagent via RPC without a model turn. Options: (1) enqueue a new NodePacket / let heartbeat dispatch; (2) `steer`/`prompt` the *orchestrator* to dispatch workers (still LLM-mediated); (3) spawn separate Pi worker process **[not implemented]**. | (1) yes for new graph work; (2) weak; (3) new work | **[VERIFIED limits]** |
| **inspect worker** | Read spool: `events.jsonl` tail, `get_state` only if inside owner client, worktree `git status`/diff, `packet.json`. | yes (read-only) | **[VERIFIED / ASSUMPTION for git]** |
| **send message** | Append `steer.jsonl` → drained as RPC `steer` mid-turn or `prompt` when idle. Same channel as `gddp steer`. | yes | **[VERIFIED]** |
| **retry / nudge** | Steer with fixed template ("resume progress; do not research GDDP; dispatch workers"). **Not** redispatch job. | observationally ok | **[ASSUMPTION efficacy]** |
| **replace worker** | **No** subagent kill API in adapter. Replacing *attempt*: needs safe cancel primitive — **missing**. Soft: `cancel.requested` + human redispatch. | unsafe if DB-failed | **[VERIFIED gap]** |
| **report escalation** | Write `supervisor_escalation.json` under attempt/orchestrator dir; surface in `gddp watch` / jobs show; optional human notify. | yes | **[ASSUMPTION new artifact]** |
| **do nothing** | Exit cycle. | yes | — |
| **abort turn** | RPC `abort` only from owner client; kills in-flight turn, shared across batch packets. | dangerous / session-scoped | **[VERIFIED]** |
| **kill Pi process** | `killpg` on orchestrator — ends **all** in-flight packets for project; drains inbox as plumbing failures. | last resort | **[VERIFIED]** |

**v1 allowed actions for an automated cycle:** inspect (read), steer nudge (rate-limited), escalate (write), do nothing.
**v1 forbidden:** DB fail of live jobs, kill Pi except operator-approved, pretend cancel is terminal.

---

### (e) State that must persist between cycles (explicitly not in the model)

Store under spool (files are LOOP truth) and optionally index in DB later:

```
_orchestrators/<project>/supervisor/
 last_cycle.json # timestamp, decisions, rule ids fired
 intervention_counts.json # per attempt_id → {nudge, escalate, …}
 stall_watermarks.json # last events.jsonl size/mtime seen as "progress"
 escalations/*.json # durable human-facing receipts
```

**Must persist:**

| Field | Why | Tag |
|---|---|---|
| Intervention counts | Prevent nudge storms | essay + **[ASSUMPTION]** |
| Last progress watermark | Distinguish "still silent" from "silent since last check" | **[ASSUMPTION]** |
| Open escalations | Don't re-page every cycle | **[ASSUMPTION]** |
| Cycle config | `STALL_EVENTS_S`, max nudges | config |

**Must not persist in the model:** narrative of the graph, research notes, "what node 17 means," prior chain-of-thought. That is the essay's point and handoff 106's failure mode.

**Pi session file / message history** may persist for the *executor* session; the **supervisor cycle** should not read it into an LLM context by default. Inspect = structured facts only.

---

### (f) Interaction with one-persistent-orchestrator-per-project

**Recommendation: layer beneath, not wholesale replacement — yet.**

| Layer | Role | Tag |
|---|---|---|
| **Graph + heartbeat** | What work exists; dispatch packets | **[VERIFIED LOOP]** |
| **pi_rpc `run_orchestrator`** | Owns Pi process, prompts packets, persist_result, steer drain | **[VERIFIED]** |
| **LLM in that Pi session** | Today: "orchestrator" that calls `subagent` | **[VERIFIED preamble]** |
| **Stateless supervisor cycle (proposed)** | Outside the model: census desired attempts, read spool/DB, apply C-rules, steer/escalate/nop | this draft |
| **Evaluator + human** | Judge / accept | **[VERIFIED LOOP]** |

**Short term:** keep the persistent Pi session as the **execution host** (workers still need *some* intelligence to call tools). Add the dumb cycle as:

- a **heartbeat phase** (alongside `reconcile_sessions`), and/or
- a timer inside `run_orchestrator`'s `on_poll` (has RPC access) that only emits structured escalations/steers — **no** extra model turn for "thinking about supervision."

**Medium term (essay-complete):** shrink or eliminate the LLM's supervisory latitude:

1. Give the persistent session a **hard context contract** (handoff 106 fixes 1–3) so it cannot rediscover GDDP.
2. Move "are workers alive?" off the model onto the file/RPC supervisor.
3. If worker-level RPC sessions become real, the persistent "orchestrator" LLM can shrink toward a thin dispatcher—or disappear, with the runtime issuing worker prompts directly.

**Replacement condition:** only when "start worker" is a **runtime** primitive (spawn Pi or Task with known session id), not a hope that a smart model calls `subagent`. Until then, replacing the persistent orchestrator with a fully dumb cycle **cannot** execute nodes. **[VERIFIED topology]**

---

## 4. Half-page sketch: canonical-summary compaction (runtime-owned)

**Goal:** If a persistent smart model remains, collapse its context toward a **fixed supervisor summary**, not conversational memory of research.

**What the runtime must own for safety:**

1. **Canonical summary text** — byte-stable protocol zone, same idea as evaluator zones / `_PACKET_PREAMBLE`, but reduced to: worker liveness & forward progress; dispatch required workers; observe via spool/RPC facts; intervene only on concrete blockage; do not execute, research, adjudicate, or mutate graph. **[essay + handoff 106]**
2. **Pointer list, not blobs** — call `build_canonical_pointers()` (or a thinner orchestrator variant) so any allowed read is a named path; missing → `UNAVAILABLE`. **[VERIFIED evaluator pattern; handoff 106 fix #1]**
3. **Zone assembly** — protocol → project (empty or pointers) → node → attempt; never merge zones in one sort that busts prefix cache. **[VERIFIED evaluator comment pattern; adapter already has `TurnPrompt`]**
4. **Compaction trigger outside the model** — runtime decides when to destroy narrative (e.g. after `agent_end`, or when `messageCount` / usage exceeds budget). Must not rewrite history mid-tool-loop (handoff 106: `turn_end` compaction was harmful). Prefer settle boundaries. **[VERIFIED handoff]**
5. **What compaction may delete** — tool transcripts of research, assistant narration, redundant reads. **What it must re-inject every cycle** — the fixed summary + current structured supervisor state file (watermarks, open escalations, current attempt ids) + packet zones.
6. **Coverage measurement** — record which pointers were opened; alert if orchestrator reads outside the allowlist (detect research drift live). **[VERIFIED evaluator has this; orchestrator does not]**
7. **Conflict with 12h idle** — long-lived session retains excavated context until compact/exit. Runtime must either compact aggressively on settle, or end/resume session with `--session` and a **replaced** history that starts from the canonical summary **[ASSUMPTION: Pi resume semantics allow truncated history — not verified]**. Static `.pi/settings.json` `compaction.reserveTokens` is a ceiling, not a contract **[VERIFIED handoff]**.

**Safety line:** the model must not be the authority on what was compacted away. The runtime writes the post-compaction prompt; the model only continues from that prompt. If Pi's native compaction keeps a `CompactionEntry` summary the model wrote, treat that summary as **untrusted** and overwrite with the runtime's fixed supervisor summary on the next owned `prompt`. **[ASSUMPTION on CompactionEntry shape from handoff]**

---

## 5. V1 build sequence (proposal only)

1. **Census CLI/heartbeat tick:** desired attempts from DB ∩ spool status ∩ orchestrator `state`/`inbox`/`current_attempt`. No LLM.
2. **Stall detector:** implement checklist C2 (events mtime + pid) → `supervisor_escalation.json`.
3. **Rate-limited steer nudge** with fixed template; cap via intervention_counts.
4. **Handoff 106 context contract** on the persistent orchestrator (pointers + zones) so the smart layer stops manufacturing the problem the dumb layer detects.
5. **Defer** worker-level session inventory and cancel+redispatch until primitives exist.

---

## 6. Bottom line

The essay's dumb supervisor is the right *authority* shape for GDDP. Against **verified** `pi_rpc` source, that supervisor today can be **attempt/process-level and mostly spool-based**; it cannot yet "read actual Pi worker sessions," and it cannot safely "replace worker" or cancel+redispatch. Worker persistence substituting for orchestrator context is a **future transport property**, not a present adapter fact. A stateless cycle should sit as a **deterministic layer under** the persistent project Pi session, escalating and nudging from observables, while the remaining LLM (if any) is fenced by a runtime-owned canonical summary—not trusted to remember what supervising means.
