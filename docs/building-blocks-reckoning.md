# Building blocks — reckoning for the operator

Audit only. No preferred architecture. No mold pass.

This is written so **you** can see the pieces, see the glue that got poured on them, and picture two or three different machines you could build from the same parts. It is not an inventory dump.

---

## 1. What GDDP is for (one breath)

You write a **graph of intent** (nodes, deps, criteria). Something **dispatches** bounded work to a **replaceable executor**. When work **returns**, an **evaluator** judges whether that change still matches the project’s meaning — not “did tests go green,” but “does this preserve intent and graph integrity?” **You** decide when a node is actually done (`complete`). Executors and their queues are disposable; the graph is not.

Everything else in the repo is either a real piece of that sentence, or scaffolding that grew because agents keep adding layers.

---

## 2. The fracture that explains almost everything

Two questions got fused into one status bit:

| Question | Who should answer it | What it controls |
|----------|----------------------|------------------|
| May the **next agent** start? | Scheduler / evidence | Execution sequencing |
| Is this node **done** for the project? | **You** | Graph truth |

Day-one intent (rebuild doc, provisional design): if work is good enough and you’re asleep, the next node should open. Dependencies **sequence agents**; they do not force operator downtime.

What got built for months: only `complete` unblocked dependents, and only you write `complete`. So every edge became a human wait. Agents then **wrote that freeze down as doctrine** (“no automatic advancement”) and defended it. Distortion with a name outlives a bug.

**Provisional** (2026-07-30) is the first clean split: evaluator pass can mark `provisional` so dependents may move; `complete` stays yours. Smoke run 1 green (`d59c172`) shows the *flow* can work once work actually returns and gets judged.

Hold that split in your head while reading the pieces. A lot of dogma is just people forgetting the split.

---

## 3. The building blocks (extracted, not assembled)

Read these as **parts in a bin**. Current code wires them one way. That wiring is not sacred.

### A. Project meaning (the graph)

**Node YAML + project index + a reader.**  
Human-authored intent, criteria, dependencies, status. Runtime only *loads* them (`graph_reader`).

- **Why it exists:** Agent chat is not project continuity. The DAG is.
- **Assumption still true?** Yes. Without this, you have a harness, not GDDP.
- **Mechanism vs policy:** The files are policy (your words). The reader is mechanism.
- **Dogma to watch:** Treating the graph as something the runtime should silently rewrite. Return-router / graph-updater history pushed “machines advance truth”; later doctrine pushed back to human `complete`.

### B. “What counts as a satisfied dependency?”

Not a module — a **policy set**: which statuses mean “this edge no longer blocks.”

Today that set is meant to be `{complete, provisional}`, but it lives in **several places** that can drift:

- live admission: `scope_checker`
- operator view: `gddp-config` `frontier.py`
- evaluator integrity checks: `decision_engine`
- **still complete-only:** decision-loop `dispatch_next` (old Jules-issue path)

- **Why it exists:** Multi-node work needs a shared notion of “upstream is far enough along.”
- **Assumption still true?** You need *a* shared notion. You do **not** need four copies.
- **Mechanism vs policy:** Pure policy, copy-pasted as constants.
- **Dogma:** “Only human-complete may unlock anything” — that was the fused-question freeze, not the original goal.

### C. Admission: “may this node start a job *now*?”

`scope_checker`: no conflicting active job, deps satisfied under B.

- **Why:** Prevents double-dispatch and building on unready upstream.
- **Still true for graph work?** Yes. For a one-node canary, it’s often heavier than you need.
- **Not the same as** frontier (B’s cousin: a *view* of ready/blocked/moving). Frontier helps you see; admission is the gate.

### D. Durable attempt memory (the queue DB)

SQLite: events, jobs, sessions, results (`init_db`, `state_recorder`, `results_store`).

- **Why:** An attempt needs an ID that survives Jules, local pi, crashes, and your next SSH session.
- **Still true?** Yes for anything unattended or multi-executor.
- **Mechanism.** Policy is what you *do* with rows, not the tables themselves.

### E. Ways work *enters* the system (ingress — separable)

| Piece | What it does | Born for | Still the default truth? |
|-------|----------------|----------|---------------------------|
| **Webhook intake** | GitHub HMAC → `events` row; `project_id` left null | Mar 2026 Jules/GitHub world | No — only one door among several |
| **Classifier** | Event tags → ready node + executor pick | “Work arrives as GitHub noise” | Only if you stay event-driven |
| **Executor preselection on event** | Operator override of default mode | Canary / intent | Useful when used; underused vs defaults |
| **Direct “run this node”** (CLI / override / local argv) | Skip the social graph of GitHub | How you actually work now | Yes for real velocity — but under-modeled as *first-class* ingress |

Dogma: **webhook = the front door.** That assumption died when Jules got API/CLI and local_subprocess got commit-ref returns. Code still has the door; belief shouldn’t require every trip to walk through it.

