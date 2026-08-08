# gddp-runtime fun facts

A handful of interesting stories and technical details from the project's history.

---

## 1. The AGENTS.md anti-pattern warning

The project's AGENTS.md opens with a stark warning about a recurring failure pattern:

> "An agent assumes that a certain behavior exists. That agent designs around that assumption without verifying. The system fails because the assumption was false. More machinery was proposed to fix the failure and that invented workaround becomes architecture."

This isn't theoretical -- it's a description of what actually happened. The warning was written after observing multiple instances where agents (including the project author) built elaborate machinery to work around failures that could have been prevented by verifying assumptions first. The doctrine documents (Tests-can-fail, GDDP-becomes-small-and-real) were extracted from these failures.

**The lesson:** Architecture should not be invented to work around failures that could have been prevented by checking first.

---

## 2. KillMode=process is mandatory

The systemd service file for the heartbeat runner contains a critical directive:

```ini
# KillMode=process is REQUIRED: the tick spawns executor supervisors
KillMode=process
```

Why? Because the heartbeat runner spawns executor supervisor processes, and systemd's default `KillMode=control-group` would kill all of them when the heartbeat stops. This would leave orphaned executor sessions running, consuming resources and potentially corrupting state.

The `KillMode=process` setting ensures that only the heartbeat process itself is killed, leaving the executor supervisors to shut down cleanly. This was learned the hard way -- the FRESH-HOST-STANDUP.md documents commit `d45afaf` as the fix for "systemd KillMode reaping executors."

**The lesson:** Systemd defaults are not always what you want, especially when your process spawns children that need to outlive it (or shut down gracefully).

---

## 3. The node: tagging requirement

On **Jul 8, 2026**, a commit landed: `fix(classifier): require explicit node tag -- no fallback dispatch`. Before this fix, the classifier would fall back to dispatching work to a default node if no explicit tag was provided. This created ambiguity about which node was actually being worked on, making it impossible to trace evidence back to a specific node in the graph.

The fix required explicit node tagging, ensuring that every piece of work is associated with a specific node. This closed a gap in the evidence chain -- without explicit tagging, it was impossible to know whether a failing test was evidence against the intended node or just a misrouted dispatch.

**The lesson:** Fallback behavior can silently corrupt the evidence chain. Explicit is better than implicit, especially when you're trying to trace causality.

---

## 4. Tests-can-fail doctrine

The doctrine document `docs/Tests-can-fail-nodes-can-pass.md` (canonized Jul 4, 2026) states:

> "Node status reflects accepted graph progress, not temporary implementation perfection. Tests are evidence, not graph truth. Criteria are evidence, not graph truth. Evaluator verdicts are evidence, not graph truth. Only human-accepted node status is graph truth."

This doctrine was written in response to a recurring problem: agents would mark a node as failed because a test failed, even when the human had already accepted the node. The doctrine clarifies that tests are evidence, not verdicts. A failing test might indicate a bug, or it might indicate that the test itself needs updating. The human decides.

**The lesson:** Evidence is not truth. Only human judgment can accept or reject a node's state.

---

## 5. The oldest Python code

The first Python files in the repository date from **2026-03-13**, the day of the initial commit. These were adapter stubs under `scripts/adapters/`, specifically `scripts/adapters/__init__.py`. The adapter layer has been continuously present since day one, though it has been heavily refactored.

The heartbeat runner (`scripts/runtime/heartbeat/runner.py`, now 821 lines) also traces its lineage to the first week, though it has been rewritten multiple times. The event-driven architecture -- heartbeat processes events, dispatches to executors, collects receipts -- has been the core shape since the beginning.

**The lesson:** Some architectural decisions are right from the start. The event-driven heartbeat shape has survived five months of continuous development without fundamental revision.
