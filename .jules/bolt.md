## 2024-05-18 - [Optimize Node Lookup]
**Learning:** O(E*N) lookups within an event processing loop can quickly become a bottleneck when both E (events) and N (nodes) scale up. By converting a list into a dictionary keyed by ID before entering the loop, lookup complexity drops to O(1), bringing the total operation time from O(E*N) to O(E+N).
**Action:** Always look for O(N) list-based searches `next(item for item in list if item.id == search_id)` occurring inside another loop. Refactor by pre-computing a dictionary hash map outside the loop for O(1) lookups.