### F. The executor stack (four different things people say “executor” for)

Separate them or you cannot recombine:

1. **Packet** — frozen description of one attempt (goal, criteria, base SHA, …). Contract so any worker sees the same job.
2. **Protocol** — `dispatch / status / collect / cancel`. Assumes “async session,” which fits cloud agents and local long jobs; a pure one-shot script can feel shoehorned.
3. **Transport** — how the bits move:
   - **Jules Action** (issue + GitHub ceremony) — day-one; assumption “Jules needs remote PR theater” is **stale** once CLI/API exist.
   - **Jules CLI / API** — direct cloud agent.
   - **local_subprocess** — worktree + `result_commit_sha`; this is the path that matched live N2 / provisional smoke.
4. **Dispatch policy** — *who* gets chosen: `allowed_execution_modes` (default `["jules"]`), first mode wins, `GDDP_EXECUTOR_OVERRIDE` as escape hatch. **Policy**, not physics. Default Jules is the bar that excludes how you work unless you override or edit YAML.

Neutral executor **contract** (1–2) serves doctrine.  
Neutral executor **practice** dies at (4) and at keeping (3a Action) as the mental default.

### G. Base commit bind + base-chaining

At plan time the attempt records **what SHA it was built on**. When a dep is only `provisional`, its work is on an attempt ref, not HEAD — so dependents **chain** to that result SHA (`_chained_base`, `a5e0eb9`). Multiple provisional deps → refuse (no merge machinery).

- **Why:** Without this, provisional unblocks the *status* but the next agent builds on a tree missing upstream work.
- **Still true under provisional?** Yes.
- **Dogma failure mode:** using base mismatch to **throw away returned work before the evaluator speaks**. Overnight run taught that; rebuild rule is explicit: **never block evaluation to protect merge purity.** Base is evidence / merge admission, not a silencer.

### H. The heartbeat is not one block

People say “heartbeat.” Inside it:

| Slice | Job |
|-------|-----|
| **Tick / runner** | Order of operations for one process wake-up |
| **Collect** | Poll adapter, take patch or commit-ref, durable result SHA |
| **Eval trigger** | *When* verify runs — today both reconciler *and* return_router call the bridge |
| **Eval engine** | Deterministic + semantic + integrity → receipt (**the product**) |
| **Bridge** | Subprocess CLI so a hung model doesn’t kill the loop |
| **Post-eval routing** | Always `awaiting_review` (you still own complete) |
| **Provisional writer** | Optional graph-adjacent status if verdict qualifies; never writes `complete` |
| **human_gate** | Per-node opt-out of provisional |

**Assumption that aged:** “reconciler reconciles.” It mostly **polls, collects, and kicks eval**. Naming lies.

**Dual eval entry** (PR return vs session collect) is the same *engine* with two *doorbells*. Fine if identical; dangerous if they drift.

### I. Return router (merged PR)

Mar 14, 2026: built to auto-advance graph on PR merge; later de-fanged to receipt + review.

- **Why then:** Executor return *was* “PR landed.”
- **Still required?** Only for Action/PR-shaped transports. Local commit-ref never needs it for the happy path.
- **Survives as:** optional side door, not the spine.

### J. Dead / parallel control plane

**Decision-loop** powers (`dispatch_next` opens GitHub issues for Jules, complete-only deps) are still in tree. **Heartbeat does not import them** as the live brain. Two control planes is how you get “two CLI surfaces disagree on dispatchable.”

Treat decision-loop as **parts on the shelf** (maybe keep “propose complete PR”), not as a second factory floor.

### K. You

CLIs / `jobs_status` / reading receipts. And the only authority that writes **`complete`**. Everything else is evidence and sequencing.

---

## 4. How dogma assembled them (short story)

Not conspiracy — **gradient**:

1. Start GitHub-native (webhook, issue, PR, Jules Action).
2. Encode “human owns truth” as “nothing moves without human complete.”
3. Every failure adds a layer (base checks, mediated adapters, dual loops, extra status enums).
4. Agents read layers as terrain; freeze workarounds into AGENTS.md.
5. Direct Jules + local commit-ref arrive; **ingress and transport policy don’t get demoted.**
6. You operate the whole thing once; rebuild doc names the accretion.

Local reasonableness, global contradiction — same diagnosis as “multiple fractured agentic approaches.”

---

## 5. Three ways to assemble the same blocks

Only three. Same bin of parts. Different spine. **None is “the answer.”**

### Assembly 1 — Unattended factory (event-driven multi-executor)

**Spine:** durable queue + heartbeat tick + graph admission + multi-transport + eval on every return + provisional open + human complete later.

