"""
test_replay.py — Tests for the replay logic.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add the parent directory to sys.path to allow importing from the current package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.runtime import replay

class TestReplay(unittest.TestCase):

    @patch('scripts.runtime.replay.connect')
    @patch('scripts.runtime.return_router.handle_merged_pr')
    def test_replay_result_success(self, mock_handle, mock_connect):
        # Setup mocks
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_event = {'event_id': 'evt_123', 'event_type': 'pull_request.closed', 'project_id': 'test'}
        mock_con.execute.return_value.fetchone.return_value = mock_event
        mock_handle.return_value = {"status": "completed"}

        # Run
        replay.replay_result("res_123")

        # Assert
        mock_con.execute.assert_called_with("SELECT * FROM events WHERE event_id = ?", ("evt_123",))
        mock_handle.assert_called_with(mock_event)

    @patch('scripts.runtime.replay.connect')
    def test_replay_result_not_found(self, mock_connect):
        # Setup mocks
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_con.execute.return_value.fetchone.return_value = None

        # Run
        replay.replay_result("res_not_found")

        # Assert (should just print error and return)
        mock_con.execute.assert_called_with("SELECT * FROM events WHERE event_id = ?", ("evt_not_found",))

    @patch('scripts.runtime.replay.connect')
    @patch('scripts.runtime.heartbeat.dispatcher.dispatch')
    @patch('scripts.runtime.heartbeat.state_recorder.mark_job_running')
    @patch('scripts.runtime.heartbeat.state_recorder.mark_event_mapped')
    @patch('builtins.input', return_value='yes')
    def test_replay_job_success(self, mock_input, mock_mapped, mock_running, mock_dispatch, mock_connect):
        # Setup mocks
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_job = {
            'job_id': 'job_123',
            'event_id': 'evt_123',
            'node_id': 'node_123',
            'project_id': 'test',
            'executor': 'jules',
            'goal': 'test goal',
            'status': 'failed',
            'repo': 'owner/repo'
        }
        mock_con.execute.return_value.fetchone.return_value = mock_job

        mock_dispatch_res = MagicMock()
        mock_dispatch_res.success = True
        mock_dispatch_res.issue_url = "http://issue"
        mock_dispatch.return_value = mock_dispatch_res

        # Run
        replay.replay_job("job_123")

        # Assert
        mock_dispatch.assert_called_with(mock_job, 'owner/repo')
        mock_mapped.assert_called_with(mock_con, 'evt_123')
        mock_running.assert_called_with(mock_con, 'job_123')
        mock_con.commit.assert_called()

    @patch('scripts.runtime.replay.connect')
    @patch('builtins.input', return_value='no')
    def test_replay_job_aborted(self, mock_input, mock_connect):
        # Setup mocks
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        mock_job = {
            'job_id': 'job_123',
            'event_id': 'evt_123',
            'node_id': 'node_123',
            'project_id': 'test',
            'executor': 'jules',
            'goal': 'test goal',
            'status': 'failed',
            'repo': 'owner/repo'
        }
        mock_con.execute.return_value.fetchone.return_value = mock_job

        # Run
        replay.replay_job("job_123")

        # Assert
        mock_con.commit.assert_not_called()

if __name__ == "__main__":
    unittest.main()
