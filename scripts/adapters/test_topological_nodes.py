"""Unit tests for mission_projection._topological_nodes ordering."""

from __future__ import annotations

import pytest

from scripts.adapters.mission_projection import _topological_nodes
from scripts.runtime.heartbeat.graph_reader import NodeData


def _node(node_id: str, *, depends_on: list[str] | None = None) -> NodeData:
    return NodeData(
        node_id=node_id,
        title=f"Title for {node_id}",
        status="ready",
        type="capability",
        why=f"Why {node_id} matters",
        depends_on=depends_on or [],
        acceptance_criteria=[],
        constraints=[],
        allowed_execution_modes=["factory_mission"],
        required_artifacts=[],
        priority="normal",
        unlocks=[],
    )


def _ids(nodes: list[NodeData]) -> list[str]:
    return [node.node_id for node in nodes]


def test_depends_on_ordering_is_respected():
    """Dependents must appear after every selected dependency."""
    nodes = [
        _node("merge", depends_on=["left", "right"]),
        _node("tail", depends_on=["merge"]),
        _node("right", depends_on=["root"]),
        _node("left", depends_on=["root"]),
        _node("root"),
    ]

    ordered = _ids(_topological_nodes(nodes))

    for dependency, dependent in [
        ("root", "left"),
        ("root", "right"),
        ("left", "merge"),
        ("right", "merge"),
        ("merge", "tail"),
    ]:
        assert ordered.index(dependency) < ordered.index(dependent)
    assert set(ordered) == {node.node_id for node in nodes}


def test_independent_nodes_keep_stable_input_order():
    """Nodes with no selected deps preserve their relative input order."""
    nodes = [
        _node("gamma"),
        _node("alpha"),
        _node("beta"),
    ]

    assert _ids(_topological_nodes(nodes)) == ["gamma", "alpha", "beta"]


def test_independent_nodes_stay_stable_among_a_dependent_chain():
    """Unrelated ready nodes keep input order while chain deps still order."""
    nodes = [
        _node("indie-b"),
        _node("child", depends_on=["parent"]),
        _node("indie-a"),
        _node("parent"),
    ]

    ordered = _ids(_topological_nodes(nodes))

    assert ordered.index("parent") < ordered.index("child")
    # Ready roots in input order: indie-b, indie-a, parent — then child.
    assert ordered == ["indie-b", "indie-a", "parent", "child"]


def test_external_dependencies_are_ignored_for_ordering():
    """depends_on entries outside the selection do not block a node."""
    nodes = [
        _node("selected-child", depends_on=["outside-parent"]),
        _node("selected-root"),
    ]

    assert _ids(_topological_nodes(nodes)) == [
        "selected-child",
        "selected-root",
    ]


def test_duplicate_node_ids_raise():
    with pytest.raises(ValueError, match="duplicate node ids"):
        _topological_nodes([_node("same"), _node("same")])


def test_dependency_cycle_raises():
    nodes = [
        _node("first", depends_on=["second"]),
        _node("second", depends_on=["first"]),
    ]

    with pytest.raises(ValueError, match="cycle"):
        _topological_nodes(nodes)
