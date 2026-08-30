# Continuity boundary — what survives an executor turn, and what `--resume` would have to earn

**Status:** analysis / proposal. No code changed. Read-only lane feeding `cursor_cli_adapter.py`.
**Date:** 2026-08-29
**Lane:** cold-turn / stateless lifecycle architecture.

Claim tags: **[V]** grounded in a cited file in this repo or on this host · **[A]** inference · **[GAP]** does not exist today.

Sources read in full: `scripts/adapters/executor_protocol.py`, `scripts/adapters/pi_rpc_adapter.py`,
`scripts/adapters/session_prompt.py`, `scripts/adapters/local_subprocess_adapter.py` (dispatch path),
`scripts/runtime/heartbeat/dispatcher.py`, `scripts/runtime/heartbeat/state_recorder.py` (attempt allocation),
`scripts/runtime/heartbeat/reconciler.py` (retry path), `scripts/runtime/return_router.py` (retry path),
`scripts/local_agent_executor.py` (worktree/persist), `scripts/prompt_topology.py`,
`scripts/runtime/verification/semantic/context_builder.py`, `scripts/init_db.py`, `.pi/settings.json`,
`deploy/mini-heartbeat/env/gddp.env`, `docs/proposals/LOOP.md`, `docs/proposals/stateless-supervisor-cycle.md`,
`docs/current/Smart Supervisor vs. Dumb Orchestrator.md`, `.handoffs/106-*`, `.handoffs/107-*`,
`scripts/runtime/spike/cursor_cli_spike.py`, `scripts/runtime/spike/cursor_cli_spike_results.json`.

---

## 0. One thing to read first

GDDP already runs a cold-turn executor in production. The armed heartbeat's `local_subprocess` argv is
`pi … --print --no-session …` — session explicitly disabled, one process per attempt
(`deploy/mini-heartbeat/env/gddp.env:13`; `scripts/adapters/local_subprocess_adapter.py:29-30,51-96`). **[V]**

And `pi_rpc` has had a resume lever since it was written — `PiRpcAdapter(resume_session_file=…)` →
`command.json` → `pi --session <file>` (`scripts/adapters/pi_rpc_adapter.py:132,162-164,195-199,993,1042-1043`).
Nothing in the runtime has ever set it: `_build_adapter` passes only `repo`, `cwd`, `model`
(`scripts/runtime/heartbeat/dispatcher.py:198-209`), and no env var sets it
(`deploy/mini-heartbeat/env/gddp.env`). The only caller is a unit test
(`scripts/adapters/test_pi_rpc_adapter.py:284-304`). **[V]**

So the question is not "can we go cold." It is "has anything ever needed the alternative." Answer so far: no.

---

## 1. Inventory: state that survives between executor turns

Durability classes, per the operator sketch: **durable** (runtime guarantees it across process/host death) ·
**opportunistic** (nice if present, never depended on) · **disposable** (may be destroyed at any turn boundary) ·
**transport-specific** (exists only for one adapter shape).

### 1.1 Durable today

