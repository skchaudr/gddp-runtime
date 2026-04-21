import sys
from unittest.mock import MagicMock

# Mock yaml since it's missing in the environment and required by GraphReader
try:
    import yaml
except ImportError:
    sys.modules["yaml"] = MagicMock()

import unittest
from scripts.runtime.openclaw.context_reader import read_project_state, ProjectState
from scripts.runtime.heartbeat.graph_reader import NodeData, ProjectGraph

class TestReadProjectState(unittest.TestCase):
    def setUp(self):
        self.mock_reader = MagicMock()
        self.project_id = "test-project"

    def test_read_project_state_categorization(self):
        # Setup mock project
        mock_project = ProjectGraph(
            project_id=self.project_id,
            project_name="Test Project",
            repo="owner/repo",
            nodes=[
                {"id": "node-pending"},
                {"id": "node-in-progress"},
                {"id": "node-complete"},
                {"id": "node-blocked"},
            ],
            execution_policy={}
        )
        self.mock_reader.load_project.return_value = mock_project

        # Setup mock nodes
        nodes_data = {
            "node-pending": NodeData(node_id="node-pending", title="Pending", status="pending", type="capability", why="", depends_on=[], acceptance=[], constraints=[], allowed_execution_modes=[], required_artifacts=[], priority="normal", unlocks=[]),
            "node-in-progress": NodeData(node_id="node-in-progress", title="In Progress", status="in_progress", type="capability", why="", depends_on=[], acceptance=[], constraints=[], allowed_execution_modes=[], required_artifacts=[], priority="normal", unlocks=[]),
            "node-complete": NodeData(node_id="node-complete", title="Complete", status="complete", type="capability", why="", depends_on=[], acceptance=[], constraints=[], allowed_execution_modes=[], required_artifacts=[], priority="normal", unlocks=[]),
            "node-blocked": NodeData(node_id="node-blocked", title="Blocked", status="blocked", type="capability", why="", depends_on=[], acceptance=[], constraints=[], allowed_execution_modes=[], required_artifacts=[], priority="normal", unlocks=[]),
        }

        def load_node(p_id, n_id):
            return nodes_data[n_id]

        self.mock_reader.load_node.side_effect = load_node

        # Execute
        state = read_project_state(self.mock_reader, self.project_id)

        # Assert
        self.assertIsInstance(state, ProjectState)
        self.assertEqual(state.project_id, self.project_id)
        self.assertEqual(state.repo, "owner/repo")
        self.assertEqual(len(state.nodes), 4)
        self.assertEqual(len(state.pending_nodes), 1)
        self.assertEqual(state.pending_nodes[0].node_id, "node-pending")
        self.assertEqual(len(state.in_progress_nodes), 1)
        self.assertEqual(state.in_progress_nodes[0].node_id, "node-in-progress")
        self.assertEqual(len(state.complete_nodes), 1)
        self.assertEqual(state.complete_nodes[0].node_id, "node-complete")
        self.assertEqual(len(state.blocked_nodes), 1)
        self.assertEqual(state.blocked_nodes[0].node_id, "node-blocked")

    def test_read_project_state_node_not_found_skipped(self):
        mock_project = ProjectGraph(
            project_id=self.project_id,
            project_name="Test Project",
            repo="owner/repo",
            nodes=[{"id": "node-exists"}, {"id": "node-missing"}],
            execution_policy={}
        )
        self.mock_reader.load_project.return_value = mock_project

        def load_node(p_id, n_id):
            if n_id == "node-missing":
                raise FileNotFoundError("Mock not found")
            return NodeData(node_id=n_id, title=n_id, status="pending", type="capability", why="", depends_on=[], acceptance=[], constraints=[], allowed_execution_modes=[], required_artifacts=[], priority="normal", unlocks=[])

        self.mock_reader.load_node.side_effect = load_node

        state = read_project_state(self.mock_reader, self.project_id)

        self.assertEqual(len(state.nodes), 1)
        self.assertEqual(state.nodes[0].node_id, "node-exists")

    def test_read_project_state_empty_project(self):
        mock_project = ProjectGraph(
            project_id=self.project_id,
            project_name="Empty Project",
            repo="owner/repo",
            nodes=[],
            execution_policy={}
        )
        self.mock_reader.load_project.return_value = mock_project

        state = read_project_state(self.mock_reader, self.project_id)

        self.assertEqual(len(state.nodes), 0)
        self.assertEqual(len(state.pending_nodes), 0)

    def test_read_project_state_other_status(self):
        mock_project = ProjectGraph(
            project_id=self.project_id,
            project_name="Test Project",
            repo="owner/repo",
            nodes=[{"id": "node-ready"}],
            execution_policy={}
        )
        self.mock_reader.load_project.return_value = mock_project

        self.mock_reader.load_node.return_value = NodeData(
            node_id="node-ready", title="Ready", status="ready",
            type="capability", why="", depends_on=[], acceptance=[],
            constraints=[], allowed_execution_modes=[], required_artifacts=[],
            priority="normal", unlocks=[]
        )

        state = read_project_state(self.mock_reader, self.project_id)

        self.assertEqual(len(state.nodes), 1)
        self.assertEqual(state.nodes[0].node_id, "node-ready")
        self.assertEqual(len(state.pending_nodes), 0)
        self.assertEqual(len(state.in_progress_nodes), 0)
        self.assertEqual(len(state.complete_nodes), 0)
        self.assertEqual(len(state.blocked_nodes), 0)

if __name__ == "__main__":
    unittest.main()
