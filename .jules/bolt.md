## 2026-06-08 - Heartbeat loop optimizations
**Learning:** Performance in `_plan_dispatches` (`runner.py`) degraded significantly as events and ready nodes grew because `node_id` lookups took O(N) inside an O(E) loop (total O(E*N)), and `classify` sorting took O(N log N) for each event.
**Action:** Always pre-compute a dictionary lookup (`{n.node_id: n for n in ready_nodes}`) before loops to change lookups from O(E*N) to O(E + N). Replace `sorted()[0]` with `min(..., key=...)` in `classify.py` to change complexity from O(N log N) to O(N).
