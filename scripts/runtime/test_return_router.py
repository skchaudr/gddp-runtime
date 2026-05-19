"""
test_return_router.py — Tests for review-receipt routing on merged PRs.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

# Add the parent directory to sys.path to allow importing from the current package
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.runtime.return_router import (
    handle_merged_pr,
    parse_job_id,
    parse_node_id,
    validate_repo,
)


class TestReturnRouter(unittest.TestCase):
    def test_parse_node_id(self):
        body1 = "This PR implements the feature.\n\nnode: auth-boundary\njob: job_123"
        self.assertEqual(parse_node_id(body1), "auth-boundary")

        body2 = "Fixed stuff.\nNODE: data-sync\n"
        self.assertEqual(parse_node_id(body2), "data-sync")

        body3 = "node:    scan-vault-core   "
        self.assertEqual(parse_node_id(body3), "scan-vault-core")

        body4 = "No node tag here."
        self.assertIsNone(parse_node_id(body4))

    def test_parse_job_id(self):
        body1 = "node: auth-boundary\njob: job_123"
        self.assertEqual(parse_job_id(body1), "job_123")

        body2 = "JOB: job_456"
        self.assertEqual(parse_job_id(body2), "job_456")

        body3 = "No job tag here."
        self.assertIsNone(parse_job_id(body3))

    def test_validate_repo(self):
        self.assertTrue(validate_repo("skchaudr/vault-doctor"))
        self.assertFalse(validate_repo("other/repo"))

    @patch("scripts.runtime.return_router._mark_job_awaiting_review")
    @patch("scripts.runtime.return_router.write_result")
    @patch("scripts.runtime.return_router._load_job")
    def test_handle_merged_pr_success(self, mock_load_job, mock_write, mock_mark_review):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 12,
                "body": "node: auth-node\njob: job_123",
                "merged_at": "2024-03-20T10:00:00Z",
                "html_url": "https://github.com/skchaudr/vault-doctor/pull/12",
            },
        }
        mock_load_job.return_value = {
            "job_id": "job_123",
            "repo": "skchaudr/vault-doctor",
            "node_id": "auth-node",
            "executor": "jules",
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(
            res,
            {
                "status": "needs_review",
                "result_id": "res_123456",
                "job_id": "job_123",
                "node_id": "auth-node",
            },
        )
        from unittest.mock import ANY
        mock_write.assert_called_once_with(
            result_id="res_123456",
            job_id="job_123",
            executor="jules",
            outcome="success",
            status="needs_review",
            received_at="2024-03-20T10:00:00Z",
            github_action={
                "source": "merged_pr",
                "event_id": "evt_123456",
                "repo_name": "skchaudr/vault-doctor",
                "pr_number": 12,
                "merged_at": "2024-03-20T10:00:00Z",
                "merged_pr_url": "https://github.com/skchaudr/vault-doctor/pull/12",
                "node_id": "auth-node",
                "review_required": True,
                "raw_payload_path": "payload.json",
            },
            con=ANY,
        )
        mock_mark_review.assert_called_once_with("job_123", ANY)

    @patch("scripts.runtime.return_router.write_result")
    def test_handle_merged_pr_invalid_repo(self, mock_write):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "other/repo"},
            "pull_request": {"number": 13},
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(res, {"status": "rejected", "reason": "repo_not_allowed"})
        mock_write.assert_not_called()

    @patch("scripts.runtime.return_router.write_result")
    def test_handle_merged_pr_missing_node_tag(self, mock_write):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 14,
                "body": "job: job_123",
            },
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(res, {"status": "rejected", "reason": "missing_node_tag"})
        mock_write.assert_not_called()

    @patch("scripts.runtime.return_router.write_result")
    def test_handle_merged_pr_missing_job_tag(self, mock_write):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 15,
                "body": "node: test-node",
            },
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(res, {"status": "rejected", "reason": "missing_job_tag"})
        mock_write.assert_not_called()

    @patch("scripts.runtime.return_router.write_result")
    @patch("scripts.runtime.return_router._load_job")
    def test_handle_merged_pr_rejects_unknown_job(self, mock_load_job, mock_write):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 16,
                "body": "node: auth-node\njob: job_123",
            },
        }
        mock_load_job.return_value = None

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(res, {"status": "rejected", "reason": "job_not_found"})
        mock_write.assert_not_called()

    @patch("scripts.runtime.return_router.write_result")
    @patch("scripts.runtime.return_router._load_job")
    def test_handle_merged_pr_rejects_mismatched_job_metadata(self, mock_load_job, mock_write):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 17,
                "body": "node: auth-node\njob: job_123",
            },
        }
        mock_load_job.return_value = {
            "job_id": "job_123",
            "repo": "skchaudr/vault-doctor",
            "node_id": "other-node",
            "executor": "jules",
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(res, {"status": "rejected", "reason": "node_job_mismatch"})
        mock_write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
