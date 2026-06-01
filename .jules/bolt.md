## 2024-05-18 - Algorithm optimization in classification and dispatch
**Learning:** Found two O(N log N) and O(E*N) loops causing significant CPU bottlenecks in `classifier.py` and `runner.py` respectively. The first was easily solved by substituting an inefficient sorted lookup with a built-in min lookup. The second was optimized by substituting a list lookup with a hash map lookup.
**Action:** Always verify loops matching elements. If a list lookup needs to happen inside a loop over events, it's better to pre-compute a dictionary using a hash map before iterating.
