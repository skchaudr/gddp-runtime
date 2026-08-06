## 2026-06-04 - Optimize Node Lookup
**Learning:** In the heartbeat runner, sequential processing of incoming events requires looking up the matched node ID from the list of ready nodes. Searching the list for each event is an O(E*N) operation. Converting the ready nodes to a hash map beforehand reduces this to O(E+N), showing a measurable performance increase.
**Action:** Use dictionary lookups to avoid iterating over the same lists repeatedly inside loops.
