import unittest
from unittest.mock import MagicMock, patch, call
import json
import os
import sys
from pathlib import Path

# Add the root directory to sys.path to allow imports from scripts
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.heartbeat import run_heartbeat, PHASE3_NODE

class TestHeartbeatLogic(unittest.TestCase):

    @patch("scripts.heartbeat.connect")
    @patch("scripts.heartbeat.JulesActionAdapter")
    @patch("scripts.heartbeat.ts_id")
    @patch("scripts.heartbeat.now")
    @patch("scripts.heartbeat.job_dir")
    def test_run_heartbeat_success(self, mock_job_dir, mock_now, mock_ts_id, mock_adapter_class, mock_connect,):
        # Setup mocks
        mock_now.return_value = "2023-01-01T00:00:00Z"
        mock_ts_id.return_value = "20230101000000000"
        mock_job_dir.return_value = Path("/tmp/job_123")

        mock_con = MagicMock()
        mock_cur = mock_con.cursor.return_value
        mock_connect.return_value = mock_con

        # Mock an event
        mock_event = {
            "event_id": "evt_123",
            "event_type": "issue.opened"
        }
        mock_cur.fetchall.return_value = [mock_event]

        # Mock adapter
        mock_adapter = mock_adapter_class.return_value
        mock_dispatch_result = MagicMock()
        mock_dispatch_result.success = True
        mock_dispatch_result.issue_url = "http://github.com/issue/1"
        mock_adapter.dispatch.return_value = mock_dispatch_result

        # Run heartbeat
        run_heartbeat("owner/repo")

        # Verify calls
        mock_cur.execute.assert_any_call("SELECT * FROM events WHERE status = 'received'")

        # Check classification update
        classification = {
            "category": "implementation_request",
            "intent": "advance_existing_node",
            "in_scope": True,
            "matched_node_id": PHASE3_NODE["node_id"],
            "executor_recommendation": "jules",
            "requires_code_execution": True,
            "requires_human_review": False,
        }
        mock_cur.execute.assert_any_call(
            "UPDATE events SET status = 'classified', classification = ?, scope_status = 'in_scope' WHERE event_id = ?",
            (json.dumps(classification), "evt_123")
        )

        # Check job insertion (partial check of the query or just that it was called)
        # We can check that the number of calls to execute is as expected

        # Check dispatch
        mock_adapter.dispatch.assert_called_once()
        dispatched_node = mock_adapter.dispatch.call_args[0][0]
        self.assertEqual(dispatched_node["node_id"], PHASE3_NODE["node_id"])
        self.assertEqual(dispatched_node["job_id"], "job_20230101000000000")

        # Check final status updates
        mock_cur.execute.assert_any_call(
            "UPDATE events SET status = 'mapped' WHERE event_id = ?", ("evt_123",)
        )
        mock_con.commit.assert_called_once()

    @patch("scripts.heartbeat.connect")
    def test_run_heartbeat_no_events(self, mock_connect):
        mock_con = MagicMock()
        mock_cur = mock_con.cursor.return_value
        mock_connect.return_value = mock_con
        mock_cur.fetchall.return_value = []

        run_heartbeat("owner/repo")

        mock_cur.execute.assert_called_once_with("SELECT * FROM events WHERE status = 'received'")
        mock_con.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
