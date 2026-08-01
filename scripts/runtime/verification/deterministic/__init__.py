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


_SUBJECT_DIFF_CAP = 50


def _subject_diff(repo: Path, base: str) -> dict:
    """Neutral files-touched evidence for base..HEAD. Valence-free by design:
    scope drift between authoring and completion is normal — the lane
    measures, it never accuses. Interpretation belongs to the semantic lane
    and the human gate."""
    import subprocess

    def _git(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=30, check=False,
        )

    tip = _git(["rev-parse", "HEAD"])
    proc = _git(["diff", "--name-status", f"{base}..HEAD"])
    if tip.returncode != 0 or proc.returncode != 0:
        return {
            "status": "unavailable",
            "base": base,
            "error": (proc.stderr or tip.stderr or "git diff failed").strip()[:200],
        }
    files = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        files.append({"status": status, "path": path})
    return {
        "status": "ok",
        "base": base,
        "tip": tip.stdout.strip(),
        "files": files[: _SUBJECT_DIFF_CAP],
        "truncated": len(files) > _SUBJECT_DIFF_CAP,
        "file_count": len(files),
        "note": (
            "Includes anything untracked the executor left behind (wrapper "
            "commits with git add -A) — junk is deliberately visible here."
        ),
    }


def assemble(
    *,
    node_yaml: dict,
    project_yaml: dict,
    repo: Path,
    config_root: Path | None = None,
    expected_base_commit_sha: str | None = None,
) -> DeterministicResult:
    """Run all deterministic checks and return a DeterministicResult."""
    node_id = node_yaml.get("node_id", "")

    criteria = [
        evaluate_criterion(item, repo, node_id, config_root=config_root)
        for item in node_yaml.get("acceptance_criteria", [])
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
        subject_diff=(
            _subject_diff(repo, expected_base_commit_sha)
            if expected_base_commit_sha
            else None
        ),
    )


__all__ = ["assemble"]