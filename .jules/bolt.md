## 2024-05-14 - [O(E*N) list scans to O(E+N) dict lookup in Heartbeat event loop]
**Learning:** In the `_plan_dispatches` function, a loop over events (E) was internally using `next((n for n in ready_nodes if n.node_id == node_id), None)` to find matched ready nodes (N), resulting in an O(E*N) bottleneck.
**Action:** Always pre-compute a dictionary keyed by the lookup ID before looping over large event streams when you need to match attributes, reducing complexity to O(E + N).
