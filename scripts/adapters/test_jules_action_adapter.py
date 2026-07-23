import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from adapters.executor_protocol import DispatchResult, NodePacket
from adapters.jules_action_adapter import JulesActionAdapter, _flatten


class TestJulesActionAdapter(unittest.TestCase):
    def setUp(self):
        self.repo = "owner/repo"
        self.adapter = JulesActionAdapter(self.repo)
        self.sample_packet = NodePacket(
            job_id="job_123",
            execution_attempt_id="job_123:attempt:0",
            node_id="node_456",
            title="Fix bug",
            goal="Repair the leaking pipe",
            why="Water is everywhere",
            constraints=("Don't use duct tape", {"material": "copper"}),
            acceptance_criteria=("No leaks", ("test 1", "test 2")),
            required_artifacts=(),
            attempt_index=0,
        )

    def test_flatten_string(self):
        self.assertEqual(_flatten("simple string"), "simple string")

    def test_flatten_dict(self):
        self.assertEqual(_flatten({"key": "value", "a": "b"}), "key: value — a: b")

    def test_flatten_list(self):
        self.assertEqual(_flatten(["item1", "item2", 3]), "item1, item2, 3")

    def test_build_issue_body(self):
        body = self.adapter.build_issue_body(self.sample_packet)
        self.assertIn("## Goal\nRepair the leaking pipe", body)
        self.assertIn("## Why\nWater is everywhere", body)
        self.assertIn("- Don't use duct tape", body)
        self.assertIn("- material: copper", body)
        self.assertIn("- [ ] No leaks", body)
        self.assertIn("- [ ] test 1, test 2", body)
        self.assertIn("node: node_456", body)
        self.assertIn("job: job_123", body)
        self.assertIn("does not advance graph truth automatically", body)

    def test_build_issue_body_with_required_artifacts(self):
        packet = replace(
            self.sample_packet,
            required_artifacts=("decision.md", "result-summary.md", "patch.diff"),
        )
        body = self.adapter.build_issue_body(packet)
        self.assertIn("## Required Artifacts", body)
        self.assertIn("decision.md", body)
        self.assertIn("result-summary.md", body)
        self.assertIn("patch.diff", body)
        self.assertIn("executor-receipt.md", body)

    def test_build_issue_body_includes_strengthened_metadata_reminder(self):
        body = self.adapter.build_issue_body(self.sample_packet)
        self.assertIn("CRITICAL", body)
        self.assertIn("PR Metadata Block Required", body)
        self.assertIn("node: node_456", body)
        self.assertIn("job: job_123", body)
        self.assertIn("This is not optional", body)

    def test_build_issue_body_without_required_artifacts(self):
        packet = replace(self.sample_packet, required_artifacts=())
        body = self.adapter.build_issue_body(packet)
        self.assertNotIn("## Required Artifacts", body)
        # Rest of the body is still correct
        self.assertIn("## Goal\nRepair the leaking pipe", body)
        self.assertIn("## Why\nWater is everywhere", body)
        self.assertIn("node: node_456", body)

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run")
    def test_dispatch_reports_missing_token_when_gh_auth_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not logged in")

        result = self.adapter.dispatch(self.sample_packet)

        self.assertFalse(result.success)
        self.assertIsNone(result.issue_url)
        self.assertEqual(
            result.error,
            "Missing GitHub token: set GITHUB_TOKEN/GH_TOKEN or authenticate gh",
        )
        mock_run.assert_called_once_with(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run")
    def test_dispatch_uses_gh_auth_token_fallback(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="keychain-token\n", stderr=""),
            MagicMock(
                returncode=0,
                stdout="https://github.com/owner/repo/issues/42\n",
                stderr="",
            ),
        ]

        result = self.adapter.dispatch(self.sample_packet)

        self.assertTrue(result.success)
        self.assertEqual(mock_run.call_count, 2)
        issue_call = mock_run.call_args_list[1]
        self.assertEqual(issue_call.args[0][:3], ["gh", "issue", "create"])
        self.assertEqual(issue_call.kwargs["env"]["GH_TOKEN"], "keychain-token")

    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run")
    def test_dispatch_reports_missing_token_when_gh_auth_times_out(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["gh", "auth", "token"], timeout=10)

        result = self.adapter.dispatch(self.sample_packet)

        self.assertFalse(result.success)
        self.assertEqual(
            result.error,
            "Missing GitHub token: set GITHUB_TOKEN/GH_TOKEN or authenticate gh",
        )

    @patch.dict("os.environ", {"GITHUB_TOKEN": "github-token-value"}, clear=True)
    @patch("subprocess.run")
    def test_dispatch_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/owner/repo/issues/42\n",
            stderr=""
        )

        result = self.adapter.dispatch(self.sample_packet)

        self.assertTrue(result.success)
        self.assertEqual(result.issue_url, "https://github.com/owner/repo/issues/42")
        self.assertIsNone(result.error)

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "gh")
        self.assertIn("--repo", cmd)
        self.assertIn(self.repo, cmd)
        self.assertIn("--label", cmd)
        self.assertIn("jules", cmd)
        self.assertEqual(kwargs["env"]["GH_TOKEN"], "github-token-value")

    @patch.dict("os.environ", {"GH_TOKEN": "gh-token-value"}, clear=True)
    @patch("subprocess.run")
    def test_dispatch_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: repository not found"
        )

        result = self.adapter.dispatch(self.sample_packet)

        self.assertFalse(result.success)
        self.assertIsNone(result.issue_url)
        self.assertEqual(result.error, "Error: repository not found")

    @patch.dict("os.environ", {"GITHUB_TOKEN": "github-token-value"}, clear=True)
    @patch("subprocess.run")
    def test_dispatch_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["gh"], timeout=30)

        result = self.adapter.dispatch(self.sample_packet)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "gh CLI timed out")

    @patch.dict("os.environ", {"GITHUB_TOKEN": "github-token-value"}, clear=True)
    @patch("subprocess.run")
    def test_dispatch_exception(self, mock_run):
        mock_run.side_effect = Exception("Unexpected error")

        result = self.adapter.dispatch(self.sample_packet)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Unexpected error")

if __name__ == "__main__":
    unittest.main()
