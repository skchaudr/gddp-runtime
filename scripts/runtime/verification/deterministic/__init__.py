"""Deterministic verification floor — assembles a DeterministicResult."""

from __future__ import annotations

from pathlib import Path

from ..schemas import (
    CriterionMismatch,
    DeterministicResult,
    HumanReviewQuestion,
    MissingEvidence,
)
from .artifacts import check_artifacts
from .constraints import collect_constraint_files, evaluate_constraint
from .deps import dependency_status
from .probes import evaluate_criterion


def assemble(
    *,
    node_yaml: dict,
    project_yaml: dict,
    repo: Path,
    config_root: Path | None = None,
) -> DeterministicResult:
    """Run all deterministic checks and return a DeterministicResult."""
    node_id = node_yaml.get("node_id", "")

    criteria = [
        evaluate_criterion(item, repo, node_id, config_root=config_root)
        for item in node_yaml.get("acceptance", [])
    ]

    constraint_files = collect_constraint_files(node_yaml, repo)
    constraints = [
        evaluate_constraint(text, repo, constraint_files)
        for text in node_yaml.get("constraints", [])
    ]

    deps_status = dependency_status(project_yaml, node_yaml.get("depends_on", []))
    artifacts_present = check_artifacts(node_yaml, repo)

    criteria_mismatches = [
        CriterionMismatch(
            criterion_id=c.id,
            kind=c.mismatch_kind,
            detail=c.mismatch_detail,
        )
        for c in criteria
        if c.mismatch_kind and c.status != "pass"
    ]
    missing_evidence = [
        MissingEvidence(
            criterion_id=c.id,
            what_is_missing=c.mismatch_detail or c.reasoning,
            what_exists=c.evidence[0] if c.evidence else "",
        )
        for c in criteria
        if c.needs_evidence
    ]
    human_review_questions = [
        HumanReviewQuestion(criterion_id=c.id, question=c.human_question)
        for c in criteria
        if c.human_question
    ]

    return DeterministicResult(
        criteria=criteria,
        constraints=constraints,
        artifacts_present=artifacts_present,
        deps_status=deps_status,
        criteria_mismatches=criteria_mismatches,
        missing_evidence=missing_evidence,
        human_review_questions=human_review_questions,
    )


__all__ = ["assemble"]