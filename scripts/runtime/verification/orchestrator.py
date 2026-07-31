from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from . import decision_engine, deterministic, integrity_combiner
from .schemas import ContextCoverage, IntegrityOutput, LaneCoverage, SemanticOutput, VerdictReceipt
from .semantic.agent import SemanticAgent
from .semantic.context_builder import build_canonical_pointers

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
    # Phase 1 provenance: the exact change being judged.
    merge_commit_sha: str | None = None,
    pr_ref: str | None = None,
    job_id: str | None = None,
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
        # The built-in SemanticAgent fallback was removed: pi is the only
        # evaluator path. If no pi harness is wired, hard-fail rather than
        # silently run the weaker agent with broken coverage traces.
        if semantic_harness is None:
            raise RuntimeError(
                "semantic_harness (pi) is required — the built-in agent "
                "fallback was removed. Wire PiHarnessRunner in the bridge."
            )
        semantic = semantic_harness(
            node=node_yaml,
            graph=project_yaml,
            deterministic_result=det,
            shape_profile=shape_profile,
            repo=repo,
        )

    verdict, signals, action = decision_engine.decide(det, semantic)

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
            config_root=config_root,
        )
        verdict, action = integrity_combiner.combine(criteria_verdict, integrity, action)

    # Phase 2: build canonical context and compute per-lane coverage.
    canonical = build_canonical_pointers(
        node=node_yaml, graph=project_yaml, repo=repo, config_root=config_root,
    )
    coverage = _compute_context_coverage(canonical, semantic, integrity, repo)

    return VerdictReceipt(
        project_id=project_yaml.get("project_id", ""),
        node_id=node_yaml.get("node_id", ""),
        verdict=verdict,
        criteria_verdict=criteria_verdict,
        integrity=integrity,
        confidence=signals.overall_confidence,
        criteria_confidence=signals.criteria_confidence,
        completeness=signals.completeness,
        graph_readiness=signals.graph_readiness,
        completeness_status=_completeness_status(semantic),
        deterministic=det,
        semantic=semantic,
        decision_reasoning=semantic.overall_reasoning if semantic else action,
        required_next_action=action,
        generated_at=now(),
        evaluated_tree_sha=_capture_tree_sha(repo),
        evaluated_commit_sha=_capture_commit_sha(repo),
        merge_commit_sha=merge_commit_sha,
        pr_ref=pr_ref,
        job_id=job_id,
        canonical_context=canonical,
        context_coverage=coverage,
    )


def _capture_tree_sha(repo: Path) -> str | None:
    """Best-effort capture of the git tree SHA at the repo path.

    This is a tree object SHA, not a commit SHA. It remains for receipt
    provenance; compare merge_commit_sha to evaluated_commit_sha instead.
    Returns None if the repo is not a git repo or git is unavailable — never
    raises.
    """
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _capture_commit_sha(repo: Path) -> str | None:
    """Best-effort capture of the exact commit evaluated at ``repo``.

    ``merge_commit_sha`` is a commit SHA, while ``HEAD^{tree}`` is a tree
    object SHA. Keep both receipt fields, but only compare commit to commit.
    """
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _should_run_semantic(det) -> bool:
    has_indeterminate = any(criterion.status == "indeterminate" for criterion in det.criteria)
    deps_incomplete = any(
        status not in decision_engine.SATISFIED_DEP_STATUSES
        for status in det.deps_status.values()
    )
    constraint_violated = any(constraint.status == "violated" for constraint in det.constraints)
    criterion_failed = any(criterion.status == "fail" for criterion in det.criteria)
    return has_indeterminate and not deps_incomplete and not constraint_violated and not criterion_failed


def _completeness_status(semantic) -> str:
    if semantic is None:
        return "not-run"
    if semantic.budget_exhausted or not semantic.judgments:
        return "partial"
    return "complete"


# ---------------------------------------------------------------------------
# Phase 2: Context coverage computation
# ---------------------------------------------------------------------------

_COVERAGE_SEVERITY = {"none": 0, "low": 1, "medium": 2, "high": 3}
_DOC_KEYS = {"readme", "project_brief"}


