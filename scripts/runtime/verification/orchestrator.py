from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import decision_engine, deterministic, integrity_combiner
from .schemas import IntegrityOutput, SemanticOutput, VerdictReceipt
from .semantic.agent import SemanticAgent

SemanticHarness = Callable[..., SemanticOutput]
IntegrityHarness = Callable[..., IntegrityOutput]


def verify(
    *,
    node_yaml: dict,
    project_yaml: dict,
    repo: Path,
    runner,
    toolbox,
    shape_profile: dict | None = None,
    config_root: Path | None = None,
    semantic_agent_kwargs: dict[str, Any] | None = None,
    semantic_harness: SemanticHarness | None = None,
    integrity_harness: IntegrityHarness | None = None,
    now: Callable[[], str] = lambda: __import__("datetime")
    .datetime.now(__import__("datetime").timezone.utc)
    .isoformat(),
) -> VerdictReceipt:
    det = deterministic.assemble(
        node_yaml=node_yaml,
        project_yaml=project_yaml,
        repo=repo,
        config_root=config_root,
    )
    semantic = None
    if _should_run_semantic(det):
        if semantic_harness is not None:
            semantic = semantic_harness(
                node=node_yaml,
                graph=project_yaml,
                deterministic_result=det,
                shape_profile=shape_profile,
                repo=repo,
            )
        else:
            semantic = SemanticAgent(runner=runner, toolbox=toolbox, **(semantic_agent_kwargs or {})).run(
                node=node_yaml,
                graph=project_yaml,
                deterministic_result=det,
                shape_profile=shape_profile,
            )

    verdict, confidence, action = decision_engine.decide(det, semantic)

    # Lane 2: integrity evaluation ALWAYS runs (unlike semantic criteria
    # adjudication, which only fires on indeterminate evidence). A green
    # deterministic run must not bypass it. None here means not wired yet;
    # the live bridge will default this ON.
    criteria_verdict = verdict
    integrity = None
    if integrity_harness is not None:
        integrity = integrity_harness(
            node=node_yaml,
            graph=project_yaml,
            deterministic_result=det,
            repo=repo,
        )
        verdict, action = integrity_combiner.combine(criteria_verdict, integrity, action)

    return VerdictReceipt(
        project_id=project_yaml.get("project_id", ""),
        node_id=node_yaml.get("node_id", ""),
        verdict=verdict,
        criteria_verdict=criteria_verdict,
        integrity=integrity,
        confidence=confidence,
        criteria_confidence=confidence,
        completeness_status=_completeness_status(semantic),
        deterministic=det,
        semantic=semantic,
        decision_reasoning=semantic.overall_reasoning if semantic else action,
        required_next_action=action,
        generated_at=now(),
    )


def _should_run_semantic(det) -> bool:
    has_indeterminate = any(criterion.status == "indeterminate" for criterion in det.criteria)
    deps_incomplete = any(status != "complete" for status in det.deps_status.values())
    constraint_violated = any(constraint.status == "violated" for constraint in det.constraints)
    criterion_failed = any(criterion.status == "fail" for criterion in det.criteria)
    return has_indeterminate and not deps_incomplete and not constraint_violated and not criterion_failed


def _completeness_status(semantic) -> str:
    if semantic is None:
        return "not-run"
    if semantic.budget_exhausted or not semantic.judgments:
        return "partial"
    return "complete"
