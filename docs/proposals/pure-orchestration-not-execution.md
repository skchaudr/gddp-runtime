
# Orchestrator and Lifecycle Control Blocker

The orchestrator cannot safely say “this attempt is dead, start another one” today, because the runtime has no clean public operation that makes that statement true.

What exists right now is basically:

`jobs set failed` = mutate bookkeeping

not:

`cancel attempt` = stop/neutralize executor + prevent late-result resurrection + transition lifecycle coherently

That distinction is huge.

And the late-result resurrection is particularly nasty because it violates the boring-orchestrator model at the *exact place* where you need determinism. If the orchestrator marks something failed, but the still-running executor can later finish, get collected, run evaluation, and rewrite the job back to awaiting_review, then “failed” is not actually a terminal lifecycle action. It’s just a temporary opinion stored in the DB.

So I think the correct architectural read is now:
- The orchestrator can safely have observational lifecycle authority today.
- It can inspect liveness, staleness, completion, crashes, and results.
- But active lifecycle termination authority is not safely exposed yet.

That’s a much narrower and cleaner statement than “we need to redesign cancellation.”

And this is exactly where I would resist scope creep again. The Pi-orchestrator task does not suddenly need to implement gddp jobs cancel. GLM should record:

```
> Hard limitation discovered: GDDP currently lacks a safe public cancellation primitive for a live executor. Therefore the initial Pi orchestrator must not attempt to mark active jobs failed and redispatch them. It should detect and report suspected stuck/hung attempts to the human operator.
```

That still gives you a perfectly useful v1:

dispatch → observe → detect completion/crash/stall → report/recommend → human handles unsupported cancellation cases

Then gddp jobs cancel becomes a very crisp separate runtime task later, with an unusually well-defined contract because GLM just traced exactly what it would need to preserve.

And I especially like what this investigation reveals about the larger design principle:

Authority should only be granted where the system has a real atomic-ish operation backing it.

You don’t want the orchestrator’s prompt saying “you may cancel attempts” because some combination of database writes sort of approximates cancellation. You want a real control surface where:

cancel(job) means one coherent lifecycle action.

Until that exists, the orchestrator doesn’t own cancellation.

That is boring in the best possible way.
