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
            "title": "Auth node",
            "goal": "Fix authentication",
            "why": "Protect users",
            "required_artifacts": json.dumps(["decision.md", "patch.diff"]),
            "previous_findings": None,
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
                "merge_commit_sha": "abc123retrybase",
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

    def test_redispatch_allocates_attempt_and_persists_packet_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_project_yaml(tmpdir)
            with (
                patch("scripts.runtime.return_router._load_job", return_value=self._base_job()),
                patch("scripts.runtime.return_router.write_result"),
                patch("scripts.runtime.return_router._mark_job_awaiting_review") as mock_mark,
                patch("scripts.runtime.return_router.verify_job_return", return_value=self._fail_verdict_with_evidence()),
                patch("scripts.runtime.return_router._config_root", return_value=Path(tmpdir)),
                patch("scripts.runtime.heartbeat.dispatcher.dispatch") as mock_dispatch,
                patch("scripts.runtime.return_router._connect") as mock_connect,
                patch("scripts.runtime.return_router.allocate_retry_attempt") as mock_allocate,
                patch("scripts.runtime.return_router.finalize_executor_session_dispatch") as mock_finalize,
                patch("scripts.runtime.return_router.mark_job_running") as mock_running,
            ):
                mock_con = MagicMock()
                mock_connect.return_value = mock_con

                def allocate(con, job, **kwargs):
                    updated = dict(job)
                    updated["attempt"] = 1
                    updated["previous_findings"] = json.dumps(
                        kwargs["previous_findings"]
                    )
                    return updated, "ses_retry"

                mock_allocate.side_effect = allocate
                mock_dispatch.return_value = DispatchResult(
                    success=True,
                    issue_url="https://github.com/skchaudr/vault-doctor/issues/99",
                )

                with patch("builtins.open", mock_open(read_data=json.dumps(self._base_payload()))):
                    res = handle_merged_pr(self._base_event())

                self.assertEqual(res["status"], "redispatched")
                self.assertTrue(res["dispatch_success"])
                allocated_findings = mock_allocate.call_args.kwargs[
                    "previous_findings"
                ]
                self.assertEqual(allocated_findings["verdict"], "fail")
                self.assertEqual(
                    mock_allocate.call_args.kwargs["expected_base_commit_sha"],
                    "abc123retrybase",
                )
                dispatched_job = mock_dispatch.call_args.args[0]
                self.assertEqual(dispatched_job["attempt"], 1)
                from scripts.runtime.heartbeat.dispatcher import _build_node_packet

                packet = _build_node_packet(dispatched_job)
                self.assertEqual(packet.execution_attempt_id, "job_123:attempt:1")
                self.assertEqual(
                    packet.required_artifacts,
                    ("decision.md", "patch.diff"),
                )
                self.assertEqual(packet.previous_findings["verdict"], "fail")
                mock_finalize.assert_called_once_with(
                    mock_con,
                    "ses_retry",
                    state="mediated",
                    session_id="https://github.com/skchaudr/vault-doctor/issues/99",
                )
                mock_running.assert_called_once_with(mock_con, "job_123")
                mock_mark.assert_not_called()

    def test_operator_retry_injects_human_fix_list_and_uses_evaluated_commit(self):
        from scripts.runtime import return_router

        job = dict(
            self._base_job(),
            status="awaiting_review",
            queue_state="awaiting_review",
        )
        verification = self._fail_verdict_with_evidence()
        verification["evaluated_commit_sha"] = "result123"
        with (
            patch.object(return_router, "_load_job", return_value=job),
            patch.object(
                return_router,
                "_latest_job_verification",
                return_value=("res_latest", verification, "result123"),
            ),
            patch.object(
                return_router,
                "_redispatch_with_findings",
                return_value={"status": "redispatched", "dispatch_success": True},
            ) as redispatch,
        ):
            result = return_router.retry_reviewed_job(
                "job_123", "new clean Khoj user is ready"
            )

        self.assertEqual(result["status"], "redispatched")
        args = redispatch.call_args.args
        self.assertEqual(args[1]["_retry_base_commit_sha"], "result123")
        self.assertEqual(
            args[3]["human_fix_list"]["reason"],
            "new clean Khoj user is ready",
        )

    def test_operator_retry_requires_awaiting_review_job(self):
        from scripts.runtime import return_router

        with patch.object(
            return_router, "_load_job", return_value=self._base_job()
        ):
            result = return_router.retry_reviewed_job("job_123", "try again")

        self.assertEqual(result["status"], "retry_rejected")
        self.assertEqual(result["reason"], "job_not_awaiting_review")

    def test_retry_preflight_failure_does_not_consume_attempt(self):
        from scripts.runtime import return_router

        job = self._base_job()
        job["_retry_base_commit_sha"] = "result123"
        with (
            patch(
                "scripts.runtime.heartbeat.dispatcher.executor_preflight_error",
                return_value="pi_rpc spool root is required",
            ),
            patch.object(return_router, "allocate_retry_attempt") as allocate,
            patch.object(return_router, "_mark_job_awaiting_review") as mark_review,
        ):
            result = return_router._redispatch_with_findings(
                "job_123",
                job,
                "auth-node",
                self._fail_verdict_with_evidence(),
                "res_123",
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertFalse(result["dispatch_attempted"])
        self.assertEqual(result["dispatch_error"], "pi_rpc spool root is required")
        allocate.assert_not_called()
        mark_review.assert_called_once_with("job_123")

    def test_retry_dispatch_failure_keeps_allocated_attempt_visible(self):
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
                patch("scripts.runtime.return_router.allocate_retry_attempt") as mock_allocate,
                patch("scripts.runtime.return_router.finalize_executor_session_dispatch") as mock_finalize,
                patch("scripts.runtime.return_router.mark_job_running"),
            ):
                mock_con = MagicMock()
                mock_connect.return_value = mock_con
                updated = self._base_job()
                updated["attempt"] = 1
                mock_allocate.return_value = (updated, "ses_retry_failed")

                with patch("builtins.open", mock_open(read_data=json.dumps(self._base_payload()))):
                    res = handle_merged_pr(self._base_event())

                self.assertEqual(res["status"], "needs_review")
                self.assertTrue(res["dispatch_attempted"])
                self.assertFalse(res["dispatch_success"])
                mock_finalize.assert_called_once_with(
                    mock_con,
                    "ses_retry_failed",
                    state="dispatch_failed",
                    error="simulated dispatch failure",
                )
                mock_mark.assert_called_once_with("job_123")

    def test_redispatch_cas_loss_cancels_late_remote_and_preserves_job_state(self):
        from scripts.runtime import return_router
        from adapters.executor_protocol import SessionRef

        mock_con = MagicMock()
        job = self._base_job()
        retried_job = dict(job, attempt=1)
        verification = self._fail_verdict_with_evidence()
        session_ref = SessionRef("jules_api", "late-return-session")
        with (
            patch.object(return_router, "_connect", return_value=mock_con),
            patch.object(
                return_router,
                "allocate_retry_attempt",
                return_value=(retried_job, "ses_cancelled_retry"),
            ),
            patch(
                "scripts.runtime.heartbeat.dispatcher.dispatch",
                return_value=DispatchResult(success=True, session_ref=session_ref),
            ),
            patch.object(
                return_router,
                "finalize_executor_session_dispatch",
                return_value=False,
            ),
            patch(
                "scripts.runtime.heartbeat.dispatcher.cancel_remote_session",
                return_value=(
                    False,
                    "late session cancellation was not accepted; remote may continue",
                ),
            ) as mock_cancel,
            patch.object(return_router, "mark_job_running") as mock_running,
        ):
            result = return_router._redispatch_with_findings(
                "job_123",
                job,
                "auth-node",
                verification,
                "res_123456",
            )

        self.assertEqual(result["status"], "dispatch_superseded")
        self.assertFalse(result["reservation_finalized"])
        mock_running.assert_not_called()
        mock_cancel.assert_called_once_with(session_ref, job["repo"])

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
                patch("scripts.runtime.return_router.allocate_retry_attempt") as mock_allocate,
                patch("scripts.runtime.return_router.finalize_executor_session_dispatch"),
                patch("scripts.runtime.return_router.mark_job_running"),
            ):
                mock_con = MagicMock()
                mock_connect.return_value = mock_con
                updated = self._base_job()
                updated["attempt"] = 1
                mock_allocate.return_value = (updated, "ses_criteria_retry")

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
