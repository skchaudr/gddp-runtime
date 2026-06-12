## 2024-05-24 - [O(N log N) to O(N) optimization in classifier]
**Learning:** Selecting the highest priority element from an unsorted list was implemented using `sorted(list)[0]`, which takes O(N log N) time complexity. Since we only need the smallest element, `min(list)` gives O(N) time complexity.
**Action:** Always prefer `min()` or `max()` instead of `sorted()[0]` or `sorted()[-1]` when searching for a single extreme element, avoiding unnecessary sorting overhead.