**Day in the life:** Something creates an event (webhook, or a stamped synthetic event). Classifier maps it to a ready node. Admission checks deps. Packet goes to whichever transport policy allows. Collect runs without needing a webhook. Evaluator always fires. Pass → provisional → next nodes can plan. You review receipts when you’re back and flip `complete` or reject.

**Uses hard:** graph, dependency policy (one copy ideally), admission, DB, packet/protocol, registry of transports, collect, eval engine, provisional, your review.

**Leaves on the shelf or demotes:** Action/Jules-issue as *required* path; decision-loop as live dispatcher; “webhook or it didn’t happen.”

**Optimizes:** Rigs comparing pathways while you’re away.  
**Costs:** More moving parts; easy to re-accrete ceremony.  
**Fails when:** Defaults still force Jules Action and complete-only gates somewhere.

### Assembly 2 — Direct node work (how you actually start jobs)

**Spine:** you name a node (and executor) → job/session → collect → **eval always** → provisional → next ready for you or the same executor to pick up.

**Day in the life:** No GitHub novel. `dispatch(node_id, local|jules_api|…)`. Same packet and eval as Assembly 1. Graph still sequences; ingress is **operator intent**, not issue noise. Heartbeat can shrink to “poll active sessions + maybe claim next ready,” not “digest the world’s webhooks.”

**Uses hard:** graph, packet/protocol, local (and peers) transport, collect, eval, provisional, base-chain, your complete.

**Leaves on the shelf:** webhook-forward as primary; classifier as required; return_router for the happy path; Action adapter.

**Optimizes:** Quick dispatch, neutral executor in *practice*, evaluator still the product.  
**Costs:** Cold start is explicit (you or a tiny scheduler must poke the first node). Less “magic from GitHub.”  
**Fails when:** `allowed_execution_modes` default still pretends Jules-only, or base checks silence eval.

### Assembly 3 — Eval shell around any work (graph soft, continuity manual)

**Spine:** bounded work happens however it happens (peer agent, harness packet, human PR). GDDP’s job is **canonical context + evaluator + receipt + your status write**. Graph may document deps; it need not drive a factory.

**Day in the life:** Work lands as a commit or artifact. You (or a thin hook) run the evaluator against node + neighbors + README/brief. Receipt goes in front of you. You update the graph by hand (or evidence PR). No provisional chains, no multi-adapter registry required.

**Uses hard:** graph as meaning, eval engine, receipts, you.  
**Leaves on the shelf:** heartbeat factory, classifier, most transports, provisional, base-chaining, dual control planes.

**Optimizes:** Minimum dogma; maximum clarity of “what is GDDP vs what is agent harness.”  
**Costs:** No unattended multi-node continuity; intent drift only caught when something invokes eval.  
**Fails when:** you pretend you still have a factory but only built a linter.

---

## 6. Side-by-side (only what changes the feeling of the system)

| | Factory (1) | Direct (2) | Eval shell (3) |
|--|-------------|------------|----------------|
| What starts work? | Event / classifier | You name the node | External / ad hoc |
| Must GitHub intake live? | Optional | No | No |
| Executors | Many, registry | Many, **you pick** | Often one-off |
| When does eval run? | On every collect/return | Same | When you invoke it |
| May next node open without you? | Provisional yes | Provisional yes | Only if you say so |
| Who writes `complete`? | You | You | You |
| Closest to “neutral + quick + eval each submission + continue” | If policy is honest | **Closest match** | Eval yes; continue no |

---

## 7. Load-bearing evidence (so this isn’t vibes)

- **Fused complete/dep freeze → provisional split:** `docs/GDDP-rebuild.md`; code `provisional_gate.py`, `scope_checker.SATISFIED_DEP_*`, `frontier.py`; git `5901769`, smoke `d59c172`.
- **Base used as veto before eval:** rebuild narrative (overnight three sessions); relax path `56db172`; chaining `a5e0eb9`.
- **Return router born auto-advance:** `1c00cdd` (2026-03-14); now receipt-only header in `return_router.py`.
- **Neutral protocol vs Jules default:** `executor_protocol.py` + adapters vs `graph_reader` default `["jules"]` and `_pick_executor` first mode.
- **Dual live return→eval doorbells:** `reconciler.EvaluationBatch` / `_finalize_evaluation` and `return_router` → `verify_job_return`.
- **Dead parallel dispatcher:** `decision_loop/powers/dispatch_next.py` still complete-only; not the heartbeat import graph.
- **Intake doesn’t own project_id:** `intake_server` stamps `project_id: None`; runner adopts by repo.

---

## 8. What this is for when you read it again

Ask per piece: **is this mechanism I still need, policy I chose, or glue from a dead assumption?**

Then pick an assembly *feeling* (1 / 2 / 3) — not a rewrite plan — and only later mark keep / mold / discard on the pieces that assembly actually uses.

**Audit complete for this pass.** No code changed. v1 table and v2 spreadsheet-of-40 are superseded by this file.
