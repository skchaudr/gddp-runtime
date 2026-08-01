"""Tests for the return-path verification bridge (E1)."""

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


def setUpModule():
    # The bridge fetches the key via `pass` when the env lacks it, which would
    # consume mocked subprocess side_effects; pin the env so tests are
    # deterministic regardless of the shell they run in.
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-real")

from scripts.runtime.verification import bridge
from scripts.runtime.verification.semantic.timeouts import (
    BRIDGE_TIMEOUT_OVERHEAD_SECONDS,
    PI_TIMEOUT_SECONDS,
    bridge_timeout_seconds,
)


def _fake_paths_exist():
    """Patch the yaml/repo existence checks to pass."""
    return patch("scripts.runtime.verification.bridge.Path.exists", return_value=True)


@contextmanager
def _pinned_subject():
    """Make bridge tests evaluate a pinned subject without creating a real worktree."""
    with _fake_paths_exist(), patch(
        "scripts.runtime.verification.bridge._create_worktree",
        return_value=Path("/tmp/fake-wt"),
    ), patch("scripts.runtime.verification.bridge._remove_worktree"):
        yield


def _verify_return(project_id="vault-doctor", node_id="auth-node", **kwargs):
    kwargs.setdefault("merge_commit_sha", "abc123")
    return bridge.verify_job_return(project_id, node_id, **kwargs)


class TestParseCliSummary(unittest.TestCase):
    def test_parses_final_json_after_pi_stream_noise(self):
        stdout = 'pi thinking...\n{"not": "closed"\nmore text\n{\n  "verdict": "pass",\n  "receipt_path": "/x.json"\n}'
        parsed = bridge._parse_cli_summary(stdout)
        self.assertEqual(parsed["verdict"], "pass")

    def test_returns_none_when_no_json(self):
        self.assertIsNone(bridge._parse_cli_summary("no json here"))


class TestTimeoutBudget(unittest.TestCase):
    def test_outer_timeout_covers_two_pi_lanes_and_bounded_overhead(self):
        minimum = 2 * PI_TIMEOUT_SECONDS + BRIDGE_TIMEOUT_OVERHEAD_SECONDS
        self.assertEqual(bridge_timeout_seconds(1), minimum)
        self.assertGreaterEqual(bridge.VERIFY_TIMEOUT_SECONDS, minimum)


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
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=proc
        ):
            res = _verify_return()
        self.assertEqual(res["verification_status"], "ok")
        self.assertEqual(res["verdict"], "pass")
        self.assertEqual(res["receipt_path"], "/tmp/r.json")

    def test_nonzero_exit_is_error(self):
        proc = subprocess.CompletedProcess(args=[], returncode=3, stdout="", stderr="boom")
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=proc
        ):
            res = _verify_return()
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("exited 3", res["error"])
        self.assertIn("boom", res["error"])

    def test_timeout_is_error(self):
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="cli", timeout=1),
        ):
            res = _verify_return()
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("timed out", res["error"])

    def test_transient_error_retried_once_then_succeeds(self):
        summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="blip")
        ok = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary), stderr=""
        )
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", side_effect=[fail, ok]
        ) as mock_run:
            res = _verify_return()
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
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", side_effect=[fail, fail]
        ):
            res = _verify_return()
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("after 1 retry", res["error"])
        self.assertIn("first attempt", res["error"])

    def test_unparseable_stdout_is_error(self):
        proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="garbage", stderr="")
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=proc
        ):
            res = _verify_return()
        self.assertEqual(res["verification_status"], "error")
        self.assertIn("no parseable", res["error"])


