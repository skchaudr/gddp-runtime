After knowing things were off, and my own project was susceptible to drift, a reconciliation and ground truth needed to be established

First, Opus 4.8: 

"The vision is clear and it's the right one. Let me confirm I have it, then look up the openClaw heartbeat as you said.

The vision, restated so you can correct it:

You author nodes and the project map (the DAG) in gddp-config.
A runtime loop dispatches each node to an agent-agnostic executor (Claude, Jules, you, even pi-with-a-different-extension-set). The executor does the work and produces evidence.
The pi-based evaluator is a different role: it does NOT read AGENTS.md (that's for the executor). It reads the canonical narrative docs (README, PROJECT-BRIEF, the first/foundational node) plus the DAG neighborhood of the current node — every node that relates to it. Its sole job: prevent drift, preserve intent, protect project integrity. It is not checking tests; it is checking that the work matches the intent of the project and the node's place in the graph.
You review the evaluator's evidence and decide. Only you move a node to complete.
The whole thing is viable because it's just DAG traversal, and the openClaw heartbeat already proves a pi-binary-based dispatch loop runs for real (Microsoft/OpenAI-backed, not going away).
Now let me look up the openClaw heartbeat in your pi harness dir.


Explored 4 searches and thought 1 time
Now I get it. The openClaw heartbeat is already the dispatch engine you're describing, and GDDP maps onto it cleanly:

Packet = node. Your gddp-config node YAML is the bounded-work contract (the packet).
Dispatch targets = executors. targets.conf already lists pi,local, mac-claude (claude-code), hermes (ssh), agent1/agent2 (tmux claude), human, ipad. Agent-agnostic dispatch to Claude/Jules/you/pi-itself is a solved problem in your harness.
Heartbeat = pi-dispatch-loop / factory-heartbeat / pi-orchestrate. The loop that pulls packets and dispatches them.
Independent verification = the evaluator. Harness design principle #3: "Verification is independent of the agent's claims." That's the GDDP evaluator's exact job — don't trust the executor, verify against intent/integrity.
mutations: false hard-rejects write-capable tools = the read-only-where-it-matters guard.
Response serialization gated = the typed submit_verdict contract (parses or rejects).
So GDDP doesn't rebuild the loop. It adds three things on top of the openClaw engine: (1) the graph (DAG of nodes, not just a flat packet queue), (2) the evaluator's canonical-doc + DAG-neighborhood context (read README/PROJECT-BRIEF/foundational node + related nodes, not AGENTS.md), and (3) the human-review gate (only you flip a node). The pi-binary engine, the dispatch, the heartbeat, the verify-runner, the timestamped artifacts — all already exist and are battle-tested.

That's a clean, viable architecture. Now building the guard extension — the enforcement layer that makes "broad inputs, enforced outputs" real for the evaluator."

ChatGPT (steeped in GDDP project docs): 

Yeah — this is the first version of the architecture that feels small enough to actually exist and strong enough to justify itself.

The key breakthrough is that you stopped trying to make GDDP be “the whole agent system.”

Now it has a clean role:

GDDP is not the executor.
GDDP is not the agent harness.
GDDP is the intent-preservation and graph-integrity layer around work.

That distinction makes the whole thing click.

The clean stack is basically:

gddp-config
  = project intent + DAG + node contracts
openClaw / pi heartbeat / dispatch loop
  = packet routing + executor invocation + artifacts
executor
  = Claude / Jules / Codex / human / pi / whatever does the work
GDDP evaluator
  = semantic verifier against canonical docs + DAG neighborhood
Sab
  = final authority who moves node state

That is not delusional. That is a very normal distributed-work architecture, except aimed at agentic development instead of humans on Jira tickets.

The biggest conceptual win is this line:

The pi-based evaluator is a different role: it does NOT read AGENTS.md.

That matters a lot.

Because AGENTS.md is executor-facing. It tells the worker how to behave in the repo.

But the evaluator should not inherit the worker’s framing. The evaluator needs the project’s source of truth, not the executor’s operating instructions.

So the evaluator context being:

README
PROJECT-BRIEF
foundational / first node
current node
DAG neighbors
related upstream/downstream nodes
deterministic result/evidence

is exactly the right shape.

That gives you separation of concerns:

Executor asks:
“What do I need to do?”
Evaluator asks:
“Does what was done still preserve the project’s intended meaning?”

That is the drift-prevention boundary.

And honestly, the “only Sab moves node to complete” rule is not just a control preference. It is the architectural safety valve. It prevents the system from becoming self-certifying. The executor cannot complete itself. The evaluator cannot complete it either. The evaluator can only produce a structured verdict and evidence.

So the durable invariant becomes:

No node becomes complete without human acceptance of evidence.

That is simple, enforceable, and very hard to accidentally overcomplicate.

The phrase that feels like the real product boundary here is:

Broad inputs, enforced outputs.

Executors can be messy. Agents can vary. Some can be Claude, Jules, Pi, Codex, human, Grok, whatever.

But the evaluator must be boring:

read canonical context
read node + graph neighborhood
read deterministic evidence
emit typed verdict
reject malformed output
never mutate project state

That is where the guard extension belongs.

Not as “another agent.”

As the enforcement layer around the semantic verifier.

Something like:

semantic-evaluator/
  input_builder.py
  context_policy.py
  verdict_schema.json
  evaluator_prompt.md
  parse_verdict.py
  guard.py
  fixtures/

And the evaluator contract should probably be brutally plain:

{
  "verdict": "pass | block | drift | insufficient | contradicted | unknown",
  "confidence": "low | medium | high",
  "intent_preserved": true,
  "graph_integrity_preserved": true,
  "evidence": [],
  "risks": [],
  "required_human_review": true
}

The “required_human_review: true” is almost funny, but useful. It makes the verifier acknowledge its own place in the system.

This also resolves the earlier tension between deterministic and semantic verification:

Deterministic checks answer:
“Did the expected mechanical thing happen?”
Semantic evaluator answers:
“Does this still mean what the project meant?”

That is exactly why the evaluator should read DAG neighbors. A node can pass its local tests and still damage the project’s shape. The graph neighborhood is how you catch that.

The architecture is viable because the hard parts are no longer bundled together.

You do not need to invent:

a new agent runtime
a new async dispatch layer
a new worker protocol
a new TUI
a new everything

You already have the dispatch heartbeat shape.

GDDP adds:

graph-aware packet meaning
canonical intent context
typed semantic verdicts
human completion gate

That is a much smaller and more powerful claim.

The most important sentence from the whole thing might be:

GDDP doesn’t rebuild the loop.

Exactly.

It constrains, interprets, and verifies the loop.

That is a real system boundary.

------------ 

Claude points a really good point: 

Already built (matches ChatGPT's "enforcement layer around the semantic verifier"):

Guard extension = exactly "not another agent, the enforcement layer." Broad inputs, enforced outputs, never mutates project state, rejects/records blocked attempts.
submit_verdict typed terminal tool = "emit typed verdict, reject malformed output."
"Only Sab moves node to complete" = the safety valve, already canonized in your AGENTS.md addendum.
The gap worth naming for the next step: ChatGPT's proposed evaluator contract is intent/integrity-shaped, ours is still criteria-shaped:

code

theirs:  verdict (pass|block|drift|insufficient|contradicted|unknown), intent_preserved, graph_integrity_preserved, required_human_review
ours:    judgments[] (judged_pass|judged_fail|indeterminate), overall_reasoning, budget_exhausted
Ours answers "does the code meet each criterion?" Theirs answers "does this still mean what the project meant?" That's the exact delta the canonical-doc + DAG-neighborhood context work closes: once the evaluator reads README/PROJECT-BRIEF/foundational node + DAG neighbors (not just the current node's criteria), it can legitimately produce intent_preserved and graph_integrity_preserved — because "a node can pass its local tests and still damage the project's shape; the graph neighborhood is how you catch that." So the next vision step isn't just "add context," it's "graduate the verdict contract from criteria-only to intent+integrity."

--- 

I respond: I think it is time to put the final nail in the coffin of "this is about checking if the code passes tests"

ChatGPT responds: 

Yes. That is the clean coffin nail.

The distinction is not:

tests vs LLM judgment

The distinction is:

local correctness vs project meaning

Your current evaluator contract is still mostly shaped like a semantic test runner:

Given criteria, judge whether the implementation satisfies each criterion.

That is useful, but it is not yet the full GDDP vision.

The upgraded evaluator contract is shaped like an intent/integrity verifier:

Given canonical project intent, graph position, neighboring nodes, deterministic evidence, and implementation evidence, judge whether this work preserves the meaning and structure of the project.

That is the actual thing.

A node can satisfy its acceptance criteria and still be wrong because it may:

solve the wrong layer
collapse a future abstraction
violate an upstream design decision
duplicate responsibility owned by another node
change the project’s direction without authorization
make a local fix that creates graph-level drift
pass tests while weakening the project contract

That is why “does the code pass tests?” is not the center of gravity.

Tests are evidence. Criteria are evidence. Deterministic checks are evidence. They are not the verdict.

The verdict is closer to:

Does this completed work still preserve the project’s intended shape?

So the evolution is exactly:

v1 evaluator:
criteria satisfaction
v2 evaluator:
criteria satisfaction + intent preservation + graph integrity
v3 evaluator:
criteria satisfaction + intent preservation + graph integrity + explicit drift diagnosis

The contract shift matters because it changes what the model is allowed to notice.

With the current criteria-shaped output, the evaluator can say:

{
  "judgments": [
    {
      "criterion": "The dispatcher persists jobs",
      "judgment": "judged_pass"
    }
  ],
  "overall_reasoning": "The implementation satisfies the stated criteria."
}

That may be true and still incomplete.

The GDDP-shaped output needs room to say:

{
  "verdict": "drift",
  "intent_preserved": false,
  "graph_integrity_preserved": false,
  "criteria_result": "mostly_passed",
  "reasoning": "The implementation satisfies the local dispatcher criteria, but it moves project-level completion authority into the executor path, violating the canonical invariant that only the human operator can mark nodes complete.",
  "evidence": [
    "Current node asked for dispatch persistence.",
    "PROJECT-BRIEF defines human-gated completion.",
    "Neighbor node verification-runner owns completion review.",
    "Implementation added auto-complete behavior inside dispatch."
  ],
  "required_human_review": true
}

That is the difference.

The first evaluator says:

Looks good locally.

The second evaluator says:

It works, but it damaged the system contract.

That is the whole reason GDDP deserves to exist.

So the next step is not merely “add more context.” More context alone can still produce a criteria-shaped answer.

The next step is:

graduate the verdict contract

from this:

Did the implementation meet the node criteria?

to this:

Did the implementation preserve the node’s intended role inside the project graph?

That gives you the final clean framing:

GDDP verification is not test verification.
GDDP verification is intent preservation under graph constraints.
Tests prove behavior.
Criteria prove local satisfaction.
The evaluator checks whether the work still belongs in the project.
The human operator decides whether the node becomes complete.

That is very solid. It also explains why the evaluator should read canonical docs and DAG neighborhood instead of AGENTS.md.

AGENTS.md tells the executor how to work.

The canonical docs and graph tell the evaluator what must remain true.

That sentence alone kills the “it just checks tests” misunderstanding.
