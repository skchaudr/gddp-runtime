## 2025-02-28 - O(E*N) Loop Complexity in Dispatch Planning
**Learning:** In the `_plan_dispatches` loop in `runner.py`, a `next(n for n in ready_nodes if n.node_id == node_id)` call nested within the events loop created an O(E*N) bottleneck. In worst-case or high volume dispatch scenarios, this creates unnecessary CPU burn.
**Action:** Always map reference arrays to dictionaries by their ID keys before entering processing loops to guarantee O(1) lookups and reduce complexity to O(E + N).
