import timeit
import random

class NodeData:
    def __init__(self, node_id, priority):
        self.node_id = node_id
        self.priority = priority

priorities = ["high", "normal", "low", "unknown"]
nodes = [NodeData(f"node_{i}", random.choice(priorities)) for i in range(1000)]

def test_sorted():
    priority_order = {"high": 0, "normal": 1, "low": 2}
    target = sorted(nodes, key=lambda n: priority_order.get(n.priority, 1))[0]

def test_min():
    priority_order = {"high": 0, "normal": 1, "low": 2}
    target = min(nodes, key=lambda n: priority_order.get(n.priority, 1))

print("sorted:", timeit.timeit(test_sorted, number=10000))
print("min:", timeit.timeit(test_min, number=10000))
