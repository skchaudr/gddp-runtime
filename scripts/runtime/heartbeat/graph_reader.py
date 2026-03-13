"""
graph_reader.py — Reads gddp-config YAML and returns graph state.

Replaces the hardcoded PHASE3_NODE dict in heartbeat.py.
The config_path must point to the root of a gddp-config checkout.
On the Pi: set GDDP_CONFIG_PATH env var or pass explicitly.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class NodeData:
    node_id: str
    title: str
    status: str
    type: str
    why: str
    depends_on: list[str]
    acceptance: list[str]
    constraints: list[str]
    allowed_execution_modes: list[str]
    required_artifacts: list[str]
    priority: str
    unlocks: list[str]


@dataclass
class ProjectGraph:
    project_id: str
    project_name: str
    repo: str
    nodes: list[dict]          # summary rows from project.yaml
    execution_policy: dict


class GraphReader:
    def __init__(self, config_path: Optional[str] = None):
        # Resolve path: arg > env var > sibling directory convention
        if config_path:
            self.config_path = Path(config_path)
        elif os.getenv("GDDP_CONFIG_PATH"):
            self.config_path = Path(os.environ["GDDP_CONFIG_PATH"])
        else:
            # Convention: gddp-config lives next to gddp-runtime in ~/repos/
            runtime_root = Path(__file__).parent.parent.parent.parent
            self.config_path = runtime_root.parent / "gddp-config"

        if not self.config_path.exists():
            raise FileNotFoundError(
                f"gddp-config not found at {self.config_path}. "
                "Set GDDP_CONFIG_PATH env var or pass config_path explicitly."
            )

    def load_project(self, project_id: str) -> ProjectGraph:
        project_yaml = self.config_path / "graphs" / project_id / "project.yaml"
        if not project_yaml.exists():
            raise FileNotFoundError(f"No project graph found: {project_yaml}")

        with open(project_yaml) as f:
            data = yaml.safe_load(f)

        return ProjectGraph(
            project_id=data["project_id"],
            project_name=data["project_name"],
            repo=data["repo"],
            nodes=data.get("nodes", []),
            execution_policy=data.get("execution_policy", {}),
        )

    def load_node(self, project_id: str, node_id: str) -> NodeData:
        node_file = self.config_path / "graphs" / project_id / "nodes" / f"{node_id}.yaml"
        if not node_file.exists():
            raise FileNotFoundError(f"No node file found: {node_file}")

        with open(node_file) as f:
            data = yaml.safe_load(f)

        return NodeData(
            node_id=data["node_id"],
            title=data["title"],
            status=data.get("status", "pending"),
            type=data.get("type", "capability"),
            why=data.get("why", ""),
            depends_on=data.get("depends_on", []),
            acceptance=data.get("acceptance", []),
            constraints=data.get("constraints", []),
            allowed_execution_modes=data.get("allowed_execution_modes", ["jules"]),
            required_artifacts=data.get("required_artifacts", []),
            priority=data.get("priority", "normal"),
            unlocks=data.get("unlocks", []),
        )

    def get_ready_nodes(self, project_id: str) -> list[NodeData]:
        """
        Returns nodes that are status=ready in project.yaml AND have a node YAML file.
        Does not verify depends_on at this layer — scope_checker handles that.
        """
        project = self.load_project(project_id)
        ready = []

        for node_summary in project.nodes:
            if node_summary.get("status") != "ready":
                continue
            try:
                node = self.load_node(project_id, node_summary["id"])
                ready.append(node)
            except FileNotFoundError:
                # Node is ready in project.yaml but has no detail file yet — skip
                pass

        return ready
