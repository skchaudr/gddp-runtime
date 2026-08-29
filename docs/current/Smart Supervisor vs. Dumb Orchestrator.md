
# Smart Supervisor vs. Dumb Orchestrator

A response or addendum to: ~/repos/gddp-runtime/.handoffs/106-orchestrator-context-contract-gap.md 

Yes. That distinction makes a lot of sense.

What you’re describing isn’t really an orchestrator that understands the run. It’s closer to a runtime supervisor whose entire worldview is:

There is supposed to be work happening. Are the workers alive? Are they progressing? If not, make the smallest intervention necessary to restore progress.

That is dramatically less context than “understand the graph, reason about node dependencies, evaluate project state, decide what should happen next.”

And I think the incident you mentioned—where the orchestrator decided to conduct a fucking research project instead of dispatching agents—is almost perfect evidence for the distinction. You gave something with broad reasoning capabilities enough informational surface that it could reinterpret its job. The failure wasn’t necessarily that the model was insufficiently intelligent. It had too much latitude about what its role meant.

The dumb version could have an almost comically small state:

expected workers:
  node-17 -> session A
  node-18 -> session B
  node-19 -> session C
for each worker:
  alive?
  currently working?
  last meaningful activity?
  waiting for input?
  blocked/error?
  intervention count?

And then an equally small action vocabulary:

start worker
inspect worker
send message
retry / nudge
replace worker
report escalation
do nothing

Critically, it doesn’t need to answer:

What does node 17 mean?
Is this implementation architecturally correct?
What should the graph do after node 18?
Should node 19 be accepted?
What research would help the executor?

Those belong elsewhere.

So Pi RPC becomes especially interesting because the supervisor doesn’t need to be the workers or retain their conversational state. Pi owns that. The supervisor can come back repeatedly and interrogate durable agent processes through RPC. In that architecture, worker persistence substitutes for orchestrator context persistence.

That changes the compaction question too.

I wouldn’t necessarily think of it as:

“How do I keep this smart orchestrator alive forever without context degradation?”

but rather:

“How little information does each supervision cycle require?”

Potentially each cycle could practically be stateless:

Read desired worker set.
Read actual Pi sessions.
Compare.
Inspect suspicious sessions.
Perform bounded corrective action.
Exit.

Then run again later.

If you do use a persistent smart model, your idea of aggressively compacting toward essentially the same canonical supervisor summary makes much more sense than normal conversational compaction. You’re deliberately destroying accumulated narrative because narrative is a liability here. The summary doesn’t need to progressively capture everything the orchestrator has learned. It can keep collapsing back toward:

Your responsibility is worker liveness and forward progress.
Dispatch required workers.
Observe them through Pi RPC.
Intervene only on concrete evidence of blockage/stall/failure.
Do not perform executor work.
Do not research the task.
Do not adjudicate node correctness.
Do not modify graph state beyond the explicitly permitted operations.

In fact, I think there’s a neat architectural principle hiding here:

The graph should contain the intelligence about what work exists. The executor should contain the intelligence required to do the work. The evaluator should contain the intelligence required to judge the work. The supervisor only needs enough intelligence to keep those machines moving.

That also fits extremely well with your broader frustration around independently mutable state. Making the orchestrator another rich representation of “what’s going on” means yet another thing that can disagree with the graph/runtime. Making it deliberately stupid means it can operate mostly on observable runtime facts, rather than maintaining its own interpretation of reality.