class TestCredentialFetch(unittest.TestCase):
    def setUp(self):
        # setUpModule pins the key so most tests skip the fetch; remove it so
        # the credential-fetch path actually executes in these tests.
        self._saved_key = os.environ.pop("DEEPSEEK_API_KEY", None)

    def tearDown(self):
        if self._saved_key is not None:
            os.environ["DEEPSEEK_API_KEY"] = self._saved_key
        os.environ.pop("GDDP_DEEPSEEK_KEY_CMD", None)
        os.environ.pop("GDDP_VERIFY_SEMANTIC_ARGS", None)

    def test_custom_key_command_is_used(self):
        os.environ["GDDP_DEEPSEEK_KEY_CMD"] = "echo test-key-123"
        summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
        cred = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="test-key-123\n", stderr=""
        )
        cli = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary), stderr=""
        )
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.subprocess.run",
            side_effect=[cred, cli],
        ) as mock_run:
            res = _verify_return()
        self.assertEqual(res["verification_status"], "ok")
        # The first subprocess.run call is the credential fetch; it must use
        # the shlex-split custom command.
        first_call = mock_run.call_args_list[0]
        self.assertEqual(first_call.args[0], ["echo", "test-key-123"])

    def test_absent_binary_does_not_crash(self):
        # GDDP_DEEPSEEK_KEY_CMD unset -> default "pass show api/deepseek";
        # mock shutil.which so `pass` is reported absent.
        os.environ.pop("GDDP_DEEPSEEK_KEY_CMD", None)
        summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
        cli = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary), stderr=""
        )
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.shutil.which", return_value=None
        ), patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=cli
        ) as mock_run:
            res = _verify_return()
        self.assertEqual(res["verification_status"], "ok")
        # The credential fetch must not have invoked subprocess.run; only the
        # verifier CLI call should have occurred.
        self.assertEqual(mock_run.call_count, 1)

    def test_chatgpt_route_does_not_fetch_deepseek_key(self):
        os.environ["GDDP_VERIFY_SEMANTIC_ARGS"] = (
            "--semantic-mode live --semantic-harness pi "
            "--semantic-provider chatgpt --semantic-pi-model gpt-5.4"
        )
        summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
        cli = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary), stderr=""
        )
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=cli
        ) as mock_run:
            res = _verify_return()

        self.assertEqual(res["verification_status"], "ok")
        self.assertEqual(mock_run.call_count, 1)


class TestIntegrityFlag(unittest.TestCase):
    """The bridge must default --integrity on and respect GDDP_INTEGRITY_MODE."""

    def test_bridge_defaults_integrity_on(self):
        """The CLI command includes --integrity on by default."""
        os.environ.pop("GDDP_INTEGRITY_MODE", None)
        summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
        proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary), stderr=""
        )
        with _pinned_subject(), patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=proc
        ) as mock_run:
            _verify_return()

        cmd = mock_run.call_args[0][0]
        # Find --integrity in the command list
        idx = cmd.index("--integrity")
        self.assertEqual(cmd[idx + 1], "on")

    def test_bridge_respects_integrity_off(self):
        """GDDP_INTEGRITY_MODE=off passes --integrity off to the CLI."""
        os.environ["GDDP_INTEGRITY_MODE"] = "off"
        try:
            summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
            proc = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(summary), stderr=""
            )
            with _pinned_subject(), patch(
                "scripts.runtime.verification.bridge.subprocess.run", return_value=proc
            ) as mock_run:
                _verify_return()

            cmd = mock_run.call_args[0][0]
            idx = cmd.index("--integrity")
            self.assertEqual(cmd[idx + 1], "off")
        finally:
            os.environ.pop("GDDP_INTEGRITY_MODE", None)


class TestProvenancePassthrough(unittest.TestCase):
    """Phase 1: merge_commit_sha triggers worktree + provenance CLI args."""

    def test_missing_merge_sha_fails_closed_without_cli(self):
        """An unpinned subject must not produce a valid-looking receipt."""
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge._run_cli"
        ) as mock_cli, patch(
            "scripts.runtime.verification.bridge._create_worktree"
        ) as mock_wt:
            res = bridge.verify_job_return("vault-doctor", "auth-node")
        self.assertEqual(res["verification_status"], "subject_mismatch")
        self.assertIn("merge_commit_sha", res["error"])
        mock_wt.assert_not_called()
        mock_cli.assert_not_called()

    def test_merge_sha_creates_worktree_and_passes_args(self):
        """With merge_commit_sha, worktree is created and CLI gets --merge-commit-sha."""
        summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
        cli_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary), stderr=""
        )
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge._create_worktree", return_value=Path("/tmp/fake-wt")
        ), patch(
            "scripts.runtime.verification.bridge._remove_worktree"
        ) as mock_remove, patch(
            "scripts.runtime.verification.bridge.subprocess.run", return_value=cli_proc
        ) as mock_run:
            res = bridge.verify_job_return(
                "vault-doctor", "auth-node",
                merge_commit_sha="abc123",
                pr_ref="42",
                job_id="job_001",
                attempt=0,
            )
        self.assertEqual(res["verification_status"], "ok")
        cmd = mock_run.call_args[0][0]
        self.assertIn("--merge-commit-sha", cmd)
        idx = cmd.index("--merge-commit-sha")
        self.assertEqual(cmd[idx + 1], "abc123")
        self.assertIn("--pr-ref", cmd)
        self.assertIn("--job-id", cmd)
        self.assertIn("--attempt", cmd)
        self.assertEqual(cmd[cmd.index("--attempt") + 1], "0")
        mock_remove.assert_called_once_with(
            bridge._repos_root() / "vault-doctor", Path("/tmp/fake-wt")
        )

    def test_worktree_failure_returns_subject_mismatch(self):
        """If worktree creation fails, return subject_mismatch, don't evaluate."""
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge._create_worktree", return_value=None
        ), patch(
            "scripts.runtime.verification.bridge.subprocess.run"
        ) as mock_run:
            res = bridge.verify_job_return(
                "vault-doctor", "auth-node",
                merge_commit_sha="abc123",
            )
        self.assertEqual(res["verification_status"], "subject_mismatch")
        self.assertIn("abc123", res["error"])
        mock_run.assert_not_called()


