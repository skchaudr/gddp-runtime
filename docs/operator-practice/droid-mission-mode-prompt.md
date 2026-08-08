/Users/sab-mini/repos/gddp-runtime/docs/two-mode-executor-architecture.md

Okay so the goal is to figure out how to run GDDP graphs and Droid's mission mode together 

At first GDDP would wrap up the executor, call it non-interactively, and owned its lifecycle, ensured it was in the right worktree, made sure it committed at the end, etc 

But now GDDP owned the executor, the very thing I intended for it not to do, so that we could be flexible, and we weren't 

We ran droid! droid exec mode ran well, it did well, but, the first mission mode I attempted to run (mission mode has built in orchestration, validation, and user-end testing, huge pros) I realized, we couldn't. It could not run missions on graphs, only nodes, so we could hand off a graph and let droid knock out nodes, because our process was per node 

So, the goal is to get questions answered, and then implement based on what we discover, the cleanest mission architecture for GDDP 
