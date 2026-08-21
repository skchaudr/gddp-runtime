"""Tests for the integrity combiner — the two-lane authority boundary."""

from __future__ import annotations

from . import integrity_combiner
from .schemas import (
    GraphObservation,
    GraphRecommendation,
    IntegrityFinding,
    IntegrityOutput,
    Verdict,
)


# ---------------------------------------------------------------------------
# Unit tests: _INTEGRITY_FLOOR mapping and combine() behaviour
# ---------------------------------------------------------------------------

def _integrity(
    verdict: str = "pass",
    intent_preserved: bool = True,
    graph_integrity_preserved: bool = True,
    required_human_review: bool = False,
) -> IntegrityOutput:
    return IntegrityOutput(
        verdict=verdict,
        intent_preserved=intent_preserved,
        graph_integrity_preserved=graph_integrity_preserved,
        required_human_review=required_human_review,
        confidence=0.9,
        findings=[],
        reasoning="test",
    )


def test_combine_none_integrity_returns_criteria_unchanged() -> None:
    combined, action = integrity_combiner.combine(Verdict.PASS, None, "proceed")
    assert combined == Verdict.PASS
    assert action == "proceed"


def test_combine_integrity_pass_returns_criteria_unchanged() -> None:
    combined, action = integrity_combiner.combine(
        Verdict.PASS, _integrity("pass"), "proceed"
    )
    assert combined == Verdict.PASS
    assert action == "proceed"


def test_combine_integrity_pass_does_not_downgrade_criteria_fail() -> None:
    combined, action = integrity_combiner.combine(
        Verdict.FAIL, _integrity("pass"), "fix and re-submit"
    )
    assert combined == Verdict.FAIL
    assert action == "fix and re-submit"


def test_combine_drift_floors_at_needs_human_review() -> None:
    combined, action = integrity_combiner.combine(
        Verdict.PASS, _integrity("drift"), "proceed"
    )
    assert combined == Verdict.NEEDS_HUMAN_REVIEW
    assert "Human review required" in action


def test_combine_contradicted_floors_at_needs_human_review() -> None:
    combined, action = integrity_combiner.combine(
        Verdict.PASS, _integrity("contradicted"), "proceed"
    )
    assert combined == Verdict.NEEDS_HUMAN_REVIEW
    assert "Human review required" in action


def test_combine_block_floors_at_needs_human_review() -> None:
    combined, action = integrity_combiner.combine(
        Verdict.PASS, _integrity("block"), "proceed"
    )
    assert combined == Verdict.NEEDS_HUMAN_REVIEW
    assert "Human review required" in action


def test_combine_insufficient_floors_at_needs_more_evidence() -> None:
    combined, action = integrity_combiner.combine(
        Verdict.PASS, _integrity("insufficient"), "proceed"
    )
    assert combined == Verdict.NEEDS_MORE_EVIDENCE
    assert "Human review required" in action


def test_combine_unknown_floors_at_needs_human_review() -> None:
    combined, action = integrity_combiner.combine(
        Verdict.PASS, _integrity("unknown"), "proceed"
    )
    assert combined == Verdict.NEEDS_HUMAN_REVIEW
    assert "Human review required" in action


def test_combine_criteria_worse_than_integrity_floor_wins() -> None:
    # criteria is already FAIL, integrity drift floors at needs-human-review
    # FAIL > needs-human-review, so FAIL wins
    combined, action = integrity_combiner.combine(
        Verdict.FAIL, _integrity("drift"), "fix and re-submit"
    )
    assert combined == Verdict.FAIL


def test_combine_pass_with_violated_flags_floors_up() -> None:
    # integrity says pass but flags are violated — malformed; floor up
    combined, action = integrity_combiner.combine(
        Verdict.PASS,
        _integrity("pass", intent_preserved=False, graph_integrity_preserved=True),
        "proceed",
    )
    assert combined == Verdict.NEEDS_HUMAN_REVIEW


def test_combine_pass_with_both_flags_violated_floors_up() -> None:
    combined, action = integrity_combiner.combine(
        Verdict.PASS,
        _integrity("pass", intent_preserved=False, graph_integrity_preserved=False),
        "proceed",
    )
    assert combined == Verdict.NEEDS_HUMAN_REVIEW


def test_combine_block_with_violated_flags_stays_blocked() -> None:
    # integrity block + violated flags - block floors at needs-human-review
    # but even with flags violated, the floor is still needs-human-review
    combined, action = integrity_combiner.combine(
        Verdict.PASS,
        _integrity("block", intent_preserved=False, graph_integrity_preserved=False),
        "proceed",
    )
    assert combined == Verdict.NEEDS_HUMAN_REVIEW


