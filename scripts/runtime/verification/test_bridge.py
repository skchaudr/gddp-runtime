"""Tests for the return-path verification bridge (E1)."""

import json
import os
import subprocess
import unittest
from unittest.mock import patch


def setUpModule():
    # The bridge fetches the key via `pass` when the env lacks it, which would
    # consume mocked subprocess side_effects; pin the env so tests are
    # deterministic regardless of the shell they run in.
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-real")

from scripts.runtime.verification import bridge


def _fake_paths_exist():
    """Patch the yaml/repo existence checks to pass."""
    return patch("scripts.runtime.verification.bridge.Path.exists", return_value=True)


class TestParseCliSummary(unittest.TestCase):
    def test_parses_final_json_after_pi_stream_noise(self):
        stdout = 'pi thinking...\n{"not": "closed"\nmore text\n{\n  "verdict": "pass",\n  "receipt_path": "/x.json"\n}'
        parsed = bridge._parse_cli_summary(stdout)
        self.assertEqual(parsed["verdict"], "pass")

    def test_returns_none_when_no_json(self):
        self.assertIsNone(bridge._parse_cli_summary("no json here"))


class TestVerifyJobReturn(unittest.TestCase):
    def test_missing_project_id_is_error_not_raise(self):
        res = bridge.verify_job_return(None, "some-node")
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("project_id", res["error"])

    def test_missing_node_yaml_is_error(self):
        res = bridge.verify_job_return("no-such-project", "no-such-node")
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("not found", res["error"])

    def test_success_returns_receipt_summary(self):
        summary = {
            "receipt_path": "/tmp/r.json",
            "verdict": "pass",
            "criteria_confidence": 0.9,
            "completeness_status": "complete",
            "required_next_action": "Proceed to accept_node (open evidence PR).",
        }
        proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary, indent=2), stderr=""
        )
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=proc
        ):
            res = bridge.verify_job_return("vault-doctor", "auth-node")
        self.assertEqual(res["verification_status"], "ok")
        self.assertEqual(res["verdict"], "pass")
        self.assertEqual(res["receipt_path"], "/tmp/r.json")

    def test_nonzero_exit_is_error(self):
        proc = subprocess.CompletedProcess(args=[], returncode=3, stdout="", stderr="boom")
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=proc
        ):
            res = bridge.verify_job_return("vault-doctor", "auth-node")
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("exited 3", res["error"])
        self.assertIn("boom", res["error"])

    def test_timeout_is_error(self):
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="cli", timeout=1),
        ):
            res = bridge.verify_job_return("vault-doctor", "auth-node")
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("timed out", res["error"])

    def test_transient_error_retried_once_then_succeeds(self):
        summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="blip")
        ok = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary), stderr=""
        )
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", side_effect=[fail, ok]
        ) as mock_run:
            res = bridge.verify_job_return("vault-doctor", "auth-node")
        self.assertEqual(res["verification_status"], "ok")
        self.assertEqual(mock_run.call_count, 2)

    def test_missing_paths_not_retried(self):
        with patch("scripts.runtime.verification.bridge.subprocess.run") as mock_run:
            res = bridge.verify_job_return("no-such-project", "no-such-node")
        self.assertEqual(res["verification_status"], "error")
        mock_run.assert_not_called()
        self.assertNotIn("retryable", res)

    def test_double_failure_reports_both_attempts(self):
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", side_effect=[fail, fail]
        ):
            res = bridge.verify_job_return("vault-doctor", "auth-node")
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("after 1 retry", res["error"])
        self.assertIn("first attempt", res["error"])

    def test_unparseable_stdout_is_error(self):
        proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="garbage", stderr="")
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=proc
        ):
            res = bridge.verify_job_return("vault-doctor", "auth-node")
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("no parseable", res["error"])


if __name__ == "__main__":
    unittest.main()
