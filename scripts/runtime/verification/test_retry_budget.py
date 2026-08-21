"""Tests for retry budget logic (evaluator-to-executor retry loop)."""

import unittest

from scripts.runtime.verification.retry_budget import (
    has_criteria_evidence,
    has_evidence_references,
    should_retry,
)


class TestHasEvidenceReferences(unittest.TestCase):
    def test_file_path_in_findings_returns_true(self):
        integrity = {
            "findings": [
                {"severity": "high", "summary": "src/auth.py leaks credentials"},
            ],
        }
        self.assertTrue(has_evidence_references(integrity))

    def test_line_reference_in_findings_returns_true(self):
        integrity = {
            "findings": [
                {"severity": "medium", "summary": "bug at lib/common.zsh:42"},
            ],
        }
        self.assertTrue(has_evidence_references(integrity))

    def test_file_path_in_reasoning_returns_true(self):
        integrity = {
            "findings": [],
            "reasoning": "The change in scripts/runtime/bridge.py bypasses the verifier.",
        }
        self.assertTrue(has_evidence_references(integrity))

    def test_no_file_paths_returns_false(self):
        integrity = {
            "findings": [
                {"severity": "high", "summary": "the code feels wrong"},
            ],
            "reasoning": "Something is off but no specific file mentioned.",
        }
        self.assertFalse(has_evidence_references(integrity))

    def test_none_returns_false(self):
        self.assertFalse(has_evidence_references(None))

    def test_empty_findings_and_no_reasoning_returns_false(self):
        self.assertFalse(has_evidence_references({"findings": [], "reasoning": ""}))

    def test_affected_node_ids_returns_true_without_file_path(self):
        """A finding with non-empty affected_node_ids is actionable evidence
        even without an explicit file-path reference in its summary text."""
        integrity = {
            "findings": [
                {"summary": "intent drift detected", "affected_node_ids": ["node-x"]},
            ],
        }
        self.assertTrue(has_evidence_references(integrity))

    def test_empty_affected_node_ids_and_no_file_path_returns_false(self):
        """Empty affected_node_ids AND no file path in summary → no evidence."""
        integrity = {
            "findings": [
                {"summary": "intent drift detected", "affected_node_ids": []},
            ],
            "reasoning": "something feels off",
        }
        self.assertFalse(has_evidence_references(integrity))


class TestHasCriteriaEvidence(unittest.TestCase):
    def test_evidence_list_with_file_path_returns_true(self):
        criteria_findings = [
            {"evidence": ["src/foo.py has bug"], "reasoning": ""},
        ]
        self.assertTrue(has_criteria_evidence(criteria_findings))

    def test_reasoning_with_file_path_returns_true(self):
        criteria_findings = [
            {"evidence": [], "reasoning": "see scripts/bar.py for issue"},
        ]
        self.assertTrue(has_criteria_evidence(criteria_findings))

    def test_empty_list_returns_false(self):
        self.assertFalse(has_criteria_evidence([]))

    def test_none_returns_false(self):
        self.assertFalse(has_criteria_evidence(None))

    def test_no_file_paths_returns_false(self):
        criteria_findings = [
            {"evidence": ["the implementation is wrong"], "reasoning": "needs more work"},
        ]
        self.assertFalse(has_criteria_evidence(criteria_findings))


