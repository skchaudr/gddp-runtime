# The Reckoning — GDDP vs. GDDP (2026-07-31)

**Status: judgment worksheet, not doctrine.** Each building block gets: what it
actually is, when and why it emerged (git evidence), what the architecture
pretends it is, and whether it serves or contradicts the core purpose. The
operator rules keep / mold / discard. Nothing in this file is a decision.

## The yardstick (the project's own words)

1. Detect drift — of intent and of project integrity. That is the entire purpose.
2. Only the human moves graph truth. The evaluator is the second-to-last gate.
3. Executors are replaceable transports. One neutral packet, one result contract.
4. GDDP constrains, interprets, and verifies the loop. It is not the executor
   and not the agent harness.
5. Preserve forward agentic momentum — keep work moving while catching drift.

## The timeline that explains the fracture

- **Mar 12–19**: GDAD era. Schema, webhook intake, heartbeat, classifier,
  dispatcher, scope checker, return router — the machinery skeleton.
- **May 12**: "drift" language first appears (docs).
- **Jun 21–30**: CLI era + evaluator built (decision engine, semantic lanes).
- **Jul 4**: Doctrine canonized (GDDP-becomes-small-and-real,
  Tests-can-fail-nodes-can-pass) — **after** most machinery existed.
- **Jul 7–29**: Executor era. default_executor field, reconciler, adapter
  contract, local_agent_executor, jules_api, frontier, rebuild doc.
- **Jul 30–31**: Provisional flow + base-chaining + smoke run 1. First live
  end-to-end proof of the core loop.

The doctrine was written down four months after the machinery started, and the
machinery never conformed back. That is the original sin every entry below
inherits from.

---

## The pieces

### 1. Node schema + status model (`schemas/v1/node.yaml`)
- **Is:** the unit of intent. YAML contract for a bounded piece of work.
- **Emerged:** Mar 12, Phase 1 initial commit — before any executor or evaluator.
- **Pretends:** nothing. It says what it is.
- **Verdict evidence:** ALIGNED. Statuses pending/ready/complete/deferred from
  day one; `provisional` added Jul 30 to unstick the loop without touching
  human-owned `complete`. Proven in smoke run 1.

### 2. `allowed_execution_modes` + `VALID_EXEC_MODES`
- **Is:** a per-node allowlist of executor brand names; validator blesses
  modes the runtime cannot dispatch (`agent`, `vertex`, `pi_worker`,
  `vm_worker`, `human` have no adapters).
- **Emerged:** Mar 12, day-one schema field. No case, no design discussion.
  Survived every rewrite by inertia.
- **Pretends:** to be capability constraints. In practice it's executor
  identity baked into graph truth.
- **Verdict evidence:** CONTRADICTS yardstick 3 (executor neutrality). The
  phantom modes created the Jul 30 fixture failure (node said `agent`, no
  adapter existed). Operator ruled Jul 31: executor neutrality is expressed
  by `auto` → project default, not by brand lists.

### 3. `execution_policy` + `default_executor` (project.yaml)
- **Is:** per-project knobs: default executor, concurrency cap, retry budget.
- **Emerged:** execution_policy Mar 13; default_executor Jul 7 hardening.
- **Pretends:** to configure dispatch. `default_executor` is declared in every
  project.yaml and **read by nothing** (zero consumers, verified Jul 31).
  max_concurrent_jobs and retry_budget are read.
- **Verdict evidence:** HALF-ALIGNED. The read knobs work; the unread one is
  the honest home for "dispatch without naming a transport" (yardstick 3),
  waiting to be wired.

### 4. The graph DAG (depends_on, unlocks)
- **Is:** dependency edges between units of intent; the frontier derives from it.
- **Emerged:** Mar 12.
- **Pretends:** nothing. Stays a DAG; evidence links are separate.
- **Verdict evidence:** ALIGNED. Yardstick 2 and 5 both depend on it.

### 5. gddp CLI + TUI (`scripts/gddp.py`, node_cli)
- **Is:** the operator control plane — node CRUD, status, jobs, validate,
  positional dispatch. Single operator-facing surface.
- **Emerged:** Jun 22–23 ("fast node and graph pipeline"); unified Jul 21.
- **Pretends:** nothing. It does what the operator journey says.
- **Verdict evidence:** ALIGNED. Proven tonight: dispatch preview, jobs show,
  node show all reflect live truth (after four display-drift fixes Jul 31).

