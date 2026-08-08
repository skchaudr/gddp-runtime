from __future__ import annotations

import json
import re

import pytest

from scripts.adapters.mission_projection import (
    project_mission,
    verify_planned_feature_ids,
)
from scripts.runtime.heartbeat.graph_reader import NodeData


def _node(
    node_id: str,
    *,
    depends_on: list[str] | None = None,
    acceptance_criteria: list[object] | None = None,
    constraints: list[object] | None = None,
    required_artifacts: list[str] | None = None,
) -> NodeData:
    return NodeData(
        node_id=node_id,
        title=f"Title for {node_id}",
        status="ready",
        type="capability",
        why=f"Why {node_id} matters",
        depends_on=depends_on or [],
        acceptance_criteria=acceptance_criteria or [],  # type: ignore[arg-type]
        constraints=constraints or [],  # type: ignore[arg-type]
        allowed_execution_modes=["factory_mission"],
        required_artifacts=required_artifacts or [],
        priority="normal",
        unlocks=[],
    )


def _feature_ids(mission: str) -> list[str]:
    return re.findall(r"^### Feature `(.+)`$", mission, flags=re.MULTILINE)


def _feature_description(mission: str, node_id: str) -> str:
    heading = f"### Feature `{node_id}`\n"
    description = mission.split(heading, maxsplit=1)[1]
    return description.split("\n### Feature `", maxsplit=1)[0]


@pytest.mark.parametrize(
    "node_ids",
    [
        [],
        ["Node-One"],
        ["Audit_CASE", "execute.step-2", "final-node"],
    ],
)
def test_projection_declares_exactly_one_feature_per_node_with_exact_ids(node_ids):
    mission = project_mission([_node(node_id) for node_id in node_ids])

    assert _feature_ids(mission) == node_ids


def test_projection_orders_chain_diamond_and_independent_nodes_topologically():
    nodes = [
        _node("independent"),
        _node("merge", depends_on=["left", "right"]),
        _node("tail", depends_on=["merge"]),
        _node("right", depends_on=["root"]),
        _node("left", depends_on=["root"]),
        _node("root"),
    ]

    ordered_ids = _feature_ids(project_mission(nodes))

    for dependency, dependent in [
        ("root", "left"),
        ("root", "right"),
        ("left", "merge"),
        ("right", "merge"),
        ("merge", "tail"),
    ]:
        assert ordered_ids.index(dependency) < ordered_ids.index(dependent)
    assert set(ordered_ids) == {node.node_id for node in nodes}


def test_projection_rejects_cycles_in_the_selected_nodes():
    nodes = [
        _node("first", depends_on=["second"]),
        _node("second", depends_on=["first"]),
    ]

    with pytest.raises(ValueError, match="cycle"):
        project_mission(nodes)


def test_every_feature_requires_the_complete_minimal_execution_contract():
    node_ids = ["audit-One", "execute_two"]
    mission = project_mission(
        [_node(node_id) for node_id in node_ids],
        engagement_branch="gddp/engagement-123",
    )

    for node_id in node_ids:
        description = _feature_description(mission, node_id)
        assert "Make exactly one commit for this feature." in description
        assert f"GDDP-Node-Id: {node_id}" in description
        assert (
            f"gddp receipt --node-id {node_id} "
            "--base <starting SHA> --result <commit SHA>"
        ) in description
        assert "not complete until that receipt command exits successfully" in description
        assert (
            "git push origin "
            "HEAD:refs/heads/gddp/engagement-123"
        ) in description
        assert "Do not defer or batch this push with a later feature." in description
        assert "Never push to `main`, the repository default branch" in description
        assert "shared or release branch" in description
        assert "Never force-push" in description
        assert "`--force`, `-f`, `--force-with-lease`" in description
        assert "leading `+` refspec" in description
        assert (
            "git branch -r --contains <commit SHA>"
        ) in description
        assert "must list `origin/gddp/engagement-123`" in description
        assert (
            "not complete and must not report success until"
        ) in description


def test_projection_contains_no_gddp_gate_coupling():
    mission = project_mission([_node("source-node")]).casefold()

    for forbidden in [".gddp/gates", "gate-token", "gddp gate", "wait for gddp"]:
        assert forbidden not in mission


def test_projection_declares_one_milestone_and_assigns_every_feature_to_it():
    mission = project_mission([_node("one"), _node("two")])

    declarations = re.findall(r"^## Milestone$", mission, flags=re.MULTILINE)
    identities = re.findall(r"^Milestone: `(.+)`$", mission, flags=re.MULTILINE)

    assert len(declarations) == 1
    assert identities == ["gddp-engagement", "gddp-engagement"]
    assert set(identities) == {"gddp-engagement"}


def test_node_contract_fields_stay_complete_and_node_scoped():
    alpha = _node(
        "alpha",
        acceptance_criteria=[
            "Alpha output remains byte stable",
            {"id": "alpha-proof", "criterion": "Alpha proof is recorded"},
        ],
        constraints=["Only touch alpha.py"],
        required_artifacts=["reports/alpha evidence.md"],
    )
    beta = _node(
        "beta",
        acceptance_criteria=["Beta handles the sentinel value"],
        constraints=["Do not alter beta fixtures"],
        required_artifacts=["reports/beta.json"],
    )

    mission = project_mission([alpha, beta])
    alpha_description = _feature_description(mission, "alpha")
    beta_description = _feature_description(mission, "beta")

    for supplied_item in [
        "Alpha output remains byte stable",
        '"id": "alpha-proof"',
        '"criterion": "Alpha proof is recorded"',
        "Only touch alpha.py",
        "reports/alpha evidence.md",
    ]:
        assert supplied_item in alpha_description
        assert supplied_item not in beta_description
    for supplied_item in [
        "Beta handles the sentinel value",
        "Do not alter beta fixtures",
        "reports/beta.json",
    ]:
        assert supplied_item in beta_description
        assert supplied_item not in alpha_description