class TestShouldRetry(unittest.TestCase):
    def _base_job(self) -> dict:
        return {
            "attempt": 0,
            "max_attempts": 3,
        }

    def _base_project_yaml(self) -> dict:
        return {
            "execution_policy": {
                "retry_budget": 2,
            },
        }

    def _evidence_integrity(self) -> dict:
        return {
            "findings": [
                {"severity": "high", "summary": "src/foo.py has a bug"},
            ],
            "reasoning": "",
        }

    def test_non_pass_with_evidence_and_budget_and_room_returns_true(self):
        self.assertTrue(
            should_retry(
                verdict="needs-human-review",
                integrity=self._evidence_integrity(),
                job=self._base_job(),
                project_yaml=self._base_project_yaml(),
            )
        )

    def test_non_pass_without_evidence_returns_false(self):
        integrity = {"findings": [{"summary": "feels wrong"}], "reasoning": ""}
        self.assertFalse(
            should_retry(
                verdict="needs-human-review",
                integrity=integrity,
                job=self._base_job(),
                project_yaml=self._base_project_yaml(),
            )
        )

    def test_non_pass_with_budget_zero_returns_false(self):
        project_yaml = {"execution_policy": {"retry_budget": 0}}
        self.assertFalse(
            should_retry(
                verdict="needs-human-review",
                integrity=self._evidence_integrity(),
                job=self._base_job(),
                project_yaml=project_yaml,
            )
        )

    def test_non_pass_with_budget_missing_returns_false(self):
        project_yaml = {}
        self.assertFalse(
            should_retry(
                verdict="needs-human-review",
                integrity=self._evidence_integrity(),
                job=self._base_job(),
                project_yaml=project_yaml,
            )
        )

    def test_non_pass_attempt_at_max_returns_false(self):
        job = {"attempt": 3, "max_attempts": 3}
        self.assertFalse(
            should_retry(
                verdict="needs-human-review",
                integrity=self._evidence_integrity(),
                job=job,
                project_yaml=self._base_project_yaml(),
            )
        )

    def test_non_pass_attempt_above_max_returns_false(self):
        job = {"attempt": 5, "max_attempts": 3}
        self.assertFalse(
            should_retry(
                verdict="needs-human-review",
                integrity=self._evidence_integrity(),
                job=job,
                project_yaml=self._base_project_yaml(),
            )
        )

    def test_pass_verdict_returns_false(self):
        self.assertFalse(
            should_retry(
                verdict="pass",
                integrity=self._evidence_integrity(),
                job=self._base_job(),
                project_yaml=self._base_project_yaml(),
            )
        )

    def test_none_integrity_returns_false(self):
        self.assertFalse(
            should_retry(
                verdict="needs-human-review",
                integrity=None,
                job=self._base_job(),
                project_yaml=self._base_project_yaml(),
            )
        )

    def test_room_exactly_one_below_max_returns_true(self):
        """attempt=2 with budget=3 and max_attempts=3: one retry left."""
        job = {"attempt": 2, "max_attempts": 3}
        project_yaml = {"execution_policy": {"retry_budget": 3}}
        self.assertTrue(
            should_retry(
                verdict="fail",
                integrity=self._evidence_integrity(),
                job=job,
                project_yaml=project_yaml,
            )
        )

    def test_retry_budget_caps_below_max_attempts(self):
        """retry_budget=1 means only one retry even if max_attempts=3."""
        job = {"attempt": 1, "max_attempts": 3}
        project_yaml = {"execution_policy": {"retry_budget": 1}}
        self.assertFalse(
            should_retry(
                verdict="fail",
                integrity=self._evidence_integrity(),
                job=job,
                project_yaml=project_yaml,
            )
        )

    def test_retry_budget_allows_up_to_budget(self):
        """retry_budget=3 allows attempts 0, 1, 2 (three retries)."""
        project_yaml = {"execution_policy": {"retry_budget": 3}}
        for attempt in (0, 1, 2):
            job = {"attempt": attempt, "max_attempts": 5}
            self.assertTrue(
                should_retry(
                    verdict="fail",
                    integrity=self._evidence_integrity(),
                    job=job,
                    project_yaml=project_yaml,
                ),
                f"attempt={attempt} should retry with budget=3",
            )
        # attempt=3 exhausts the budget
        job = {"attempt": 3, "max_attempts": 5}
        self.assertFalse(
            should_retry(
                verdict="fail",
                integrity=self._evidence_integrity(),
                job=job,
                project_yaml=project_yaml,
            )
        )

    def test_criteria_evidence_with_integrity_none_returns_true(self):
        """Criteria lane has file paths, integrity lane absent → retry fires."""
        criteria_findings = [
            {
                "criterion_id": "test-1",
                "judgment": "judged_fail",
                "evidence": ["src/foo.py"],
                "reasoning": "",
            },
        ]
        self.assertTrue(
            should_retry(
                verdict="fail",
                integrity=None,
                job=self._base_job(),
                project_yaml=self._base_project_yaml(),
                criteria_findings=criteria_findings,
            )
        )

    def test_both_lanes_lack_evidence_returns_false(self):
        """Neither integrity nor criteria_findings have evidence → no retry."""
        integrity = {"findings": [{"summary": "feels wrong"}], "reasoning": ""}
        criteria_findings = [
            {"evidence": ["no concrete reference"], "reasoning": "vague concern"},
        ]
        self.assertFalse(
            should_retry(
                verdict="fail",
                integrity=integrity,
                job=self._base_job(),
                project_yaml=self._base_project_yaml(),
                criteria_findings=criteria_findings,
            )
        )

    def test_backward_compat_without_criteria_findings(self):
        """Calling without criteria_findings param works (integrity-only path)."""
        self.assertTrue(
            should_retry(
                verdict="needs-human-review",
                integrity=self._evidence_integrity(),
                job=self._base_job(),
                project_yaml=self._base_project_yaml(),
            )
        )

    def test_graph_recommendations_do_not_trigger_retry(self):
        """Cited graph_recommendations are not retry evidence."""
        integrity = {
            "findings": [],
            "reasoning": "Current node passes; graph should grow.",
            "graph_recommendations": [
                {
                    "action": "create_node",
                    "affected_node_ids": ["node-13"],
                    "rationale": "Missing continuation.",
                    "evidence": ["src/foo.py:12", "graphs/p/nodes/node-13.yaml"],
                }
            ],
        }
        self.assertFalse(
            should_retry(
                verdict="fail",
                integrity=integrity,
                job=self._base_job(),
                project_yaml=self._base_project_yaml(),
            )
        )


if __name__ == "__main__":
    unittest.main()