### 6. Positional dispatch (`gddp <node-id>` → manual_inject event)
- **Is:** operator names a node, gets a preview, confirms; an audited event
  enters the queue. One command.
- **Emerged:** discovered Jul 31 already-built (commit c8cd057 lineage); the
  session almost built a duplicate `gddp dispatch` command before finding it.
- **Pretends:** nothing.
- **Verdict evidence:** ALIGNED. Yardstick 5 in one keystroke. Proven tonight.

### 7. Intake server (GitHub webhook receiver, Flask)
- **Is:** HTTP endpoint that turns GitHub webhooks into queue events.
- **Emerged:** Mar 13, GDAD runtime initial commit — when the system was
  GitHub-webhook-intake → classify → scope → queue → execute.
- **Pretends:** to be the front door. For local/operator dispatch it is a
  side door nobody uses; the manual_inject path bypasses it entirely.
- **Verdict evidence:** CEREMONY for the current operating shape. Born of the
  assumption that work arrives via GitHub events. Still the only path for
  PR-triggered flows. Not contradictory — but not the front door anymore.

### 8. Events table + classifier (issue.opened, `node:` tag matching)
- **Is:** every dispatch (webhook or manual) becomes an `issue.opened`-shaped
  row; the classifier finds a `node: <id>` tag in url/branch/payload and maps
  it to a ready node, picking the executor from the node's mode list.
- **Emerged:** Mar 13. Tag-matching exists because untagged public-repo issues
  must never spend executor budget on a guessed node (a real guard).
- **Pretends:** to classify intent. For manual dispatches the "classification"
  is theater — the operator already named the node; the event is pre-chewed
  and the classifier re-chews it.
- **Verdict evidence:** ALIGNED as a guardrail for genuine GitHub intake;
  CEREMONY for operator dispatch. The manual event shape (issue.opened
  costume) exists only to fit this classifier.

### 9. Scope checker (`scope_checker.py`)
- **Is:** dispatch gate — deps satisfied, no active job for the node.
- **Emerged:** Mar 13.
- **Pretends:** nothing.
- **Verdict evidence:** ALIGNED. One of the four dep-gate sites; widened to
  provisional Jul 30. Proven: B's first dispatch correctly refused.

### 10. frontier.py (derived operating frontier)
- **Is:** read-only derivation of what's dispatchable now, with blockers.
- **Emerged:** Jul 27.
- **Pretends:** nothing.
- **Verdict evidence:** ALIGNED. Second dep-gate site (SATISFIED_DEP_STATUSES).

### 11. Heartbeat runner (`--all-active`, 5-min ticks)
- **Is:** the loop driver: claims events, plans dispatches, polls sessions,
  queues evaluations.
- **Emerged:** Mar 13 (heartbeat vNext).
- **Pretends:** nothing.
- **Verdict evidence:** ALIGNED, with one drift found tonight: `_active_projects`
  ignored active executor sessions, making resume-after-collect invisible
  (fixed 6bf5a41). Capacity, claiming, and FIFO all worked under load tonight.

### 12. Dispatcher + ADAPTERS registry
- **Is:** maps executor mode → adapter; creates job/session rows.
- **Emerged:** Mar 13; neutral adapter contract formalized Jul 18.
- **Pretends:** to be a plugin registry. In truth it's a dict of three plus a
  mediated alias — small, honest, and sufficient.
- **Verdict evidence:** ALIGNED. Yardstick 3's enforcement point. The phantom
  modes (piece 2) are what made it look broken.

### 13. local_subprocess adapter + local_agent_executor.py (the wrapper)
- **Is:** the generic harness hook. Wrapper creates the worktree at the base
  sha, pipes the packet to any CLI argv, then **itself** stages, commits,
  refs (`gddp/attempt-*`), and emits the result JSON. The agent speaks no
  protocol.
- **Emerged:** Jul 23, "real local subprocess dispatch."
- **Pretends:** nothing — but the session almost misdescribed it as
  "headless-only execution," which would exclude interactive and swarm work.
  The contract is: packet + base in, commit out. Any producer of that triple
  qualifies (headless CLI, interactive session, boss-mode swarm, a human).
- **Verdict evidence:** ALIGNED with the executor-neutral doctrine — this IS
  the neutral contract, working. Proven twice tonight (grok-4.5, both nodes).

### 14. jules_api adapter (+ jules_cli, mediated `jules`)
- **Is:** remote executor transport: Jules REST lifecycle, remote branches,
  PR-shaped returns.
