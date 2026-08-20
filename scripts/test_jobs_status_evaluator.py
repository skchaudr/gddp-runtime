"""Evaluator rendering coverage for the jobs-status backend."""

import json
import sqlite3
from argparse import Namespace

from scripts import jobs_status
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
        "evaluation_timing": {
            "started_at": "2026-08-01T00:00:00Z",
            "finished_at": "2026-08-01T00:20:01Z",
            "wall_s": 1201.0,
            "criteria": {"status": "completed", "elapsed_s": 1.2, "tool_calls": 4},
            "integrity": {"status": "timed-out", "elapsed_s": 1200.0, "tool_calls": 1},
        },
        "evaluated_tree_sha": "legacy-tree",
        "evaluated_commit_sha": "evaluated-commit",
        "merge_commit_sha": "different-merge-commit",
    })

    output = capsys.readouterr().out
    assert "coverage: criteria=medium  integrity=low  overall=low" in output
    assert "lane status: criteria=completed  integrity=timed-out" in output
    assert "harness error: integrity=pi timed out after 1200s" in output
    assert "timing: wall=1201.0s  criteria=completed 1.2s 4 tools  integrity=timed-out 1200.0s 1 tools" in output
    assert "commit=evaluated-commit  merge=different-merge-commit  (mismatch)" in output


def test_print_evaluation_renders_orphaned_intelligence_fields(capsys) -> None:
    print_evaluation({
        "verdict": "pass",
        "criteria_verdict": "pass",
        "criteria_confidence": 0.9,
        "integrity": {"verdict": "pass", "confidence": 0.8, "findings": []},
        "semantic_risks": "Risk: queries rely on self-reported timestamps.",
        "followup_candidates": "Human clarification: is X part of the criteria?",
        "human_review_questions": [
            {"criterion_id": "c1", "question": "Is this criterion path stale?"}
        ],
    })

    output = capsys.readouterr().out
    assert "risks:" in output
    assert "Risk: queries rely on self-reported timestamps." in output
    assert "followups:" in output
    assert "Human clarification: is X part of the criteria?" in output
    assert "question (c1): Is this criterion path stale?" in output


def test_job_show_leads_with_verdict_and_reasoning(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "queue.db"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT, node_id TEXT, title TEXT, queue_state TEXT, status TEXT,
            executor TEXT, job_type TEXT, attempt INTEGER, max_attempts INTEGER,
            created_at TEXT, artifacts_dir TEXT
        );
        CREATE TABLE results (
            job_id TEXT, received_at TEXT, outcome TEXT, status TEXT,
            acceptance_check TEXT
        );
        CREATE TABLE executor_sessions (
            job_id TEXT, attempt_index INTEGER, executor TEXT, session_id TEXT,
            state TEXT, error TEXT, result_commit_sha TEXT,
            expected_base_commit_sha TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE decision_results (
            node_id TEXT, created_at TEXT, action TEXT, reason TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "job-1", "node-1", "Human-readable title", "awaiting_review",
            "awaiting_review", "local_subprocess", "implementation", 0, 3,
            "2026-08-01T00:00:00Z", "/tmp/job-1",
        ),
    )
    con.execute(
        "INSERT INTO results VALUES (?,?,?,?,?)",
        (
            "job-1", "2026-08-01T01:00:00Z", "pass", "awaiting_review",
            json.dumps({
                "verdict": "pass",
                "criteria_verdict": "pass",
                "criteria_confidence": 0.9,
                "integrity": {
                    "verdict": "pass",
                    "confidence": 0.8,
                    "reasoning": "Intent and graph integrity are preserved.",
                },
            }),
        ),
    )
    con.commit()
    con.close()

    monkeypatch.setattr(jobs_status, "DB_PATH", db_path)
    jobs_status.cmd_show(Namespace(ref="job-1", full=False))

    output = capsys.readouterr().out
    assert output.startswith("EVALUATOR RESULT\n  verdict: pass\n  why:")
    assert "Intent and graph integrity are preserved." in output
    assert output.index("  verdict: pass") < output.index("JOB RECORD")
    assert output.index("JOB RECORD") < output.index("  job_id: job-1")
