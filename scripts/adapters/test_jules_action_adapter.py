import unittest
from unittest.mock import patch, MagicMock
import subprocess
import json
import sys
from pathlib import Path

# Add the root directory to sys.path to allow importing from scripts.adapters
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.adapters.jules_action_adapter import JulesActionAdapter, _flatten, DispatchResult

class TestJulesActionAdapter(unittest.TestCase):
    def setUp(self):
        self.repo = "owner/repo"
        self.adapter = JulesActionAdapter(self.repo)
        self.sample_job = {
            "job_id": "job_123",
            "node_id": "node_456",
            "title": "Fix bug",
            "goal": "Repair the leaking pipe",
            "why": "Water is everywhere",
            "constraints": json.dumps(["Don't use duct tape", {"material": "copper"}]),
            "acceptance_criteria": json.dumps(["No leaks", ["test 1", "test 2"]])
        }

    def test_flatten_string(self):
        self.assertEqual(_flatten("simple string"), "simple string")

    def test_flatten_dict(self):
        self.assertEqual(_flatten({"key": "value", "a": "b"}), "key: value — a: b")

    def test_flatten_list(self):
        self.assertEqual(_flatten(["item1", "item2", 3]), "item1, item2, 3")

    def test_build_issue_body(self):
        body = self.adapter.build_issue_body(self.sample_job)
        self.assertIn("## Goal\nRepair the leaking pipe", body)
        self.assertIn("## Why\nWater is everywhere", body)
        self.assertIn("- Don't use duct tape", body)
        self.assertIn("- material: copper", body)
        self.assertIn("- [ ] No leaks", body)
        self.assertIn("- [ ] test 1, test 2", body)
        self.assertIn("node: node_456", body)
        self.assertIn("job: job_123", body)
        self.assertIn("does not advance graph truth automatically", body)

    @patch("subprocess.run")
    def test_dispatch_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/owner/repo/issues/42\n",
            stderr=""
        )

        result = self.adapter.dispatch(self.sample_job)

        self.assertTrue(result.success)
        self.assertEqual(result.issue_url, "https://github.com/owner/repo/issues/42")
        self.assertEqual(result.issue_number, 42)
        self.assertIsNone(result.error)

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "gh")
        self.assertIn("--repo", cmd)
        self.assertIn(self.repo, cmd)
        self.assertIn("--label", cmd)
        self.assertIn("jules", cmd)

    @patch("subprocess.run")
    def test_dispatch_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: repository not found"
        )

        result = self.adapter.dispatch(self.sample_job)

        self.assertFalse(result.success)
        self.assertIsNone(result.issue_url)
        self.assertEqual(result.error, "Error: repository not found")

    @patch("subprocess.run")
    def test_dispatch_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["gh"], timeout=30)

        result = self.adapter.dispatch(self.sample_job)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "gh CLI timed out")

    @patch("subprocess.run")
    def test_dispatch_exception(self, mock_run):
        mock_run.side_effect = Exception("Unexpected error")

        result = self.adapter.dispatch(self.sample_job)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Unexpected error")

if __name__ == "__main__":
    unittest.main()
