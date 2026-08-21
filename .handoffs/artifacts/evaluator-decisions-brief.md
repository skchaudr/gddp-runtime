# Evaluator — three decisions, in plain language

Consolidated brief. The three earlier artifacts referenced below are the detail; this is the decision surface.

---

## Decision 1 — The evaluator can notice the graph is wrong, but its notices evaporate

**This is the big one — the evaluator is not acting the way GDDP wants it to.**

What GDDP wants: after each node is evaluated, a second, independent model (the "integrity lane") looks at the work plus your graph and asks *"does the project still point where you intended?"* — and when it sees the graph needs changing, it tells you specifically.

What happens today: the lane runs on every evaluation and CAN notice real things. Proof from your own data — in the myapi run it wrote:

> "node-13-preserve-results depends on all three concurrent eval branches… only q3/q4 artifacts exist so far, so node-13 will block until node-10 and node-12 produce their results."

That is genuine graph foresight. Today it goes exactly one place: a single prose line in the OBSERVATIONS section of the browse screen. It has no way to say *"so add a checkpoint"* or *"serialize these nodes"* — there is no vocabulary for a proposed change — and nothing collects these notices into a place you review. The evaluator's defining job produces notes that die on arrival.

**The proposed fix** (spec already drafted): let that same evaluation run attach typed *recommendations*: one of eight actions (split a node / replace it / insert a prerequisite / revise its criteria / add or remove a dependency / reorder a region / create a missing node / retire an unnecessary one), each naming the affected nodes, the reason, and the evidence — optionally a draft node YAML you could paste in. It never changes any verdict and never triggers a retry; it appears in a dedicated RECOMMENDATIONS block in the browse screen where you accept or ignore each one. No extra model calls; same evaluation run.

**Your decision:** approve the spec → I build it. Or reject/reshape it.
Spec: `.handoffs/artifacts/graph-recommendation-channel-spec.md` (four small checkboxes at the bottom: keep the 8-word action list or trim one; keep drafts receipt-only vs also writing them into a proposals folder; should a recommendation force human review on its own — spec says no; field name).

---

## Decision 2 — When an executor returns nothing evaluable, the evaluator goes silent

Two halves, one theme: the evaluator should always render *some* judgment.

**Half A — the commit gate.** To evaluate, the evaluator needs the commit hash of the executor's work. If an executor dies without committing, evaluation produces nothing: no verdict, no receipt — the job routes to review with an error note. This has not happened yet (87/87 live evaluations were fine), but your own invariant (docs/invariants/invariants.md, §3.5 "Evaluation Precedes Admission Control") says no gate may kill the evaluator's judgment.

Choices:
1. **Leave it.** If it happens, you see an error record. Zero work.
2. **Record a judgment anyway (recommended).** Even when there is nothing to evaluate, mint a one-line receipt: "evaluator ran — no committed work returned." ~10 lines of code; the promise holds mechanically.
3. **Evaluate the uncommitted mess anyway.** Bigger build, weaker evidence; not recommended.

**Half B — jobs that never reach evaluation.** Evaluation only fires while the heartbeat is actively tracking a session. If a session falls out of tracking, its work sits forever unevaluated. Nothing catches that today.

Choices:
1. **Schedule the sweep agent you already have (recommended).** A `sweep` agent exists for exactly this (finds landed-work-without-verdict and evaluates it via the sanctioned path). Put it on a schedule.
2. **Build detection into the heartbeat itself.** More machinery; only worth it if the sweep proves insufficient.
3. **Leave it.**

Detail memo: `.handoffs/artifacts/evaluator-admission-decision-memo.md`

---

## Decision 3 — Can a text-matching check alone fail a node?

Some acceptance criteria are checked by grepping for expected text. Today, if the grep fails, the node gets FAIL and no model ever looks at the code to contest it (the model lane only runs when the deterministic check says "unsure").

**Live record: this has never actually bitten.** Across 128 receipts, deterministic checks said "unsure" 379 times (each correctly escalated to a model) and "fail" exactly once — and that once was a real test command that failed, where finality is correct.

Choices:
1. **Leave it (recommended).** No observed harm; you can still reject any verdict by hand. Revisit if it ever fires wrongly.
2. **Let a model contest non-command failures.** Closes the door preemptively; costs one extra model run on that rare path.

Detail memo: `.handoffs/artifacts/heuristic-fail-finality-memo.md`
