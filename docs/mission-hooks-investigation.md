# Factory Droid Mission Mode — External Surface Investigation (Evidence-Only)

**Scope:** What can an EXTERNAL process do with a running Factory "mission"? Read-only
investigation of local artifacts, the installed binary, official docs, and Factory's
public SDK repos. No missions launched; no mission files modified.

**Evidence tiers used (in order of authority):**
1. `~/.factory/missions/` — 3 real on-disk missions; `3efe69ab-…` is the richest.
2. `droid` binary help — **installed version is `0.189.0`** (task brief said 0.179.0;
   this report reflects the 0.189 surface actually installed).
3. `docs.factory.ai` — fetched `llms.txt` + the 7 relevant pages.
4. Public SDKs cloned read-only to `/tmp`: `Factory-AI/droid-sdk-typescript`
   (`/tmp/ds-ts`) and `droid-sdk-python` (`/tmp/ds-py`).

---

## TL;DR — answers at a glance

| # | Question | Verdict | Confidence |
|---|----------|---------|------------|
| 1 | Submit new work to a running mission | **Partial** — natural-language message to orchestrator only; no structured per-feature API | Med-high |
| 2 | Read per-feature status without TTY | **Yes** — files (pull) + daemon mission notifications (push) | High (files) / Med-high (push) |
| 3 | Cancel one feature without ending mission | **Yes** — `kill_worker_session` per workerSessionId | High |
| 4 | Identity surviving restart | **Both** — dir=session UUID (resume key); `missionId`=mis_* (logical id) | High |
| 5 | Terminal/hashable artifacts | **Yes** — handoffs/*.json, worker-transcripts.jsonl, progress_log.jsonl, validation synthesis | High |
| 6 | Commit↔feature mapping | **Yes (mapping) / Partial (base)** — commitId+featureId explicit; base=git parent or packet SHA | High / Med |
| 7 | Crash/replay + dedup | **Yes** — resume reuses workerSessionId; new id = retry | High |
| 8 | Mission-wide vs per-worker + sequential | **Yes** — clear split; sequential admission only orchestrator-mediated | High |

**Bottom-line verdict: (c) not exposed.** Structured per-node external assignment
admission has no API. Build **one mission-level lease + post-hoc evidence slicing**
on the stable per-feature artifacts, keyed by `(featureId, workerSessionId, commitId)`.

---

## The protocol surface (decisive evidence)

From the SDK enums (`/tmp/ds-py/src/droid_sdk/schemas/enums.py`) and the TS reference
(`/tmp/ds-ts/docs/typescript-sdk-reference.md`):

**Client→server methods (`DroidServerMethod`):**
`initialize_session, load_session, add_user_message, interrupt_session,
kill_worker_session, update_session_settings, … close_session, compact_session,
fork_session, rename_session, get_context_stats/breakdown, get/execute_rewind`.
There is **no** `add_feature`, `submit_assignment`, `enqueue_work`, `admit_node`.

**`missions` SDK namespace (unstable) — ONLY two methods:**
`inspectReadiness`, `acknowledgeReadinessWarning` (TS ref, "unstable" table).
> "Keep unstable API use behind an application-owned adapter."

**Server→client notifications (`SessionNotificationType`) — mission events:**
`mission_state_changed, mission_features_changed, mission_progress_entry,
mission_heartbeat, mission_worker_started, mission_worker_completed`.

**`ToolConfirmationType` (permission prompts the server raises):**
includes `ProposeMission` and `StartMissionRun` — i.e. creating a mission and
starting a run are interactive permission gates, not programmatic submissions.

**REST Sessions API** (`docs.factory.ai/api-reference/sessions.md`):
`GET/POST /sessions`, `GET/PATCH/DELETE /sessions/{id}`,
`POST /sessions/{id}/interrupt`, `GET /sessions/{id}/messages`,
`POST /sessions/{id}/messages` ("enabled for selected organizations only").
No per-worker kill, no feature append, no `/missions/{id}/features`.

**Daemon transport:** websocket (default), IPC, or unix socket.
`droid daemon --listen {websocket,ipc}`; example connects `ws://127.0.0.1:37643`
with API-key auth. External callers use `connectToDaemon({url, auth:{apiKey}})`.

---

## Q1 — Submission: new work to an ALREADY-RUNNING mission → **Partial** (med-high)

There is **no structured per-feature/per-node admission API.** The only ways to feed
new work into a running mission:

1. **Natural-language message to the orchestrator session.** The orchestrator is an
   agent; you talk to it and it updates the plan itself.
   - REST: `POST /api/v0/sessions/{orchestratorId}/messages` (org-gated).
   - JSON-RPC: `droid.add_user_message` (local daemon, not org-gated).
   - SDK: `droid.sessions.resume(id)` + `session.stream(prompt)`.
   - Docs: *"the orchestrator is an agent, and you can talk to it … You need to
     change direction mid-mission → Pause and explain … The orchestrator can update
     the plan, re-scope milestones, and continue."*
     (`missions/overview.md` troubleshooting; `missions/running-cli.md`).
2. **CLI resume (continues the conversation, does not attach to a live TUI):**
   `droid exec -s <orchestratorSessionId> "<new work>"` — `exec` is single-shot
   non-interactive; it reloads the session the daemon owns (`cli-reference.md` L91,117).
3. **No filesystem inbox.** `features.json` is the orchestrator's own mutable state.
   Writing it externally is unsupported and races the orchestrator (proven: the
   orchestrator rewrites features.json itself — a `mission_run_started` log entry says
   *"Updated features.json: the wrapper feature is now …"*).

**What you CANNOT do:** append a structured feature/assignment that the mission
treats as a first-class work item with its own lease/gate. Any "new feature" is the
orchestrator's interpretation of your prose. → feeds the bottom-line verdict.

Evidence: `/tmp/ds-py/src/droid_sdk/client.py` (no admission method);
`/tmp/ds-ts/docs/typescript-sdk-reference.md` (sessions + unstable missions tables);
`~/.factory/missions/3efe69ab-…/progress_log.jsonl` (orchestrator-authored features.json edit).

---

## Q2 — Status: per-feature status without attaching to TTY → **Yes** (high)

**Pull — read structured files (high confidence, verified):**
- `features.json` — per feature: `status` (pending/in_progress/completed/cancelled),
  `workerSessionIds[]`, `currentWorkerSessionId`, `completedWorkerSessionId`, `milestone`.
- `progress_log.jsonl` — per-worker events: `worker_selected_feature`,
  `worker_started` (spawnId `worker_*`), `worker_completed` (successState,
  validatorsPassed, commitId, featureId), `worker_paused`, `mission_resumed`.
- `validation-state.json` — per-assertion (VAL-*) status: passed/failed/pending +
  `validatedAtMilestone`.
- `handoffs/*.json` — per-worker terminal completion record (see Q5).

**Push — daemon notifications (med-high; documented, not observed live):**
`SessionNotificationType` enumerates `mission_state_changed`,
`mission_features_changed`, `mission_progress_entry`, `mission_heartbeat`,
`mission_worker_started`, `mission_worker_completed`. An external process on the
daemon websocket receives these as it streams (TS ref: notification stream carries
"working-state changes, MCP status, and **mission events**").

**REST:** `GET /api/v0/sessions/{id}` + `/messages` give session-level state.

No TTY attachment required for any of the above. Evidence: `enums.py`
(SessionNotificationType); `features.json`, `progress_log.jsonl`, `validation-state.json`.

---

## Q3 — Cancellation: one feature without ending the mission → **Yes** (high)

- **`droid.kill_worker_session`** (`/tmp/ds-py/src/droid_sdk/client.py:534`) /
  **`sessions.killWorker`** (TS ref L866): sends `droid.kill_worker_session` with
  `{workerSessionId}` — kills ONE worker (one feature's in-flight work); the
  orchestrator mission continues.
- **`FeatureStatus.Cancelled`** exists in the enum — a feature can be marked cancelled.
- Docs (natural-language path): *"A worker is taking too long → Pause the orchestrator
  and tell it to mark the current item as complete and move on."*

**Caveat:** killWorker is **daemon-JSON-RPC only.** The REST Sessions API exposes only
whole-session `/interrupt` — no per-worker REST cancel. Evidence: `client.py:534-556`;
`api-reference_sessions.md` (no kill endpoint).

---

## Q4 — Identity: what survives restart as canonical → **Both, distinct roles** (high)

Verified across all 3 on-disk missions:

| Mission dir (session UUID) | `state.json` missionId | state |
|---|---|---|
| `3efe69ab-0dc5-4a45-bbca-cc815844a679` | `mis_b0cadc77` | paused |
| `15c7545f-cb1f-4cb6-aaef-3ff35bff3b8e` | `mis_52a8e0c1` | planning |
| `fc63ee55-20ad-4e92-8487-131ea1af0ab8` | `mis_bdc0ff3d` | planning |

- **Dir name = orchestrator SESSION UUID** — the filesystem key AND the resume/transport
  key: `droid --resume [sessionId]` / `droid exec -s <id>` (`cli-reference.md` L86,91).
- **`missionId` = `mis_*`** — the LOGICAL mission identity, passed to workers as
  `decomp_mission_id` (SDK `initialize_session`: *"Mission ID for worker sessions"*;
  `DecompSessionType` = orchestrator | worker). Present even at planning stage.

**Canonical answer:** the **session UUID (dir name)** is the resume/attach key an
external caller uses; **`mis_*`** is the logical identity that binds orchestrator +
workers. Both survive restart; they are not interchangeable.

Evidence: `~/.factory/missions/*/state.json` (all three); `client.py` initialize_session
docstring; `cli-reference.md`.

---

## Q5 — Terminal artifacts safe to hash, + the triggering event → **Yes** (high)

**Terminal / immutable (safe to hash):**
- **`handoffs/*.json`** — written ONCE at `worker_completed`, never modified. Proof:
  each file's mtime **exactly equals** its filename UTC timestamp
  (`…05-56-17-607Z…` → mtime `22:56:17 PDT` = `05:56:17Z`; 7 files = 7 completions).
  Fixed schema: `{timestamp, workerSessionId, featureId, milestone, successState,
  returnToOrchestrator, handoff{salientSummary, whatWasImplemented, whatWasLeftUndone,
  verification, tests, discoveredIssues, skillFeedback}}`.
- **`worker-transcripts.jsonl`** — append-only, one object per worker (7 = 7 workers),
  monotonic timestamps (`05:56:17Z → 07:20:42Z`). Each object: the worker's full
  feature skeleton/prompt + tool-call transcript.
- **`progress_log.jsonl`** — append-only event log; entries immutable once written.
- **`validation/<milestone>/…/{synthesis.json, scrutiny/reviews/*.json,
  user-testing/flows/*.json}`** + **`evidence/…`** — written at milestone validation
  (`milestone_validation_triggered` event). Terminal once the milestone validates.
- **Stable inputs** (set at planning/acceptance, not run-generated): `mission.md`,
  `architecture.md`, `AGENTS.md`, `services.yaml`, `validation-contract.md`, `init.sh`,
  `model-settings.json`, `runtime-custom-models.json`, `working_directory.txt`,
  `library/`, `skills/`.

**Mutable — NOT safe to hash mid-run:** `state.json` (state/updatedAt/
lastReviewedHandoffCount), `features.json` (per-feature status + workerSessionIds
mutate), `validation-state.json` (assertion statuses flip pending→passed/failed).

**The event that makes a file safe:** `worker_completed` (ProgressLogEntryType) writes
the handoff JSON and finalizes the transcript entry; `milestone_validation_triggered`
finalizes the validation/ synthesis + evidence files.

Evidence: `ls -la handoffs/` (mtime == filename ts); `progress_log.jsonl` event-type
counts; `enums.py` ProgressLogEntryType; `find . -type f` tree.

---

## Q6 — Commit/feature mapping + base→result boundary → **Yes (mapping) / Partial (base)**

**Mapping is explicit and verified in git.** `progress_log.jsonl` `worker_completed`
events carry `{featureId, workerSessionId, commitId, repoPath, successState,
validatorsPassed}`. The matching `handoffs/*.json` repeats featureId+workerSessionId.
Both commitIds resolve in `~/repos/gddp-runtime`:

| featureId | commitId | parent | git subject |
|---|---|---|---|
| archive-surviving-evidence | `31f549d8…` | `2072d33b…` | "docs: archive surviving canary evidence for Node 2…" |
| simplify-executor-to-worktree-only | `35b41a1f…` | `3092206d…` | "fix(executor): reduce local wrapper to worktree transport" |

Author = the user (workers commit via the user's git identity); commits land sequentially
on `main`.

**Base→result boundary per feature:**
- **Result tip** = `commitId` (in the event). **Base** = the commit's git parent (`%P`).
  For sequentially-committed features the boundary is (parent → commit) — fully
  reconstructible from git history.
- The mission's *declared* base is `expected_base_commit_sha`, used by the wrapper to
  `git worktree add --detach` (architecture.md + mission.md Feature 2). That SHA lives
  in the **gddp-runtime NodePacket**, NOT in the mission dir. So the exact declared
  worktree base is reconstructible from the repo/packet, not from mission artifacts alone.

**Partial:** mapping = high; precise declared base = med (git parent suffices for
sequential features; packet SHA needed for the worktree-pinned definition).

Evidence: `progress_log.jsonl` (worker_completed w/ commitId); `git log -1` on both
SHAs; `architecture.md` (worktree-at-expected_base_commit_sha).

---

## Q7 — Crash/replay: resume shape + dedup rule → **Yes** (high)

Observed resume pattern in the richest mission (`worker_paused`/`mission_paused` →
`mission_resumed`):

```
06:31:20  worker_paused   f8e4934b  (simplify-executor-to-worktree-only)
06:31:20  mission_paused
06:33:41  mission_resumed  resumeWorkerSessionId = f8e4934b   ← SAME id
06:33:57  worker_paused    f8e4934b
06:33:57  mission_paused
06:34:16  mission_resumed  resumeWorkerSessionId = f8e4934b   ← SAME id
```

**Pause/resume REUSES the workerSessionId — it is a continuation, not a new attempt.**

By contrast, a genuine RETRY (feature failed, orchestrator re-runs it) spawns a NEW
workerSessionId: `archive-surviving-evidence` ran as `498a1331` (failure) then
`ac4d6392` (success) — two distinct session ids, both linked by the same `featureId`.

**Resume mechanics:** the daemon owns the session. After a process kill,
`droid --resume <orchestratorSessionId>` (interactive) or `droid exec -s <id>` (headless)
reloads the orchestrator; it re-reads its own `features.json`/`state.json`/handoffs and
continues. `mission_run_started` fires each run (8× here). `state.json.lastReviewedHandoffCount`
tracks how far the orchestrator has consumed `handoffs/`.

**External-watcher dedup rule:** key on `(featureId, workerSessionId)`.
- Same workerSessionId after a resume ⇒ **continuation** — do not recount.
- New workerSessionId for an already-seen featureId ⇒ **genuine retry** — count
  separately, link via featureId.
- `worker_completed` with `successState` is the terminal signal; re-reading it post-resume
  yields the same record. `commitId` is idempotent evidence (same commit ⇒ same work).

Evidence: `progress_log.jsonl` (resume/retry events); `state.json.lastReviewedHandoffCount`.

---

## Q8 — Isolation: mission-wide vs per-worker + sequential external assignments → **Yes** (high)

**Mission-wide (shared, orchestrator-owned):** `state.json`, `mission.md`,
`architecture.md`, `AGENTS.md`, `services.yaml`, `validation-contract.md`,
`model-settings.json`, `runtime-custom-models.json`, `working_directory.txt`, `init.sh`,
`features.json` (the plan), `progress_log.jsonl` (global stream),
`worker-transcripts.jsonl` (global, one entry/worker), `validation-state.json`,
`library/`, `skills/`, `handoffs/` (dir), `evidence/`, `validation/`.

**Per-worker:** a `workerSessionId` (UUID) + `spawnId` (`worker_*`); its own
`handoffs/<ts>__<feature>__<workerSessionId>.json`; its own entry in
`worker-transcripts.jsonl`; its own **git worktree** (repo-level isolation — workers
never touch the live tree; the wrapper pins the worktree to `expected_base_commit_sha`).
The worker skeleton shows each worker receives **only its assigned feature JSON + skills**,
not sibling features — strong per-feature context isolation.

**Sequential external assignments:** feasible, but only orchestrator-mediated (Q1). The
orchestrator processes its features (here: 3 pending — dispatch-job-state-consistency,
verify-and-preserve-evidence, user-testing-validator-…) within its own plan. To run "one
GDDP node at a time," GDDP would approve a mission with one feature, let it complete,
then message the orchestrator to add the next (or spawn a fresh mission per node). There
is **no** structured "admit one node, block, admit next" API.

Evidence: `worker-transcripts.jsonl` (skeleton = single feature only); `architecture.md`
(worktree isolation); `features.json` (mission-wide feature list).

---

## Bottom-line verdict: **(c) not exposed** for structured per-node admission

Per-node external assignment admission as a structured, lease-based API **does not
exist.** The `missions` namespace exposes only readiness inspection; `sessions` exposes
message/interrupt/killWorker but no feature-append. New work enters only as
natural-language prose that the orchestrator interprets into features.

**Recommended authority model for GDDP:** do NOT try to build per-node admission leases
against the droid mission surface — there is no hook to lease. Instead:

> **One mission-level lease authorizing the whole graph (or one mission per node), with
> post-hoc evidence slicing** from droid's stable, hashable per-feature artifacts.

GDDP admits nodes to **its own** graph; droid executes; GDDP slices droid's terminal
artifacts back onto its nodes as evidence, keyed by **`(featureId, workerSessionId, commitId)`**:
- `handoffs/*.json` → per-feature completion receipt (immutable, hashable).
- `progress_log.jsonl` `worker_completed` → feature↔commit↔successState mapping.
- `validation/…/synthesis.json` → milestone validation evidence.
- Dedup across resume/retry via workerSessionId (same = continue; new = retry).

---

## Unknowns / caveats

- **Version drift:** installed binary is `0.189.0`, not the `0.179.0` stated in the brief.
  All findings reflect the 0.189 surface.
- **killWorker transport:** daemon-JSON-RPC only; NOT in the REST Sessions API (REST has
  only whole-session `/interrupt`). Unknown whether a REST per-worker cancel ships later.
- **REST message admission is org-gated:** `POST /sessions/{id}/messages` is "enabled for
  selected organizations only." The local-daemon JSON-RPC `add_user_message` path is not
  org-gated and is the reliable local admission route.
- **Push-status unobserved live:** mission notifications are documented in the SDK enums
  + TS reference, but no mission was launched here, so live streaming was not witnessed.
- **Per-feature declared base SHA:** lives in the gddp-runtime NodePacket, not the mission
  dir. Git parent suffices for sequentially-committed features; the worktree-pinned
  `expected_base_commit_sha` must be read from the packet for the exact definition.
- **No external submission was performed and no file was modified** — fully read-only.