- **Emerged:** jules_api Jul 26, after the "Jules needs webhooks" assumption
  died. jules_cli and the mediated `jules` alias predate it.
- **Pretends:** three modes where one is real. jules_cli is superseded;
  mediated `jules` is a compatibility shim.
- **Verdict evidence:** ALIGNED that it exists (second transport proves
  neutrality); UNEXAMINED in tonight's run (run 2 is its proof). The three
  names for one thing is naming debt, not architecture.

### 15. Runtime state model (jobs, queue_state, executor_sessions, results)
- **Is:** the evidence ledger. Jobs are attempts; sessions are executor runs;
  results are evaluator verdicts. Graph truth lives elsewhere.
- **Emerged:** Mar 13 jobs; Jul 17 sessions; results rows with the evaluator.
- **Pretends:** nothing — and the Jul 30 audit found it honest: evidence
  stays evidence, only humans move nodes.
- **Verdict evidence:** ALIGNED. Yardstick 2's enforcement layer. One stale-
  state bug found (failed job holding queue_state=running since Jul 11).

### 16. Reconciler (collect, resume, evaluation batch)
- **Is:** polls active sessions, collects result commits onto durable refs,
  queues and finalizes evaluations, fires the provisional gate.
- **Emerged:** Jul 17.
- **Pretends:** nothing.
- **Verdict evidence:** ALIGNED. The collected-resume path (re-evaluate
  without re-execute) was designed-in and used twice tonight. Proven.

### 17. The evaluator (deterministic + semantic + integrity, 12-row matrix)
- **Is:** the drift detector. Floor (deterministic) + Brain (semantic tool
  loop) + intent/integrity lane, combined worst-of into a verdict receipt.
- **Emerged:** Jun 30 (Floor+Brain); integrity lane and hardening through
  Jul 2.
- **Pretends:** nothing — this is the piece the whole project exists for.
- **Verdict evidence:** ALIGNED and proven live: judged both smoke nodes on
  intent AND criteria, byte-exact, with graph observations that correctly
  diagnosed its own deterministic blind spot. Two drifts found tonight: dep
  gate still required `complete` (fixed 74fe53d), and the deterministic lane
  couldn't see non-code artifacts (fixed d83ca5d). Confidence is informational,
  never a gate — threshold gating is an unbuilt, operator-deferred feature.

### 18. Provisional gate (`provisional_gate.py`)
- **Is:** on verdict pass + intent/integrity preserved + no human_gate flag,
  writes `provisional` to the node. Idempotent.
- **Emerged:** Jul 30 (tonight), after the operator ruled: default flow for
  all nodes, no confidence floor, human_gate is the only opt-in brake.
- **Pretends:** nothing.
- **Verdict evidence:** ALIGNED. The minimum change that unsticks yardstick 5
  without touching yardstick 2. Proven twice tonight (A and B).

### 19. Base-chaining (`_chained_base`, runner.py)
- **Is:** a node with one provisional dep dispatches on that dep's result
  commit instead of HEAD; multiple provisional deps defer with a reason.
- **Emerged:** Jul 30 — designed only after the smoke fixture exposed that
  provisional unblocked status but not base.
- **Pretends:** nothing.
- **Verdict evidence:** ALIGNED. Without it, provisional flow dispatches
  dependents onto code that lacks their predecessor's work. Proven: B built
  on A's `77ba473`, inherited a.txt, bounded one-file diff.

### 20. Legacy verify harness (`gddp-config/scripts/verify_node.py`)
- **Is:** a second, older copy of the verification logic living in the config
  repo. The runtime's deterministic lane was "ported from" it.
- **Emerged:** Jun 29 — one day BEFORE the runtime evaluator (Jun 30).
- **Pretends:** to be the same evaluator. It drifts: its dep gate required
  `complete` until Jul 31; its deterministic checks lack every fix the
  runtime copy got.
- **Verdict evidence:** CONTRADICTS by duplication. Two copies of one
  judgment is how tonight's four-gate drift happened. The runtime copy is
  the live one; this is the ancestor that still answers `gddp verify node`.

### 21. Return router (`scripts/runtime/return_router.py`)
- **Is:** merged-PR events route to re-dispatch/retry instead of classify.
- **Emerged:** Mar 14; graph mutation severed from return flow Apr 3.
- **Pretends:** nothing, but it serves the GitHub-shaped pipeline (piece 7/8).
- **Verdict evidence:** UNEXAMINED tonight. ALIGNED-in-principle (retry is
  evidence-driven) but its value tracks the webhook pipeline's value.

