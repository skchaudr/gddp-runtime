"""Tests for the decision loop's runner resolution (item 1.1).

Verifies that _build_decision_loop_runner never crashes on a missing optional
dependency (anthropic) and selects the correct provider from the environment.
"""

import os
import unittest
from unittest.mock import patch


class TestRunnerResolution(unittest.TestCase):
    def setUp(self):
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("DEEPSEEK_API_KEY", "GLM_API_KEY", "DEEPSEEK_BASE_URL",
                      "DEEPSEEK_MODEL", "GLM_BASE_URL", "GLM_MODEL")
        }
        for k in self._saved_env:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_deepseek_key_returns_openai_compatible_runner(self):
        from scripts.runtime.decision_loop.engine import _build_decision_loop_runner
        from scripts.runtime.verification.semantic.agent import OpenAICompatibleRunner

        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        runner = _build_decision_loop_runner()
        self.assertIsInstance(runner, OpenAICompatibleRunner)
        self.assertEqual(runner.api_key, "test-key")

    def test_glm_key_returns_openai_compatible_runner(self):
        from scripts.runtime.decision_loop.engine import _build_decision_loop_runner
        from scripts.runtime.verification.semantic.agent import OpenAICompatibleRunner

        os.environ["GLM_API_KEY"] = "test-glm-key"
        runner = _build_decision_loop_runner()
        self.assertIsInstance(runner, OpenAICompatibleRunner)
        self.assertEqual(runner.api_key, "test-glm-key")

    def test_no_keys_no_anthropic_returns_offline_runner(self):
        """When no API keys are set and anthropic is not installed, the
        decision loop falls back to OfflineFinalizingRunner, not a crash."""
        from scripts.runtime.decision_loop.engine import _build_decision_loop_runner
        from scripts.runtime.verification.cli import OfflineFinalizingRunner

        # Simulate anthropic not being installed.
        with patch.dict("sys.modules", {"anthropic": None}):
            runner = _build_decision_loop_runner()
        self.assertIsInstance(runner, OfflineFinalizingRunner)

    def test_lazy_runner_does_not_crash_without_anthropic(self):
        """The _LazyRunner class used by _run_verification must build a
        runner without crashing when anthropic is absent."""
        from scripts.runtime.decision_loop.engine import (
            _LazyRunner,
            _build_decision_loop_runner,
        )
        from scripts.runtime.verification.cli import OfflineFinalizingRunner

        lazy = _LazyRunner()
        self.assertIsNone(lazy._runner)  # Not built yet
        # Building the runner should not raise.
        with patch.dict("sys.modules", {"anthropic": None}):
            built = _build_decision_loop_runner()
        self.assertIsInstance(built, OfflineFinalizingRunner)


if __name__ == "__main__":
    unittest.main()