| # | State | Where it lives | Class | What breaks if dropped |
|---|---|---|---|---|
| 1 | Git object store + per-attempt result ref `gddp/attempt-<execution_attempt_id>` | `scripts/local_agent_executor.py:108-116`, `persist_result` L163+; surfaced as `PatchResult.result_commit_sha`/`result_ref` (`executor_protocol.py:186-188`) **[V]** | durable | The attempt has no artifact. `collect()` returns success with a SHA pointing at nothing; the evaluator has nothing to evaluate; the human has nothing to accept. This is the only executor output that is graph-relevant. |
| 2 | NodePacket, transport copy | `attempt_dir/packet.json` (`pi_rpc_adapter.py:182`) **[V]** | durable | The orchestrator loop cannot rebuild the turn prompt after its own restart (`pi_rpc_adapter.py:749-754` fails the attempt as plumbing when this read fails). |
| 3 | NodePacket, source of truth | `jobs` row (`init_db.py:79-108`), re-derived per attempt by `_build_node_packet` (`dispatcher.py:284-335`) **[V]** | durable | No attempt can ever be built. This is the packet-owns-continuity substrate. |
| 4 | Retry fix-list (`previous_findings`) | `jobs.previous_findings` (`init_db.py:105`); written by `allocate_retry_attempt` (`state_recorder.py:267-283`); composed at `return_router.py:340-352` and `reconciler.py:1400-1406`; rendered at `session_prompt.py:99-130` **[V]** | durable | Retries repeat the prior failure. This is the mechanism behind "the packet owns continuity, not the chat ID," and it is already load-bearing. |
| 5 | Attempt counters + per-attempt session rows | `jobs.attempt` / `max_attempts` / `plumbing_attempt` (`init_db.py:100-102,222`); `executor_sessions` (`init_db.py:189-208`); allocation at `state_recorder.py:251-301` (work) and `304-348` (plumbing) **[V]** | durable | Retry budgets become unbounded; the superseded-attempt guard loses the live attempt index. |
| 6 | Context pointers | Built once at dispatch (`dispatcher.py:235-281`), frozen on the packet (`executor_protocol.py:70-75`), rendered as the project zone (`pi_rpc_adapter.py:455-491`) **[V]** | durable | The project zone empties and the model re-excavates GDDP — the exact failure measured in `.handoffs/106:13-22` (29 `read` + 120 `bash` calls against 16 `subagent` dispatches). |
| 7 | Per-attempt event log | `attempt_dir/events.jsonl` (`pi_rpc_adapter.py:812,1314-1319`) **[V]** | durable | Loses `extract_actual_cached_tokens` input (`prompt_topology.py:205-249`), `compute_turn_context_coverage` input (`pi_rpc_adapter.py:557-630`), and the operator stall heuristic (`docs/current/dispatch-checklist.md`: events mtime + live pid). |
| 8 | Context coverage receipt | `attempt_dir/context_coverage.json` (`pi_rpc_adapter.py:932-941`) **[V]** | durable | Research-drift (`outside_pointers`) becomes invisible again. |
| 9 | Prompt cache report | `attempt_dir/prompt_cache_report.json` (`pi_rpc_adapter.py:826-831`), attached to the handoff (`946-950`) **[V]** | durable | No per-turn zone/token evidence in the node's evidence trail. |
| 10 | Terminal attempt state | `attempt_dir/exit.json` + `result.json` (`pi_rpc_adapter.py:951-960`, `_write_exit` L1427-1439); read by `read_pi_rpc_status` (L352-400) and `collect` (L264-316) **[V]** | durable | Nothing can terminalize an attempt; absence is *defined* as plumbing failure ("exited without durable exit state", L398-400). |
| 11 | Worktree → job correlation | append-only jsonl, `record_worktree_correlation` (`local_agent_executor.py:27-52`) **[V]** | durable | Hook/OTLP telemetry can no longer be joined back to a node once the worktree is pruned. |
| 12 | Evaluator verdict receipts | `gddp-config/verification/<project>/` (`docs/proposals/LOOP.md:16-19`) **[V]** | durable | Human review loses its evidence. Outside this repo. |

### 1.2 Not durable, despite the sketch

