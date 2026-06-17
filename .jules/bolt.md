## 2024-05-24 - min() vs sorted() for priority extraction
**Learning:** When retrieving the highest-priority node from a list of ready nodes, using `min()` instead of `sorted()` improves complexity from O(N log N) to O(N).
**Action:** Use `min()` or `max()` when only the single top/bottom element is needed, avoiding unnecessary complete sorts.