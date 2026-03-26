"""
test_return_router.py — Tests for the return router logic.
"""

import sys
import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# Mock missing modules before they are imported by return_router
sys.modules["requests"] = MagicMock()
sys.modules["yaml"] = MagicMock()

# Add the parent directory to sys.path to allow importing from the current package
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.runtime.return_router import parse_node_id, validate_repo, handle_merged_pr

class TestReturnRouter(unittest.TestCase):

    def test_parse_node_id(self):
        # Standard case
        body1 = "This PR implements the feature.\n\nnode: auth-boundary\njob: job_123"
        self.assertEqual(parse_node_id(body1), "auth-boundary")

        # Case insensitivity
        body2 = "Fixed stuff.\nNODE: data-sync\n"
        self.assertEqual(parse_node_id(body2), "data-sync")

        # Extra whitespace
        body3 = "node:    scan-vault-core   "
        self.assertEqual(parse_node_id(body3), "scan-vault-core")

        # Missing tag
        body4 = "No node tag here."
        self.assertIsNone(parse_node_id(body4))

        # Tag not on its own line (should fail based on ^ requirement)
        body5 = "The node: tag is here"
        self.assertIsNone(parse_node_id(body5))

    def test_validate_repo(self):
        self.assertTrue(validate_repo("skchaudr/vault-doctor"))
        self.assertFalse(validate_repo("other/repo"))

    @patch("scripts.runtime.return_router.write_result")
    @patch("scripts.runtime.return_router.update_graph_node_complete")
    def test_handle_merged_pr_success(self, mock_update, mock_write):
        # Setup mocks
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 12,
                "body": "node: auth-node",
                "merged_at": "2024-03-20T10:00:00Z",
                "html_url": "https://github.com/skchaudr/vault-doctor/pull/12"
            }
        }

        mock_update.return_value = {"ok": True, "commit_sha": "sha123"}

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        # Verify result
        self.assertEqual(res, {"status": "completed", "commit_sha": "sha123"})

        # Verify write_result calls
        # 1. pending
        mock_write.assert_any_call(
            result_id="res_123456",
            repo_name="skchaudr/vault-doctor",
            node_id="auth-node",
            pr_number=12,
            merged_at="2024-03-20T10:00:00Z",
            status="pending"
        )
        # 2. completed
        mock_write.assert_any_call(
            result_id="res_123456",
            repo_name="skchaudr/vault-doctor",
            status="completed",
            commit_sha="sha123"
        )

    @patch("scripts.runtime.return_router.write_result")
    def test_handle_merged_pr_invalid_repo(self, mock_write):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "other/repo"},
            "pull_request": {"number": 13}
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(res, {"status": "rejected", "reason": "repo_not_allowed"})
        mock_write.assert_called_once_with(
            result_id="res_123456",
            repo_name="other/repo",
            status="rejected",
            reason="repo_not_allowed: other/repo",
            pr_number=13
        )

    @patch("scripts.runtime.return_router.write_result")
    def test_handle_merged_pr_missing_node_tag(self, mock_write):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 14,
                "body": "No node tag here"
            }
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(res, {"status": "rejected", "reason": "missing_node_tag"})
        mock_write.assert_called_once_with(
            result_id="res_123456",
            repo_name="skchaudr/vault-doctor",
            status="rejected",
            reason="missing_node_tag",
            pr_number=14
        )

    @patch("scripts.runtime.return_router.write_result")
    @patch("scripts.runtime.return_router.update_graph_node_complete")
    def test_handle_merged_pr_update_failure(self, mock_update, mock_write):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 15,
                "body": "node: test-node"
            }
        }

        mock_update.return_value = {"ok": False, "reason": "something went wrong"}

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(res, {"status": "failed", "reason": "something went wrong"})
        # 1. pending
        mock_write.assert_any_call(
            result_id="res_123456",
            repo_name="skchaudr/vault-doctor",
            node_id="test-node",
            pr_number=15,
            merged_at=None,
            status="pending"
        )
        # 2. failed
        mock_write.assert_any_call(
            result_id="res_123456",
            repo_name="skchaudr/vault-doctor",
            status="failed",
            reason="something went wrong"
        )

if __name__ == "__main__":
    unittest.main()
