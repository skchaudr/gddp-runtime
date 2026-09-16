## 2024-06-11 - Optimize event node matching in heartbeat runner
**Learning:** In the `_plan_dispatches` loop, performing a linear scan over `ready_nodes` for every event using `next((n for n in ready_nodes if n.node_id == node_id), None)` causes O(E * N) complexity. This becomes a bottleneck as the number of events and nodes grows.
**Action:** Always pre-compute a dictionary keyed by the lookup property (e.g., `ready_nodes_by_id = {n.node_id: n for n in ready_nodes}`) before processing event loops to reduce complexity to O(E + N) and enable O(1) lookups.