| # | State | Where it lives | Actual class | What breaks |
|---|---|---|---|---|
| 13 | **Session worktree** | Created once per orchestrator *session* at the first packet's base SHA (`pi_rpc_adapter.py:1099-1105`, `local_agent_executor.py:68-84` — `tempfile.mkdtemp`); removed unconditionally in `finally` (`pi_rpc_adapter.py:1182-1186`) **[V]** | durable *within one orchestrator process*, destroyed at its exit — including the plumbing-death return at L1142-1150 | Uncommitted mid-turn work is deleted on the same path that classifies the turn as a plumbing failure. `allocate_plumbing_retry` then redispatches **cold** (`state_recorder.py:304-348`), so the runtime already accepts this loss. The base it redispatches from is attempt 0's recorded base — enforced only since `jobs.expected_base_commit_sha` was added; before that, `_handle_failed` read current HEAD first (`reconciler.py:1074`), so a retry silently re-based whenever HEAD moved. The sketch row "repository/worktree → durable" must split: object store durable, worktree not. |
| 14 | **Attempt-by-attempt findings history** | `previous_findings` is overwritten, not appended: `previous_findings = COALESCE(?, previous_findings)` on one `jobs` row (`state_recorder.py:275`) **[V]** | latest-only | Attempt 3 cannot see attempt 1's findings. "attempt history → durable" is true for counters and session rows, false for findings text. |
| 15 | **Steer read offset** | `steer.jsonl` is a durable file (`pi_rpc_adapter.py:786-788`), but its byte cursor is an in-memory dict (`pi_rpc_adapter.py:774-776`; `_read_steer_messages` returns `handle.tell()` at L1364) **[V]** | process-scoped | A replacement process re-delivers every operator steer from byte 0. Under a cold-turn transport, where a new process *is* the normal case, this becomes a live defect rather than a corner case. |
| 16 | **Context summary** | Does not exist. Closest surrogates are dispatch-time pointers (#6, static) and post-hoc coverage (#8). A runtime-owned canonical summary is proposed only, at `docs/proposals/stateless-supervisor-cycle.md:349-363` **[GAP]** | not built | Nothing breaks — nothing depends on it. The sketch row "context summary → durable" is aspirational; reclassify as *proposed*. |

### 1.3 Disposable / opportunistic / transport-specific

| # | State | Where it lives | Class | Notes |
|---|---|---|---|---|
| 17 | Pi chat history | `_orchestrators/<project>/pi-session/*.jsonl` via `--session-dir` (`pi_rpc_adapter.py:995-996,1037-1038`); path echoed to `attempt_dir/session_file` (L1126-1127); resumable via `--session` (L1042-1043) **[V]** | disposable | Confirmed disposable *empirically*, not just doctrinally: the lever exists and the runtime has never pulled it (§0). Observed live: 25 session files under `jobs/local-subprocess-spool/_orchestrators/aa-cli-tui-pass/pi-session/`. |
| 18 | Cursor chat store | `~/.cursor/chats/<cwd-hash>/<session_id>/{meta.json,store.db}`. Verified on this host: the four spike session ids resolve under `~/.cursor/chats/bd4dc41d3a979ff8c90937cb89ab71d9/`, and `meta.json` reads `{"schemaVersion":1,…,"cwd":"/private/tmp/cursor-cli-spike"}` **[V]** | disposable, **host-local and cwd-namespaced** | Outside the repo, outside `jobs/` (`AGENTS.md`: `db/`, `jobs/`, `events/` are the excluded runtime dirs — this is not even that). Not visible to `gddp watch`, not transferable between `sab-mini` and `pi-big`. See §2.6. |
| 19 | Pi compaction state | `.pi/settings.json` (`reserveTokens: 163840`, `keepRecentTokens: 12000`); in-place `CompactionEntry`, rebuild from `firstKeptEntryId` (`.handoffs/106:111-113`) **[V]** | opportunistic, model-side | `stateless-supervisor-cycle.md:363` already rules that a model-written summary is untrusted. Not a continuity mechanism GDDP may depend on. |
| 20 | Provider prefix cache (KV) | `usage.cacheRead` etc., parsed by `extract_actual_cached_tokens` (`prompt_topology.py:205-296`) **[V]** | opportunistic | `prompt_topology.py:174-181` explicitly refuses to blend provider-measured cache with GDDP-authored zone structure, because the denominator spans a harness GDDP does not model. That refusal applies verbatim to any resume-vs-cold cache argument (§2.2). |
| 21 | Orchestrator process, inbox, locks | `_orchestrators/<project>/{pid,lock,state,current_attempt,worktree_path,inbox/}` (`pi_rpc_adapter.py:186-244,1119-1170,1387-1424`) **[V]** | transport-specific | Exists only because pi_rpc is one long-lived process per project. A per-turn subprocess transport has no analogue, and `read_pi_rpc_status`'s `dispatched`/`running` distinction (L388-397) collapses with it. |

### 1.4 Verdict on each row of the target boundary sketch

| Sketch row | Verdict |
|---|---|
| repository/worktree → durable | **Split.** Object store + attempt refs: confirmed durable (#1). Worktree: **refuted** — session-scoped and deleted on the plumbing path (#13). |
| NodePacket → durable | **Confirmed**, twice over (#2, #3). |
| attempt history → durable | **Confirmed with amendment** — counters and session rows durable (#5); findings text is latest-only (#14). |
| evaluator verdict → durable | **Confirmed** (#12). |
| tool/event log → durable | **Confirmed with caveat** — durable per attempt (#7), but session-cumulative under pi_rpc, requiring a pre-turn byte offset to be interpretable (`pi_rpc_adapter.py:834-839`). A cold-turn transport removes that caveat: one process, one stream, one turn. |
| context summary → durable | **Refuted as a fact; accept as a proposal** (#16). |
| LLM chat history → disposable | **Confirmed, and stronger than stated** (#17, §0). |
| model KV/cache → opportunistic | **Confirmed** (#20), and §2.2 shows it is not resume-controlled anyway. |
| process → transport-specific | **Confirmed** (#21), with one leak to fix: the steer offset is process-scoped state on a channel that must be durable (#15). |

---

## 2. Interrogating `--resume`

### 2.1 Trigger T1 — native session / tool state

Every event type the spike observed, across all seven turns
(`cursor_cli_spike_results.json`, `event_types` keys): `system/init`, `user`, `assistant`,
`thinking/delta`, `thinking/completed`, `tool_call/started`, `tool_call/completed`, `result/success`. **[V]**

There is no plan, todo, memory, checkpoint, or session-variable event in that vocabulary. The only tool
exercised was `read`, whose entire effect is on the filesystem (`cursor_cli_spike.py:211-219`) — and the
filesystem is the worktree, which is durable state GDDP already owns (#1/#13).

**Verdict: reject.** The only native session state observed is message history, and message history is
disposable by doctrine and by GDDP's own eight-month non-use of the pi resume lever (§0).
Admitting `task_requires_native_session_state` as a trigger today would be exactly the
`AGENTS.md` failure pattern: assume a behavior, design around it, discover it was false.

### 2.2 Trigger T2 — prefix-cache economics

Every usage record in the spike (`cursor_cli_spike_results.json`):

| turn | resumed? | `inputTokens` (fresh) | `cacheReadTokens` | `cacheWriteTokens` | `duration_api_ms` | `wall_s` |
|---|---|---|---|---|---|---|
| `cold_turn` | no | 12,770 | 8,188 | 0 | 5,481 | 9.66 |
| `tool_events` | **no** | **208** | **41,880** | 0 | 9,252 | 13.31 |
| `resume_after_exit` | yes | 112 | 20,956 | 0 | 1,985 | 6.76 |
| `sigkill_mid_turn_resume_check` | yes | 63 | 20,892 | 0 | 1,867 | 6.90 |
| `sigterm_mid_turn_resume_check` | **yes** | **12,767** | **8,188** | 0 | 3,884 | 8.77 |

Two counterexamples, one in each direction, in a five-point sample:

- The **lowest fresh-input turn in the entire spike (208 tokens) was a cold turn**, and it also drew the
  **largest cache read (41,880)** — five times any resume turn. Cold ≠ uncached.
- One of the three resume turns (`sigterm_mid_turn_resume_check`) billed 12,767 fresh input against 8,188
  cache read — byte-for-byte the same profile as `cold_turn`. Resume ≠ cached.

The 8,188 figure appears on both a cold turn and a resume turn; the ~20.9K figure appears on two resume turns
that ran back-to-back. **[A]** That pattern reads as a fixed harness/system prefix plus recency, not as a
session-keyed effect. Nothing in the spike controls for prompt bytes, ordering, or elapsed time, and no
condition was repeated. `n=5, uncontrolled`.

Magnitude, taking the best resume case at face value anyway: 12,770 → 112 fresh input = **12,658 tokens saved,
once per turn**. Against `.handoffs/106:76-80`, one orchestrator session consumed **34,365,343 input tokens
across 205 requests at a 176,894-token median**. 12,658 is **0.037%** of that session. Latency: the best
resume saved ~3.5s of API time, but the third resume turn took 3,884 ms and the cold tool turn took 9,252 ms —
turn cost is dominated by the work, not by re-sending the prompt.

`prompt_topology.py:174-181` already rejects computing a single blended cache number across the GDDP/harness
boundary, on the grounds that "modeling the harness to produce one grand unified percentage would couple GDDP
to pi's internal prompt construction; that coupling is rejected until a concrete need earns it." The same
standard disqualifies this data as a policy basis.

**Verdict: reject as a trigger. Opportunistic at most.** GDDP's actual lever on cache is the one it already
built and controls: byte-stable zone ordering (`prompt_topology.py:1-35`, `session_prompt.py:15-42`,
`dispatcher.py:241-247`). Cold turns keep that lever intact — the stable prefix is stable *because it is
rebuilt identically*, not because a session is held open.

### 2.3 Trigger T3 — mid-task conversational continuity (operator steering)

This is the only candidate with substance, and it is a transport gap, not a resume argument.

Today `gddp steer` is a mid-turn RPC injection into a live process: operator appends to `steer.jsonl`, the
orchestrator's reader thread drains it as `{"type":"steer"}` during the running turn
(`pi_rpc_adapter.py:766-806`; `docs/proposals/LOOP.md:26-29`; a bare `prompt` mid-turn is rejected by pi,
L781-784). A per-turn subprocess has no such channel. And the spike shows the cost of the alternative:
SIGTERM took 1.16s to kill, exited 143, and produced **no result event** — the turn's output was lost
(`cursor_cli_spike_results.json` `sigterm_mid_turn`: `result_event: null`, 41 lines of partial assistant text). **[V]**

So `cursor_cli` steering must become cancel-then-recompose: kill the turn, and issue the next turn carrying
the operator's message. The question is whether the next turn needs the model's own prior reasoning.

**Verdict: covered by packet + spool, conditionally.** The next turn needs (a) the operator's message and
(b) enough of the prior turn to make that message legible. Both are already durable or trivially made so:
`steer.jsonl` is a file, and the prior turn's assistant text and tool paths are in `events.jsonl` (#7). What
is missing is that the adapter must render them into the **attempt zone** — the volatile zone that already
carries `previous_findings` (`session_prompt.py:31-37`) — as a per-attempt turn ledger. That is the same
"packet owns continuity" mechanism applied one level down, from attempt to turn. Resume is the lazy
alternative to writing that ledger, not a capability the ledger cannot supply.

Retained only as the **`operator_requested`** trigger: when a human explicitly asks to continue a
conversation, the human — who owns graph truth — has decided the chat is worth keeping. No inference needed.

### 2.4 Trigger T4 — multi-turn within one attempt

Not applicable yet. `local_subprocess` is one process per attempt (`local_subprocess_adapter.py:51-96`);
`pi_rpc` runs one turn per packet (`pi_rpc_adapter.py:1129-1139`, `attempt_dirs=[attempt_dir]`). If
`cursor_cli_adapter` runs more than one turn per attempt, "between turns" becomes a real interval and the
question reopens — as a *measurable redo cost*, not a presumption. **Verdict: defer.** Evidence bar in §3.3.

### 2.5 Trigger T5 — crash / plumbing recovery

`allocate_plumbing_retry` (`state_recorder.py:304-348`) already handles a session that died before durable
exit state: it keeps the attempt index, draws on a separate budget so infra noise never consumes the work-
attempt budget, and redispatches **cold**. Meanwhile the worktree its partial work lived in was deleted on the
same path (#13, `pi_rpc_adapter.py:1182-1186`).

**Verdict: reject, and note it is worse than neutral.** Resuming a chat whose corresponding filesystem work no
longer exists hands the model a transcript of edits it can no longer see — actively misleading. The correct
fix for crash recovery is worktree lifecycle (§4.1), not chat lifecycle.

### 2.6 Constraint that binds all triggers — resume is not portable

- The store is **cwd-namespaced**: `~/.cursor/chats/<cwd-hash>/<session_id>/`, with `meta.json` recording
  `"cwd":"/private/tmp/cursor-cli-spike"`. **[V]**
- The spike ran **every turn from one fixed cwd** (`cursor_cli_spike.py:124,151`: `cwd=str(SCRATCH)`), so
  **cross-cwd resume is unproven**. **[V]**
- GDDP local transports execute in a `tempfile.mkdtemp` git worktree — a **different absolute path every
  time** (`local_agent_executor.py:68-84`). **[V]** So resume across attempts would cross exactly the
  boundary the spike never tested.
- The store is under `$HOME`, host-local. `AGENTS.md` names multiple armed control planes (`sab-mini`,
  `pi-big`); a resumable session cannot migrate between them. **[V]**
- The spike's own `open_risks` names "resume durability across hours/days not provable in one session." **[V]**

**Consequence:** even where resume is wanted, it must be a *hint*. A missing or unusable session id must fall
back to a cold turn silently, never fail the attempt.

---

## 3. `session_policy`

### 3.1 Schema

Configured in `gddp-config/graphs/<project>/project.yaml` under the existing `execution_policy` block —
the surface that already carries `retry_budget`, `frontier_auto_advance`, `max_concurrent_jobs`,
`default_executor` (`graph_reader.py:78-101`; `runner.py:117-124,170`; `frontier.py:63,296`;
`reconciler.py:1346-1355`).

```yaml
execution_policy:
  session_policy:
    default: cold                  # cold | resume. Runtime default is cold; `resume` is
                                   # not accepted as a project default at v1.
    resume_when: []                # allowed values: [operator_requested]
    resume_scope: attempt          # attempt | never. Resume never crosses attempt_index.
    require_same_cwd: true         # refuse resume if the turn's cwd != the session's recorded cwd
    require_same_host: true        # refuse resume if hostname != the session's recorded host
```

Runtime default when the key is absent: `{default: cold, resume_when: [], resume_scope: attempt,
require_same_cwd: true, require_same_host: true}`. Validation follows `parse_execution_policy`'s existing
shape: raise on an unknown `resume_when` member, so a typo is a configuration error at preflight
(`dispatcher.py:57-75`) rather than a silent cold turn nobody notices.

### 3.2 Where each layer is configured, and where it is not

| Layer | Surface | Rationale |
|---|---|---|
| Project default | `project.yaml → execution_policy.session_policy` | Human-authored config in `gddp-config`, alongside every other execution policy. |
| Node override | node yaml `execution_policy.session_policy` (same schema, shallow-merged over the project's) | A node is the unit of intent; if a node genuinely needs native session state, that is a property of the node, and a human writes it. |
| Packet | Resolved policy frozen onto the `NodePacket` at dispatch, exactly like `context_pointers` (`dispatcher.py:275-281`, `executor_protocol.py:70-75`) | Guarantees a retry renders the identical decision and the identical prompt bytes. A packet that resolved to `cold` stays `cold` on retry. |
| Attempt / operator | `attempt_dir/resume.requested` holding the prior `session_id`, mirroring the existing `cancel.requested` marker convention (`pi_rpc_adapter.py:325-336,741-746`) | The one runtime-mutable input, and it is human-originated. Same file-marker idiom already in the spool. |
| **Env** | **Deliberately excluded** | `GDDP_EXECUTOR_OVERRIDE` (`dispatcher.py:66-68,107-109`) exists so an operator can reroute *transport* without touching human-owned graph truth. Resume is not transport routing — it changes what the model is told and what it remembers, which sits next to node intent. A shell export on one host is the wrong authority for that, and it would silently differ between `sab-mini` and `pi-big`. |

### 3.3 What evidence would justify a new trigger

Each stated as a falsifiable measurement, because the standing failure mode is adopting a mechanism on the
strength of a plausible story.

| Candidate trigger | Evidence required |
|---|---|
| `task_requires_native_session_state` | A `stream-json` event type outside the eight observed in §2.1 carrying state the runtime cannot reconstruct from worktree + packet. Decisive test: an identical turn N+1, same worktree, same prompt bytes — **fails cold, succeeds resumed**, reproduced ≥3 times. |
| `multi_turn_redo` | Only once an adapter runs >1 turn per attempt (§2.4). ≥20 paired turns on real nodes, measuring duplicated `tool_call` `args.path` values and fresh `inputTokens`, cold vs resumed. Justified only if cold wastes >15% of turn wall time re-reading paths the prior turn already read **and** a per-attempt turn ledger in the attempt zone (§2.3) fails to close the gap. |
| `cache_economics` | A controlled A/B: ≥30 paired turns, identical prompt bytes, identical cwd, same hour, reporting per-turn `usage.inputTokens` and `usage.cacheRead`. Justified only if resume reduces billed fresh input by a margin that is material against per-node totals — baseline for "material" is `.handoffs/106:76-80` (8.9M–34.4M input tokens per session). The present n=5 sample does not qualify and contains a counterexample in each direction. |
| `steer_continuity` | ≥10 real operator steers where cold reconstruction (prior turn result + steer text rendered into the attempt zone) produced a wrong follow-up that a resumed session got right. Fewer than that is anecdote. |
| `resume_portability` (precondition on all of the above) | Cross-cwd resume proven: a session started in worktree A resumed from worktree B. Plus a retention probe at +1h/+24h/+7d. Until this passes, no trigger may make resume required — only preferred, with cold fallback. |

---

## 4. Consequences for `cursor_cli_adapter.py`

1. **Worktree lifecycle is the real durability work, not chat.** #13 and §2.5: today the worktree is deleted
   on the plumbing path while the plumbing retry redispatches cold from the base SHA. A per-turn transport
   makes this a per-turn decision. Removal should be conditional on a persisted result, matching the existing
   contract where `persist_result` failure *keeps* the worktree (`PatchResult.worktree_path`,
   `executor_protocol.py:189`; `pi_rpc_adapter.py:302-315`).
2. **Make the steer offset durable** (#15). A cold-turn transport turns this from a corner case into the
   normal path.
3. **The attempt zone is where turn-to-turn continuity belongs** (§2.3), next to `previous_findings`
   (`session_prompt.py:31-37`) — never in the stable zones, which must stay byte-identical.
4. **Persist the session id even when policy is `cold`.** Recording `session_id` from the `system/init` event
   (`cursor_cli_spike.py:93-95`) into the attempt dir costs nothing, gives the operator a handle for
   `operator_requested`, and is the only way the §3.3 experiments ever become runnable.
5. **Keep the four-zone prompt and the per-turn cache report.** Cold turns do not weaken prefix caching
   (§2.2); byte-stable zones are what preserve it, and they are already built.

---

## 5. Bottom line

Only one thing survives an executor turn that GDDP cannot rebuild: the git object store and its per-attempt
refs. Everything else the runtime depends on is either re-derived from the `jobs` row at dispatch or written
as a file in the spool. Chat history is the one surviving item nothing reads — pi_rpc has had `--session`
wired end to end since it was written and the runtime has never set it, while the production heartbeat runs
`pi --print --no-session`.

`--resume` therefore does not earn a policy trigger on native state (none observed), on cache economics (the
spike's cheapest turn was cold and one resume turn was indistinguishable from cold; the best case is 0.037% of
a measured session's input), or on crash recovery (already handled cold, and the corresponding filesystem work
is deleted anyway). It earns exactly one: an operator explicitly asking for it. Cold is the default because it
is what the runtime already does, not because it is the austere choice.
