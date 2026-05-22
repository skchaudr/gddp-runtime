import sqlite3
import time
from dataclasses import dataclass

from runtime.heartbeat.classifier import classify
from runtime.heartbeat.graph_reader import NodeData


class MockRow(dict):
    def keys(self):
        return super().keys()

    def __getattr__(self, key):
        return self[key]

def run_benchmark():
    # Setup mock data
    num_events = 1000
    num_nodes = 1000

    events = [MockRow({"event_type": "issue.opened", "event_id": f"evt_{i}"}) for i in range(num_events)]
    ready_nodes = [
        NodeData(
            node_id=f"node_{i}",
            title="Test Node",
            status="ready",
            type="capability",
            why="Test Why",
            depends_on=[],
            acceptance=[],
            constraints=[],
            allowed_execution_modes=["jules"],
            required_artifacts=[],
            priority="normal",
            unlocks=[],
        )
        for i in range(num_nodes)
    ]

    # Measure classify
    start_time = time.time()
    for event in events:
        classify(event, ready_nodes)
    classify_time = time.time() - start_time
    print(f"Classify {num_events} events with {num_nodes} nodes: {classify_time:.4f} seconds")

    # Measure lookup (similar to _plan_dispatches inner loop)
    # The actual _plan_dispatches fetches all events and iterates over them.
    # Inside the loop, it calls classify, then looks up the node.
    start_time = time.time()
    ready_nodes_by_id = {n.node_id: n for n in ready_nodes}
    for event in events:
        classification = classify(event, ready_nodes)
        node_id = classification["matched_node_id"]
        node = ready_nodes_by_id.get(node_id)
    lookup_time = time.time() - start_time - classify_time
    print(f"Node lookup loop for {num_events} events: {lookup_time:.4f} seconds")

if __name__ == "__main__":
    run_benchmark()