def test_operator_authored_topics_map_only_to_their_source_features():
    audit = _node("distinct-audit")
    audit.title = "Audit the lunar cache"
    audit.why = "The lunar cache needs operator-authored evidence"
    execution = _node("distinct-execution", depends_on=["distinct-audit"])
    execution.title = "Repair the solar index"
    execution.why = "The solar index must consume the audit"

    mission = project_mission([audit, execution])
    audit_description = _feature_description(mission, "distinct-audit")
    execution_description = _feature_description(mission, "distinct-execution")

    assert _feature_ids(mission) == ["distinct-audit", "distinct-execution"]
    assert audit.title in audit_description
    assert audit.why in audit_description
    assert execution.title not in audit_description
    assert execution.title in execution_description
    assert execution.why in execution_description
    assert audit.title not in execution_description


def test_audit_execution_pairs_remain_one_to_one_and_dependency_ordered():
    nodes = [
        _node("execute-two", depends_on=["audit-two"]),
        _node("audit-one"),
        _node("execute-one", depends_on=["audit-one"]),
        _node("audit-two"),
    ]

    ids = _feature_ids(project_mission(nodes))

    assert len(ids) == len(nodes)
    assert set(ids) == {node.node_id for node in nodes}
    assert ids.index("audit-one") < ids.index("execute-one")
    assert ids.index("audit-two") < ids.index("execute-two")


def test_post_planning_verification_proceeds_for_exact_ordered_ids(tmp_path):
    features_path = tmp_path / "features.json"
    features_path.write_text(
        json.dumps(
            {
                "features": [
                    {"id": "Audit_CASE"},
                    {"id": "execute.step-2"},
                ]
            }
        )
    )

    result = verify_planned_feature_ids(
        features_path, ["Audit_CASE", "execute.step-2"]
    )

    assert result.proceed is True
    assert result.park_for_review is False
    assert result.observed_ids == ("Audit_CASE", "execute.step-2")


@pytest.mark.parametrize(
    "observed_ids",
    [
        ["renamed", "execute"],
        ["audit", "execute", "added"],
        ["audit"],
        ["audit", "audit"],
        ["execute", "audit"],
        ["Audit", "execute"],
        ["audit_", "execute"],
    ],
)
def test_post_planning_verification_parks_every_feature_id_drift(
    tmp_path, observed_ids
):
    features_path = tmp_path / "features.json"
    features_path.write_text(
        json.dumps({"features": [{"id": node_id} for node_id in observed_ids]})
    )

    result = verify_planned_feature_ids(features_path, ["audit", "execute"])

    assert result.proceed is False
    assert result.park_for_review is True
    assert result.observed_ids == tuple(observed_ids)
    assert "feature id drift" in result.reason.casefold()


@pytest.mark.parametrize(
    "contents",
    [
        "{not-json",
        json.dumps({}),
        json.dumps({"features": [{"title": "missing id"}]}),
    ],
)
def test_post_planning_verification_parks_unverifiable_artifacts(
    tmp_path, contents
):
    features_path = tmp_path / "features.json"
    features_path.write_text(contents)

    result = verify_planned_feature_ids(features_path, ["audit"])

    assert result.proceed is False
    assert result.park_for_review is True
    assert result.observed_ids is None
    assert "cannot verify" in result.reason.casefold()


def test_projection_serializes_frozen_nodepacket_criteria_without_mappingproxy_error():
    """Regression for the first live factory_mission dispatch failure
    (2026-08-08): NodePacket freezes dict criteria as MappingProxyType, and
    mission projection must thaw before json.dumps."""
    from types import MappingProxyType

    from scripts.adapters.executor_protocol import NodePacket
    from scripts.adapters.mission_adapter import _packet_node

    packet = NodePacket(
        job_id="job_pi-harness",
        execution_attempt_id="job_pi-harness:attempt:0",
        node_id="node-01-subagents-audit",
        title="Audit pi subagents for reliability and traceability",
        goal="Audit the subagent system",
        why="Make multi-agent orchestration reliable",
        constraints=(
            {"scope": "read-only", "paths": ["agent/agents", "agent/chains"]},
            "Commit on the result ref only",
        ),
        acceptance_criteria=(
            {"id": "report-exists", "criterion": "report exists and is non-empty"},
            {"id": "evidence-cited", "criterion": "every finding cites a path"},
        ),
        required_artifacts=("reports/pi-harness-execution/subagents-audit.md",),
        attempt_index=0,
        previous_findings={"findings": [{"id": "watchdog", "detail": "noise"}]},
        expected_base_commit_sha="a" * 40,
    )

    # Prove the packet actually freezes nested maps the way live dispatch does.
    assert isinstance(packet.acceptance_criteria[0], MappingProxyType)
    assert isinstance(packet.constraints[0], MappingProxyType)
    assert isinstance(packet.previous_findings, MappingProxyType)

    mission = project_mission([_packet_node(packet)])

    assert "node-01-subagents-audit" in mission
    assert '"id": "report-exists"' in mission
    assert '"scope": "read-only"' in mission
    assert "mappingproxy" not in mission.casefold()
