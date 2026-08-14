# Direction — where this is all going

Status: north star. Sab's riff (refined with ChatGPT), 2026-08-13. Pairs with
FLEET-VISION.md (the window) and FACTORY-MAINTENANCE-PLAN.md (the staff);
this is the why and the next mountain.

## The composition

Persistence lives in the filesystem and state, not in agent processes.
Maintenance is not a standing swarm — it is named, disposable invocations:

    .pi/agents/{steward,janitor,bridgekeeper,sweep,medic}.md

Run one from the TUI or a timer; it lives 90 seconds, performs one bounded
job, writes its tiny artifact, dies. Radically cheaper than any orchestration
layer.

And agents stay small because knowledge stays in the project (ICM):
AGENTS.md / CONTEXT.md / current-state maps hold what the project knows;
the agent file holds only role + permissions + task. Separate what the
project knows from what an invocation is allowed and expected to do.

## The experiment: escape the closed loop

GDDP has been both the thing under development and the thing used to develop
it. That proved mechanics; it cannot prove generality. MyAPI is the next
serious workload — real knowledge-architecture problems (ingestion,
provenance, authoritative snapshots, retrieval, Graphify artifacts), important
in its own right, and far enough from GDDP's problem-space to be convincing.

    GDDP ──develops/maintains──► MyAPI ──organized through──► ICM context architecture
                                        ▲
              maintained by bounded project-local Pi agents ──┘

Four claims tested simultaneously, kept as separate systems:

1. **GDDP** — can the graph reliably drive substantial development?
2. **ICM** — can a project stay understandable without giant context loads?
3. **Project-local Pi agents** — can maintenance be cheap disposable
   invocations instead of another fleet?
4. **MyAPI** — can the machinery produce a substantial independent project?

## The stress test (the thing the machinery is supposed to buy)

Start MyAPI work with a **fresh capable agent**. No accumulated history —
give it the GDDP node plus whatever the context architecture says to read.
If that agent can repeatedly enter, understand, make a bounded contribution,
leave an inspectable artifact, and exit — and the next fresh agent picks up
from there — the machinery has demonstrated its actual purpose.

Mechanically proven tonight at trivial scale (loop-soak: four zero-context
agents, 4/4 pass). MyAPI is the same contract with real stakes.
