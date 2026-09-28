## 2025-06-16 - O(E*N) to O(E+N) in runner.py
**Learning:** Linear search inside a loop iterating over database rows is a performance anti-pattern in the heartbeat framework. Specifically, converting a list of available nodes to a dictionary mapping prior to matching events drops the algorithmic complexity of event dispatching from O(E*N) to O(E+N).
**Action:** Before iterating through events during dispatch or evaluation loops, transform linearly searched lists into dictionaries keyed by the target search field.
