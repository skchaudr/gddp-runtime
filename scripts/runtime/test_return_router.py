"""
test_return_router.py — Tests for review-receipt routing on merged PRs.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

# Add the parent directory to sys.path to allow importing from the current package
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.runtime.heartbeat.dispatcher import DispatchResult
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

    @patch("scripts.runtime.return_router.verify_job_return")
    @patch("scripts.runtime.return_router._mark_job_awaiting_review")
    @patch("scripts.runtime.return_router.write_result")
    @patch("scripts.runtime.return_router._load_job")
    def test_handle_merged_pr_success(
        self, mock_load_job, mock_write, mock_mark_review, mock_verify
    ):
        event = {"raw_payload_path": "payload.json", "event_id": "evt_123456"}
        payload = {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 12,
                "body": "node: auth-node\njob: job_123",
                "merged_at": "2024-03-20T10:00:00Z",
                "html_url": "https://github.com/skchaudr/vault-doctor/pull/12",
                "merge_commit_sha": "abc123",
            },
        }
        mock_load_job.return_value = {
            "job_id": "job_123",
            "repo": "skchaudr/vault-doctor",
            "node_id": "auth-node",
            "executor": "jules",
            "project_id": "vault-doctor",
            "attempt": 0,
        }
        verification = {
            "verification_status": "ok",
            "receipt_path": "/tmp/receipt.json",
            "verdict": "pass",
            "criteria_confidence": 0.9,
            "required_next_action": "Proceed to accept_node (open evidence PR).",
        }
        mock_verify.return_value = verification

        with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
            res = handle_merged_pr(event)

        self.assertEqual(
            res,
            {
                "status": "needs_review",
                "result_id": "res_123456",
                "job_id": "job_123",
                "node_id": "auth-node",
                "verification": verification,
            },
        )
        mock_verify.assert_called_once_with(
            "vault-doctor", "auth-node",
            merge_commit_sha="abc123", pr_ref="12", job_id="job_123", attempt=0,
        )
        mock_write.assert_called_once_with(
            result_id="res_123456",
            job_id="job_123",
            executor="jules",
            outcome="success",
            status="needs_review",
            received_at="2024-03-20T10:00:00Z",
            acceptance_check=verification,
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
        )
        mock_mark_review.assert_called_once_with("job_123")

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


class TestReturnRouterRetry(unittest.TestCase):
    """Tests for the retry loop (redispatch vs awaiting_review) in handle_merged_pr."""

    def _base_job(self) -> dict:
        return {
            "job_id": "job_123",
            "repo": "skchaudr/vault-doctor",
            "node_id": "auth-node",
            "executor": "jules",
            "project_id": "vault-doctor",
            "attempt": 0,
            "max_attempts": 3,
            "constraints": "[]",
            "acceptance_criteria": "[]",
        }

    def _base_event(self) -> dict:
        return {"raw_payload_path": "payload.json", "event_id": "evt_123456"}

    def _base_payload(self) -> dict:
        return {
            "repository": {"full_name": "skchaudr/vault-doctor"},
            "pull_request": {
                "number": 12,
                "body": "node: auth-node\njob: job_123",
                "merged_at": "2024-03-20T10:00:00Z",
                "html_url": "https://github.com/skchaudr/vault-doctor/pull/12",
            },
        }

    def _fail_verdict_with_evidence(self) -> dict:
        return {
            "verification_status": "ok",
            "verdict": "fail",
            "integrity": {
                "findings": [
                    {"summary": "src/foo.py:42 has a bug", "affected_node_ids": []}
                ],
                "reasoning": "",
            },
        }

    @staticmethod
    def _make_project_yaml(tmpdir, project_id="vault-doctor", content=None):
        graphs_dir = Path(tmpdir) / "graphs" / project_id
        graphs_dir.mkdir(parents=True, exist_ok=True)
        if content is None:
            content = "execution_policy:\n  retry_budget: 3\n"
        (graphs_dir / "project.yaml").write_text(content)

    def test_redispatch_on_non_pass_verdict_with_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_project_yaml(tmpdir)
            with (
                patch("scripts.runtime.return_router._load_job", return_value=self._base_job()),
                patch("scripts.runtime.return_router.write_result"),
                patch("scripts.runtime.return_router._mark_job_awaiting_review") as mock_mark,
                patch("scripts.runtime.return_router.verify_job_return", return_value=self._fail_verdict_with_evidence()),
                patch("scripts.runtime.return_router._config_root", return_value=Path(tmpdir)),
                patch("scripts.runtime.heartbeat.dispatcher.dispatch", return_value=DispatchResult(
                    success=True, issue_url="https://github.com/skchaudr/vault-doctor/issues/99"
                )),
                patch("scripts.runtime.return_router._connect") as mock_connect,
            ):
                mock_con = MagicMock()
                mock_connect.return_value = mock_con

                with patch("builtins.open", mock_open(read_data=json.dumps(self._base_payload()))):
                    res = handle_merged_pr(self._base_event())

                self.assertEqual(res["status"], "redispatched")
                self.assertTrue(res["dispatch_success"])
                # Attempt was incremented and status/queue_state set to running after dispatch success
                self.assertEqual(mock_con.execute.call_count, 2)
                mock_con.execute.assert_any_call(
                    """UPDATE jobs
                  SET attempt = attempt + 1,
                      status = 'running',
                      queue_state = 'running'
                WHERE job_id = ?""",
                    ("job_123",),
                )
                mock_con.execute.assert_any_call(
                    "UPDATE queue_records SET queue = 'running' WHERE job_id = ?",
                    ("job_123",),
                )
                mock_con.commit.assert_called_once()
                # Did NOT route to awaiting_review
                mock_mark.assert_not_called()

    def test_dispatch_failure_does_not_increment_attempt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_project_yaml(tmpdir)
            with (
                patch("scripts.runtime.return_router._load_job", return_value=self._base_job()),
                patch("scripts.runtime.return_router.write_result"),
                patch("scripts.runtime.return_router._mark_job_awaiting_review") as mock_mark,
                patch("scripts.runtime.return_router.verify_job_return", return_value=self._fail_verdict_with_evidence()),
                patch("scripts.runtime.return_router._config_root", return_value=Path(tmpdir)),
                patch("scripts.runtime.heartbeat.dispatcher.dispatch", return_value=DispatchResult(
                    success=False, error="simulated dispatch failure"
                )),
                patch("scripts.runtime.return_router._connect") as mock_connect,
            ):
                with patch("builtins.open", mock_open(read_data=json.dumps(self._base_payload()))):
                    res = handle_merged_pr(self._base_event())

                self.assertEqual(res["status"], "needs_review")
                self.assertTrue(res["dispatch_attempted"])
                self.assertFalse(res["dispatch_success"])
                # Attempt was NOT incremented (no DB write for attempt)
                mock_connect.assert_not_called()
                # Fell back to awaiting_review
                mock_mark.assert_called_once_with("job_123")

    def test_attempt_at_cap_routes_to_awaiting_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_project_yaml(tmpdir)
            job = self._base_job()
            job["attempt"] = 3
            job["max_attempts"] = 3
            with (
                patch("scripts.runtime.return_router._load_job", return_value=job),
                patch("scripts.runtime.return_router.write_result"),
                patch("scripts.runtime.return_router._mark_job_awaiting_review") as mock_mark,
                patch("scripts.runtime.return_router.verify_job_return", return_value=self._fail_verdict_with_evidence()),
                patch("scripts.runtime.return_router._config_root", return_value=Path(tmpdir)),
                patch("scripts.runtime.heartbeat.dispatcher.dispatch") as mock_dispatch,
                patch("scripts.runtime.return_router._connect") as mock_connect,
            ):
                with patch("builtins.open", mock_open(read_data=json.dumps(self._base_payload()))):
                    res = handle_merged_pr(self._base_event())

                self.assertEqual(res["status"], "needs_review")
                # Not redispatched
                mock_dispatch.assert_not_called()
                mock_connect.assert_not_called()
                mock_mark.assert_called_once_with("job_123")

    def test_criteria_findings_passed_to_should_retry(self):
        """Retry fires based on criteria evidence alone (integrity lane absent)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_project_yaml(tmpdir)
            criteria_verdict = {
                "verification_status": "ok",
                "verdict": "fail",
                "criteria_findings": [
                    {
                        "criterion_id": "test-1",
                        "judgment": "judged_fail",
                        "evidence": ["src/foo.py"],
                        "reasoning": "",
                    },
                ],
            }
            with (
                patch("scripts.runtime.return_router._load_job", return_value=self._base_job()),
                patch("scripts.runtime.return_router.write_result"),
                patch("scripts.runtime.return_router._mark_job_awaiting_review"),
                patch("scripts.runtime.return_router.verify_job_return", return_value=criteria_verdict),
                patch("scripts.runtime.return_router._config_root", return_value=Path(tmpdir)),
                patch("scripts.runtime.heartbeat.dispatcher.dispatch", return_value=DispatchResult(
                    success=True, issue_url="https://github.com/skchaudr/vault-doctor/issues/100"
                )),
                patch("scripts.runtime.return_router._connect") as mock_connect,
            ):
                mock_con = MagicMock()
                mock_connect.return_value = mock_con

                with patch("builtins.open", mock_open(read_data=json.dumps(self._base_payload()))):
                    res = handle_merged_pr(self._base_event())

                self.assertEqual(res["status"], "redispatched")
                self.assertTrue(res["dispatch_success"])


