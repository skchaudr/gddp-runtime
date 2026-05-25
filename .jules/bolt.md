## 2024-05-24 - Heartbeat runner list scan bottleneck
**Learning:** Found an O(N*E) loop inside the heartbeat event processor where `next(n for n in ready_nodes...)` is called for every event. With lots of events and nodes, this list scan becomes a bottleneck.
**Action:** Always convert lists to dictionaries keyed by the lookup id before loops when doing repeated lookups.