def _compute_context_coverage(
    canonical: dict[str, str],
    semantic: SemanticOutput | None,
    integrity: IntegrityOutput | None,
    repo: Path | None = None,
) -> ContextCoverage | None:
    """Compute per-lane context coverage from canonical pointers + tool traces.

    Cross-references the offered canonical paths against read/grep tool calls
    in each lane's trace. read and grep count as content access; ls and find
    do not (they show awareness of existence, not content examination).

    Rating logic per lane:
      - none: zero canonical paths accessed
      - low: some content accessed but no canonical docs (README/PROJECT-BRIEF)
      - medium: at least one doc accessed, no neighbors accessed, neighbors offered
      - high: at least one doc accessed AND (neighbor accessed OR no neighbors offered)

    The no-neighbor rule: when zero neighbors are offered, "high" is achievable
    by reading canonical docs alone.
    """
    if not canonical:
        return None

    # Split offered paths into docs and neighbors, excluding UNAVAILABLE.
    # Normalize to resolved absolute paths so relative tool-call paths match.
    offered_doc_paths: set[str] = set()
    offered_neighbor_paths: set[str] = set()
    for key, val in canonical.items():
        if not isinstance(val, str) or val.startswith("UNAVAILABLE"):
            continue
        resolved = str(Path(val).resolve())
        if key in _DOC_KEYS:
            offered_doc_paths.add(resolved)
        elif key == "foundational_node":
            offered_neighbor_paths.add(resolved)
        elif key.startswith("neighbor:"):
            offered_neighbor_paths.add(resolved)

    all_offered = offered_doc_paths | offered_neighbor_paths
    if not all_offered:
        return None

    # Extract accessed paths from each lane's trace.
    # Pass repo so relative paths in the trace can be resolved to absolute
    # for matching against the offered canonical paths.
    criteria_accessed = _extract_accessed_paths(semantic, is_semantic=True, repo=repo) if semantic else None
    integrity_accessed = _extract_accessed_paths(integrity, is_semantic=False, repo=repo) if integrity else set()

    # Compute per-lane coverage.
    if criteria_accessed is None:
        criteria_lane: LaneCoverage | Literal["not_run"] = "not_run"
    else:
        criteria_lane = _rate_lane(criteria_accessed, all_offered, offered_doc_paths, offered_neighbor_paths)

    integrity_lane = _rate_lane(integrity_accessed, all_offered, offered_doc_paths, offered_neighbor_paths)

    # Overall = worst of the two lanes that ran.
    if criteria_lane == "not_run":
        overall = integrity_lane.rating
    else:
        overall = min(
            _COVERAGE_SEVERITY[criteria_lane.rating],
            _COVERAGE_SEVERITY[integrity_lane.rating],
        )
        overall = _sev_to_rating(overall)

    return ContextCoverage(
        criteria=criteria_lane,
        integrity=integrity_lane,
        overall=overall,
    )


def _extract_accessed_paths(output, is_semantic: bool, repo: Path | None = None) -> set[str]:
    """Extract file paths from read/grep tool calls in a lane's trace.

    For SemanticOutput, the trace is in budget_trace['tool_calls'] (pi path)
    or budget_trace['events'] (built-in agent path).
    For IntegrityOutput, the trace is in tool_trace.

    Paths are resolved to absolute using repo as the base for relative paths,
    so they match against the offered canonical paths (which are absolute).
    """
    accessed: set[str] = set()

    def _resolve(path: str) -> str:
        p = Path(path)
        if not p.is_absolute() and repo is not None:
            p = (repo / p).resolve()
        else:
            p = p.resolve()
        return str(p)

    if is_semantic:
        trace = output.budget_trace
        if not trace:
            return accessed
        # Pi path: trace has 'tool_calls' list
        tool_calls = trace.get("tool_calls") if isinstance(trace, dict) else None
        if tool_calls:
            tool_results = _tool_results(tool_calls)
            for entry in tool_calls:
                if _successful_content_access(entry, tool_results):
                    path = entry.get("path")
                    if path and isinstance(path, str):
                        accessed.add(_resolve(path))
        # Built-in agent path: trace has 'events' list
        events = trace.get("events") if isinstance(trace, dict) else None
        if events:
            for event in events:
                if event.get("event") == "tool_result" and event.get("tool") in ("read_file", "grep_code"):
                    # The built-in agent's trace doesn't record the path directly,
                    # so we can't match it. This is a known limitation.
                    pass
    else:
        trace = output.tool_trace
        if not trace:
            return accessed
        tool_results = _tool_results(trace)
        for entry in trace:
            if _successful_content_access(entry, tool_results):
                path = entry.get("path")
                if path and isinstance(path, str):
                    accessed.add(_resolve(path))

    return accessed


def _tool_results(trace: list[dict[str, Any]]) -> dict[str, bool]:
    """Map tool call IDs to their actual execution outcome."""
    return {
        entry["toolCallId"]: bool(entry.get("ok"))
        for entry in trace
        if entry.get("event") == "tool_execution_end"
        and isinstance(entry.get("toolCallId"), str)
    }


def _successful_content_access(entry: dict[str, Any], results: dict[str, bool]) -> bool:
    """Only successful read/grep calls establish content coverage.

    Older traces have no execution event or toolCallId; retain their previous
    meaning unless they explicitly report ``ok: false``.
    """
    if entry.get("tool") not in ("read", "grep") or entry.get("blocked"):
        return False
    call_id = entry.get("toolCallId")
    if isinstance(call_id, str):
        return results.get(call_id) is True
    return entry.get("ok") is not False


def _rate_lane(
    accessed: set[str],
    all_offered: set[str],
    doc_paths: set[str],
    neighbor_paths: set[str],
) -> LaneCoverage:
    """Rate a single lane's context coverage."""
    accessed_offered = accessed & all_offered
    accessed_docs = accessed & doc_paths
    accessed_neighbors = accessed & neighbor_paths
    not_observed = all_offered - accessed_offered

    if len(accessed_offered) == 0:
        rating = "none"
    elif len(accessed_docs) == 0:
        rating = "low"
    elif len(accessed_neighbors) == 0 and len(neighbor_paths) > 0:
        rating = "medium"
    else:
        # docs accessed AND (neighbors accessed OR no neighbors offered)
        rating = "high"

    return LaneCoverage(
        rating=rating,
        offered=len(all_offered),
        content_accessed=len(accessed_offered),
        not_observed=len(not_observed),
        accessed_paths=sorted(accessed_offered),
        not_observed_paths=sorted(not_observed),
    )


def _sev_to_rating(sev: int) -> str:
    for name, val in _COVERAGE_SEVERITY.items():
        if val == sev:
            return name
    return "none"
