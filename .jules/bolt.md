## 2024-05-28 - [O(N) Lookups for Classifier Target Priorities]
**Learning:** Selecting the target with the highest priority using `sorted(nodes)[0]` scales as O(N log N). Because Python's min function allows a key function similar to sorted, `min(nodes)` provides an O(N) solution for exactly this problem.
**Action:** Always prefer `min()` or `max()` over `sorted()[0]` or `sorted()[-1]` when fetching extreme elements from large unordered sets/lists in order to reduce runtime complexity.
