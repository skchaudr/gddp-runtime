from __future__ import annotations

import pytest

from scripts.runtime.heartbeat import dispatcher
from adapters.mission_adapter import MissionAdapter
from scripts.runtime.heartbeat.graph_reader import (
    GraphReader,
    parse_execution_policy,
    select_ready_subgraph,
)


def test_factory_mission_registry_resolves_to_mission_adapter():
    assert dispatcher.ADAPTERS["factory_mission"] is MissionAdapter
    assert isinstance(dispatcher.ADAPTERS["factory_mission"](repo="owner/repo"), MissionAdapter)


def test_execution_policy_accepts_mission_sizing_fields():
    policy = parse_execution_policy(
        {
            "max_concurrent_jobs": 3,
            "mission_engagement_size": 4,
            "mission_max_pairs": 7,
        }
    )

    assert policy["max_concurrent_jobs"] == 3
    assert policy["mission_engagement_size"] == 4
    assert policy["mission_max_pairs"] == 7


def test_project_yaml_mission_sizing_survives_graph_reader_parsing(tmp_path):
    project_dir = tmp_path / "graphs" / "mission-project"
    project_dir.mkdir(parents=True)
    (project_dir / "project.yaml").write_text(
        """
project_id: mission-project
project_name: Mission project
repo: owner/repo
nodes: []
execution_policy:
  mission_engagement_size: 3
  mission_max_pairs: 4
""".lstrip()
    )

    policy = GraphReader(str(tmp_path)).load_project(
        "mission-project"
    ).execution_policy

    assert policy["mission_engagement_size"] == 3
    assert policy["mission_max_pairs"] == 4


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mission_engagement_size", 0),
        ("mission_engagement_size", -1),
        ("mission_engagement_size", True),
        ("mission_engagement_size", "2"),
        ("mission_max_pairs", 0),
        ("mission_max_pairs", False),
    ],
)
def test_execution_policy_rejects_non_positive_integer_sizing(field, value):
    with pytest.raises(ValueError, match=field):
        parse_execution_policy({field: value})


def test_ready_subgraph_defaults_to_one_pair():
    eligible_pairs = [
        ("audit-one", "execution-one"),
        ("audit-two", "execution-two"),
    ]

    assert select_ready_subgraph(eligible_pairs, {}) == [eligible_pairs[0]]


def test_ready_subgraph_is_capped_by_mission_max_pairs():
    eligible_pairs = [
        ("audit-one", "execution-one"),
        ("audit-two", "execution-two"),
        ("audit-three", "execution-three"),
        ("audit-four", "execution-four"),
    ]

    selected = select_ready_subgraph(
        eligible_pairs,
        {"mission_engagement_size": 4, "mission_max_pairs": 2},
    )

    assert selected == eligible_pairs[:2]