def test_floor_mapping_exhaustive() -> None:
    """Every non-pass integrity verdict has a floor at or above its declared severity."""
    floors = integrity_combiner._INTEGRITY_FLOOR
    severity = integrity_combiner._SEVERITY
    # pass stays at PASS
    assert severity[floors["pass"]] == severity[Verdict.PASS]
    # all non-pass floors are >= needs-more-evidence
    for v in ("insufficient", "unknown", "drift", "contradicted", "block"):
        assert severity[floors[v]] >= severity[Verdict.NEEDS_MORE_EVIDENCE]
    # drift/contradicted/block/unknown floor at exactly needs-human-review, not higher
    for v in ("drift", "contradicted", "block", "unknown"):
        assert floors[v] == Verdict.NEEDS_HUMAN_REVIEW
    # insufficient floors at needs-more-evidence
    assert floors["insufficient"] == Verdict.NEEDS_MORE_EVIDENCE


# ---------------------------------------------------------------------------
# Phase 3: graph_observations do NOT floor the verdict
# ---------------------------------------------------------------------------


def test_graph_observations_do_not_floor_pass() -> None:
    """Integrity pass with graph_observations should NOT downgrade the verdict."""
    integrity = IntegrityOutput(
        verdict="pass",
        intent_preserved=True,
        graph_integrity_preserved=True,
        required_human_review=False,
        confidence=0.9,
        findings=[],
        reasoning="Current node passes.",
        graph_observations=[
            GraphObservation(
                severity="medium",
                summary="Upcoming nodes converge on the scheduler; serialize this region.",
                affected_node_ids=["downstream-a", "downstream-b"],
            )
        ],
    )
    combined, action = integrity_combiner.combine(Verdict.PASS, integrity, "proceed")
    assert combined == Verdict.PASS
    assert action == "proceed"


def test_graph_observations_with_findings_still_floors() -> None:
    """When findings ARE present (affecting flags), the verdict still floors."""
    integrity = IntegrityOutput(
        verdict="drift",
        intent_preserved=False,
        graph_integrity_preserved=True,
        required_human_review=True,
        confidence=0.85,
        findings=[
            IntegrityFinding(
                severity="high",
                summary="Scope creep detected.",
                affected_node_ids=["current-node"],
            )
        ],
        reasoning="Current node has drift.",
        graph_observations=[
            GraphObservation(
                severity="low",
                summary="Future convergence risk.",
                affected_node_ids=["downstream-a"],
            )
        ],
    )
    combined, action = integrity_combiner.combine(Verdict.PASS, integrity, "proceed")
    assert combined == Verdict.NEEDS_HUMAN_REVIEW


def test_graph_observations_only_no_findings_pass() -> None:
    """Only graph_observations, no findings, verdict pass -> combined stays pass."""
    integrity = IntegrityOutput(
        verdict="pass",
        intent_preserved=True,
        graph_integrity_preserved=True,
        required_human_review=False,
        confidence=0.95,
        findings=[],
        reasoning="Clean pass with forward-looking note.",
        graph_observations=[
            GraphObservation(
                severity="low",
                summary="Node arrival rate suggests aggressive parallel dispatch.",
                affected_node_ids=["downstream-a", "downstream-b", "downstream-c"],
            )
        ],
    )
    combined, action = integrity_combiner.combine(Verdict.PASS, integrity, "proceed")
    assert combined == Verdict.PASS
    assert action == "proceed"


def test_graph_recommendations_do_not_floor_pass() -> None:
    """Integrity pass with graph_recommendations must leave combined verdict pass."""
    integrity = IntegrityOutput(
        verdict="pass",
        intent_preserved=True,
        graph_integrity_preserved=True,
        required_human_review=False,
        confidence=0.9,
        findings=[],
        reasoning="Current node passes.",
        graph_recommendations=[
            GraphRecommendation(
                action="create_node",
                affected_node_ids=["node-13-preserve-results"],
                rationale="Missing continuation for query-result linking.",
                evidence=["graphs/myapi-part1/nodes/node-13-preserve-results.yaml"],
                draft_node_yaml="node_id: node-13b\n",
            )
        ],
    )
    combined, action = integrity_combiner.combine(Verdict.PASS, integrity, "proceed")
    assert combined == Verdict.PASS
    assert action == "proceed"
