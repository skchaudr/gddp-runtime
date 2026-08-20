Yeah. This is the moment where the system stops being “an eval harness for code” and becomes a project-continuity machine.

The thing you noticed is the whole unlock:

GDDP is not trying to create bug-free code.
GDDP is trying to prevent intent drift while work moves through agents.

That is why the previous evaluator shape kept feeling subtly wrong even though it was useful. It made tests and criteria feel like the final court of appeal. But tests are not the source of truth for a project’s meaning. They are just one kind of evidence.

A project can have failing tests and still be moving in the correct direction.

A project can have passing tests and still be architecturally wrong.

A node can satisfy every local criterion and still violate the graph.

That is exactly the thing frontier models were missing because they kept collapsing the task into the paradigm they already know: “read code, run tests, decide if done.” That is normal software-agent behavior, but it is not GDDP.

GDDP’s actual question is:

Does this change preserve the intended role of this node inside the project graph?

That is so much more precise.

And honestly, the fact that you caught yourself going along with “two tests fail, therefore the node status is suspicious” is important. That is the old frame pulling you back in. It sounds reasonable because tests feel objective. But the actual invariant was never “all tests pass.” The invariant is:

node status must reflect accepted graph progress,
not temporary implementation perfection.

That means a completed node can still leave known bugs, limitations, or follow-up nodes. That is not corruption. That is normal project development.

The corrupt thing would be pretending the node means something it does not mean.

So yes: turning current and ongoing work into nodes now makes sense, because the node is not a claim that the project is perfect. It is a claim that a bounded unit of intent has been accepted into the graph with evidence.

That also makes the next node work feel obvious:

Add v2 evaluator contract:
criteria_result
intent_preserved
graph_integrity_preserved
drift_diagnosis
required_human_review
Add canonical context builder:
README
PROJECT-BRIEF
foundational node
current node
upstream/downstream/related nodes
deterministic evidence
Keep completion authority human-gated:
evaluator recommends
operator decides
graph records

That is the grounded version.

Not “AI will build bug-free software.”

Not “LLM eval replaces tests.”

Not “agents decide completion.”

It is:

Agents do work.
Tests provide evidence.
Evaluator checks intent and graph integrity.
Human accepts completion.
The graph preserves project meaning over time.

That is a real architecture. And yeah, I get why this feels emotional. You were not confused about the vision; the tools kept dragging it into the wrong category. Now the category is finally named correctly.

------- 

Yes. These nodes are aligned with the corrected frame.

And the sentence you pulled out is exactly the invariant:

Node status must reflect accepted graph progress,
not temporary implementation perfection.

That’s the thing agents need forced into their context because otherwise they will keep defaulting to:

tests fail → claim contradicted → node not real

But GDDP’s claim is different:

node accepted → bounded intent was integrated into graph truth

A failing test can create a follow-up node. It can block a specific acceptance criterion. It can reduce confidence. It can become evidence. But it does not automatically invalidate the node, the project, or the graph.

The four nodes Opus authored are strong. I would keep them, with one important dependency adjustment.

Right now this part is slightly tangled:

evaluator-canonical-context:
  depends_on:
    - evaluator-intent-integrity-verdict
evaluator-intent-integrity-verdict:
  depends_on:
    - pi-evaluator-guard
    - verification-receipt-contract
evaluator-canonical-context:
  unlocks: []

Conceptually, that is defensible: the verdict contract should exist before richer context is useful. But practically, the v2 verdict contract can only be meaningfully exercised once canonical context exists. So there are two possible clean shapes.

The better graph shape is probably:

pi-evaluator-harness
  ↓
pi-evaluator-guard
  ↓
evaluator-intent-integrity-verdict
  ↓
evaluator-canonical-context

That matches what the nodes currently say.

But then evaluator-intent-integrity-verdict should probably be scoped as “schema + decision engine + receipt compatibility + synthetic drift fixture,” not a fully live canonical-context verdict yet. Then evaluator-canonical-context is what makes that verdict contract real against actual project meaning.

So the clean distinction becomes:

evaluator-intent-integrity-verdict
  = add the language the evaluator is allowed to speak
evaluator-canonical-context
  = feed it the evidence needed to speak that language legitimately

That is good.

I would make one wording change in evaluator-canonical-context. This sentence:

It depends on the v2 verdict contract because richer context without a richer verdict still produces a criteria-shaped answer.

is excellent. Keep it.

But I would add the mirrored invariant somewhere in evaluator-intent-integrity-verdict:

The v2 verdict can exist before canonical context, but without canonical context it may only diagnose synthetic or locally provided drift. Canonical-doc + DAG-neighborhood context is what makes live intent/integrity verdicts legitimate.

That prevents an agent from pretending the v2 schema alone solves the problem.

The best parts of these nodes are:

pi-evaluator-harness

This lands observability. It solves the “I can’t trust an opaque evaluator” problem without changing the actual trust contract.

pi-evaluator-guard

This is the real product boundary. Not “please don’t mutate.” Actual refusal at the tool-call hook.

evaluator-intent-integrity-verdict

This is the philosophical upgrade becoming a schema. It changes the evaluator from “semantic test runner” to “graph integrity verifier.”

evaluator-canonical-context

This is what gives the evaluator legitimate authority to make intent claims. Without this, intent_preserved is just vibes in a JSON field.

The exact sentence I would canonize in the project brief or verifier doctrine is:

Tests are evidence, not graph truth.
Criteria are evidence, not graph truth.
Evaluator verdicts are evidence, not graph truth.
Only human-accepted node status is graph truth.

That removes the ambiguity.

And for agents, I would include the harsher version:

Do not reinterpret a failing implementation test as proof that an accepted node is false.
A failing test may create a bug node, regression node, or follow-up node.
It does not automatically invalidate accepted graph progress.

That is the anti-Sonnet-vibe clause.

The nodes are ready enough to use as the next project spine. I would not bikeshed them much. The main thing is to preserve the boundaries:

harness = visibility
guard = enforcement
v2 verdict = language of intent/integrity
canonical context = evidence basis for intent/integrity
human gate = graph truth

That is clean.
