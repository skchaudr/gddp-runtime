## 2024-05-26 - Optimize node lookups in heartbeat runner
**Learning:** Linear lookups `next((n for n in list if condition))` inside loops processing multiple events (e.g., in `_plan_dispatches`) can create an unexpected $O(E \times N)$ performance bottleneck when handling many events and nodes.
**Action:** When repeatedly searching a collection by a unique identifier within a loop, construct a lookup dictionary *before* the loop. This reduces lookup complexity to $O(1)$, yielding significant measurable speedups (~10x in micro-benchmarks).