### 22. mini-heartbeat kit (arm.sh, plists, gddp.env)
- **Is:** launchd packaging for the loop on sab-mini; env-sourced executor argv.
- **Emerged:** Jul 11 (dormant pack).
- **Pretends:** nothing.
- **Verdict evidence:** ALIGNED. Tonight's plist drift (Codex inline-editing
  the live plist, bypassing the kit) showed exactly why the kit exists;
  re-arming through it restored env-sourced config. Executor model swap
  (minimax→grok-4.5) was then a one-line env edit.

### 23. Evidence store (`verification-runtime-live/`, receipts, evaluations.yaml)
- **Is:** per-node verdict receipts with tool traces, confidences, graph
  observations; the review queue's raw material.
- **Emerged:** with the evaluator, Jun 30+.
- **Pretends:** nothing.
- **Verdict evidence:** ALIGNED. Yardstick 1's memory. One display bug
  (receipt count always 0) fixed Jul 31. This is the calibration corpus for
  any future threshold feature.

### 24. Doctrine docs + PROJECT-BRIEF
- **Is:** the written identity: GDDP-becomes-small-and-real (Jul 4),
  Tests-can-fail-nodes-can-pass (Jul 4), GDDP-rebuild (Jul 29), PROJECT-BRIEF
  (Jun 21).
- **Emerged:** AFTER the machinery (see timeline). The docs describe the
  target; the code predates the description.
- **Pretends:** that the machinery conformed. It didn't — pieces 2, 7, 8, 20
  are the standing contradictions.
- **Verdict evidence:** these are the truest statements of intent the project
  has. The reckoning exists because the code drifted from them, not the
  reverse.

### 25. Confidence scores (evaluator self-assessment)
- **Is:** per-lane confidences on every receipt (0.965 criteria, 0.92
  integrity tonight).
- **Emerged:** with the evaluator.
- **Pretends:** nothing yet — but threshold-gated flow ("above X flows,
  below X blocks, in-band gets N retries") is the operator's stated next
  feature, deferred until he's calibrated on real receipts.
- **Verdict evidence:** ALIGNED as information (orders the review queue).
  UNBUILT as a gate — correctly, per the operator's no-confidence-floor rule.

---

## The map

**Aligned and proven live (run 1, tonight):** node schema + statuses (1),
CLI/TUI (5), positional dispatch (6), scope checker (9), frontier (10),
heartbeat (11), dispatcher (12), local executor wrapper (13), runtime state
model (15), reconciler (16), evaluator (17), provisional gate (18),
base-chaining (19), mini-heartbeat kit (22), evidence store (23).

**Aligned, unexamined tonight:** jules_api (14 — run 2 is its proof),
return router (21).

**Known-contradictory:** allowed_execution_modes + phantom modes (2 —
executor identity in graph truth), legacy verify harness (20 — duplicate
judgment, drifting), unread default_executor (3 — declared intent, zero
consumers).

**Ceremony (serves a shape we no longer operate):** intake server as front
door (7), classifier tag-theater for operator dispatch (8).

**Doctrine itself:** sound (24). The drift was machinery contradicting
doctrine while quoting it — never the reverse.

## What GDDP actually is today (evidence) vs. what it says it is

**Says:** an intent-preservation and drift-detection layer around work, where
a human owns graph truth and executors are replaceable transports.

**Is, as of tonight:** exactly that, for the path that ran — node → dispatch
→ local executor → evaluator → provisional → human review — plus a GitHub-
event exoskeleton from March that the live path routes around, an executor
allowlist that contradicts neutrality, and a duplicate evaluator in the
config repo. The working core is small and real. The exoskeleton is not
load-bearing.

## Questions only the operator can rule on

1. `auto` → default_executor: wire it (classifier + CLI preview + explicit
   override honored), and strip phantom modes from VALID_EXEC_MODES?
2. The legacy verify harness: converge `gddp verify node` onto the runtime
   evaluator, or delete the config-side copy?
3. The webhook exoskeleton (intake, classifier theater, return router):
   keep as the GitHub-only lane, or simplify now that manual_inject carries
   operator dispatch?
4. `allowed_execution_modes` after `auto`: shrink to genuine capability
   requirements (and rename), or drop the field?
5. Threshold gating: after receipt calibration, does confidence ever gate —
   and if so, is the gate per-node opt-in like human_gate?

*End of worksheet. Every entry above carries its evidence; every ruling is yours.*