class TestReturnRouterRepoValidation(unittest.TestCase):
    """Tests for configurable allowed_repos and fallback list."""

    def test_configurable_allowed_repos_from_project_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            graphs_dir = Path(tmpdir) / "graphs" / "vault-doctor"
            graphs_dir.mkdir(parents=True)
            (graphs_dir / "project.yaml").write_text(
                "execution_policy:\n  allowed_repos:\n    - skchaudr/some-other-repo\n"
            )
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
            job = {
                "job_id": "job_123",
                "repo": "skchaudr/vault-doctor",
                "node_id": "auth-node",
                "executor": "jules",
                "project_id": "vault-doctor",
            }
            with (
                patch("scripts.runtime.return_router._load_job", return_value=job),
                patch("scripts.runtime.return_router.write_result"),
                patch("scripts.runtime.return_router.verify_job_return", return_value={
                    "verification_status": "ok",
                    "verdict": "pass",
                }),
                patch("scripts.runtime.return_router._config_root", return_value=Path(tmpdir)),
            ):
                with patch("builtins.open", mock_open(read_data=json.dumps(payload))):
                    res = handle_merged_pr(event)

                self.assertEqual(
                    res,
                    {"status": "rejected", "reason": "repo_not_allowed_by_project"},
                )

    def test_gddp_runtime_accepted_via_fallback(self):
        self.assertTrue(validate_repo("skchaudr/gddp-runtime"))


if __name__ == "__main__":
    unittest.main()
