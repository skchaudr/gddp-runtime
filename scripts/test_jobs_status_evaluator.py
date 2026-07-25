"""Evaluator rendering coverage for the jobs-status backend."""

from scripts.jobs_status import print_evaluation


def test_evaluation_summary_uses_coverage_ratings_and_lane_errors(capsys) -> None:
    print_evaluation({
        "verdict": "needs-human-review",
        "criteria_verdict": "pass",
        "criteria_confidence": 0.9,
        "integrity": {"verdict": "unknown", "confidence": 0.0, "findings": []},
        "context_coverage": {
            "criteria": {"rating": "medium"},
            "integrity": {"rating": "low"},
            "overall": "low",
        },
        "lane_status": {"criteria": "completed", "integrity": "timed-out"},
        "harness_error": {"criteria": None, "integrity": "pi timed out after 1200s"},
        "evaluated_tree_sha": "legacy-tree",
        "evaluated_commit_sha": "evaluated-commit",
        "merge_commit_sha": "different-merge-commit",
    })

    output = capsys.readouterr().out
    assert "coverage: criteria=medium  integrity=low  overall=low" in output
    assert "lane status: criteria=completed  integrity=timed-out" in output
    assert "harness error: integrity=pi timed out after 1200s" in output
    assert "commit=evaluated-commit  merge=different-merge-commit  (mismatch)" in output