class TestWorktreeLifecycle(unittest.TestCase):
    def test_create_and_remove_clears_worktree_registration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "--allow-empty", "-m", "initial", "-q",
                ],
                cwd=repo,
                check=True,
            )
            commit_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            worktree = bridge._create_worktree(repo, commit_sha)
            self.assertIsNotNone(worktree)
            self.assertTrue(worktree.exists())

            bridge._remove_worktree(repo, worktree)

            self.assertFalse(worktree.exists())
            registered = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.assertNotIn(str(worktree), registered)

    def test_create_worktree_fetches_origin_before_add(self):
        """_create_worktree must fetch from origin so the merge commit is local."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "--allow-empty", "-m", "initial", "-q"],
                cwd=repo, check=True,
            )
            commit_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo,
                capture_output=True, text=True, check=True,
            ).stdout.strip()

            calls = []
            original_run = subprocess.run

            def tracking_run(cmd, *args, **kwargs):
                calls.append(cmd)
                return original_run(cmd, *args, **kwargs)

            with patch("scripts.runtime.verification.bridge.subprocess.run", side_effect=tracking_run):
                bridge._create_worktree(repo, commit_sha)

            git_commands = [" ".join(c[:3]) for c in calls if c[0] == "git"]
            self.assertIn("git fetch origin", git_commands)
            self.assertIn("git worktree add", git_commands)
            fetch_idx = next(i for i, c in enumerate(git_commands) if "fetch" in c)
            wt_idx = next(i for i, c in enumerate(git_commands) if "worktree" in c)
            self.assertLess(fetch_idx, wt_idx, "fetch must happen before worktree add")


if __name__ == "__main__":
    unittest.main()


class TestBasePassthrough(unittest.TestCase):
    """expected_base_commit_sha flows from the session row to the CLI as --base."""

    def test_base_forwarded_to_cli(self):
        summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
        cli_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary), stderr=""
        )
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge._create_worktree",
            return_value=Path("/tmp/fake-wt"),
        ), patch(
            "scripts.runtime.verification.bridge._remove_worktree"
        ), patch(
            "scripts.runtime.verification.bridge.subprocess.run",
            return_value=cli_proc,
        ) as mock_run:
            res = bridge.verify_job_return(
                "vault-doctor", "auth-node",
                merge_commit_sha="abc123",
                expected_base_commit_sha="b" * 40,
                job_id="job_001",
                attempt=0,
            )
        self.assertEqual(res["verification_status"], "ok")
        cmd = mock_run.call_args[0][0]
        self.assertIn("--base", cmd)
        self.assertEqual(cmd[cmd.index("--base") + 1], "b" * 40)

    def test_no_base_omits_flag(self):
        summary = {"receipt_path": "/tmp/r.json", "verdict": "pass"}
        cli_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(summary), stderr=""
        )
        with _fake_paths_exist(), patch(
            "scripts.runtime.verification.bridge._create_worktree",
            return_value=Path("/tmp/fake-wt"),
        ), patch(
            "scripts.runtime.verification.bridge._remove_worktree"
        ), patch(
            "scripts.runtime.verification.bridge.subprocess.run",
            return_value=cli_proc,
        ) as mock_run:
            bridge.verify_job_return(
                "vault-doctor", "auth-node",
                merge_commit_sha="abc123",
                job_id="job_001",
                attempt=0,
            )
        cmd = mock_run.call_args[0][0]
        self.assertNotIn("--base", cmd)
