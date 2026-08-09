"""
graph_reader.py — Reads gddp-config YAML and returns graph state.

Replaces the hardcoded PHASE3_NODE dict in heartbeat.py.
The config_path must point to the root of a gddp-config checkout.
On the Pi: set GDDP_CONFIG_PATH env var or pass explicitly.
"""

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from typing import Optional

import yaml

DEFAULT_MISSION_ENGAGEMENT_SIZE = 1
DEFAULT_MISSION_MAX_PAIRS = 5
DEFAULT_EXECUTION_MODE_ALLOWLIST = frozenset(
    {
        "agent",
        "droid",
        "factory_mission",
        "human",
        "jules",
        "jules_api",
        "jules_cli",
        "local_subprocess",
        "pi_rpc",
        "pi_worker",
        "vertex",
        "vm_worker",
    }
)


def validate_node_execution_modes(
    value: object,
    allowed_modes: Iterable[str] = DEFAULT_EXECUTION_MODE_ALLOWLIST,
) -> list[str]:
    """Return declared modes after enforcing the runtime allowlist."""
    if not isinstance(value, list):
        raise ValueError("allowed_execution_modes must be a list")

    allowlist = frozenset(allowed_modes)
    disallowed = [
        mode
        for mode in value
        if not isinstance(mode, str) or mode not in allowlist
    ]
    if disallowed:
        raise ValueError(f"disallowed execution mode(s): {disallowed}")
    return list(value)


def parse_execution_policy(value: object) -> dict:
    """Validate mission sizing and return a policy with stable defaults."""
    if value is None:
        policy = {}
    elif isinstance(value, Mapping):
        policy = dict(value)
    else:
        raise ValueError("execution_policy must be a mapping")

    for field_name, default in (
        ("mission_engagement_size", DEFAULT_MISSION_ENGAGEMENT_SIZE),
        ("mission_max_pairs", DEFAULT_MISSION_MAX_PAIRS),
    ):
        configured = policy.get(field_name, default)
        if (
            isinstance(configured, bool)
            or not isinstance(configured, int)
            or configured < 1
        ):
            raise ValueError(
                f"execution_policy.{field_name} must be a positive integer"
            )
        policy[field_name] = configured
    return policy


def select_ready_subgraph(
    eligible_pairs: Iterable[tuple[object, object]],
    execution_policy: object,
) -> list[tuple[object, object]]:
    """Select a deterministic, policy-bounded prefix of ready node pairs."""
    policy = parse_execution_policy(execution_policy)
    pair_limit = min(
        policy["mission_engagement_size"],
        policy["mission_max_pairs"],
    )
    return list(islice(eligible_pairs, pair_limit))


@dataclass
class NodeData:
    node_id: str
    title: str
    status: str
    type: str
    why: str
    depends_on: list[str]
    acceptance_criteria: list[str]
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
    def __init__(
        self,
        config_path: Optional[str] = None,
        *,
        execution_mode_allowlist: Iterable[str] | None = None,
    ):
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

        self.execution_mode_allowlist = frozenset(
            DEFAULT_EXECUTION_MODE_ALLOWLIST
            if execution_mode_allowlist is None
            else execution_mode_allowlist
        )

        # Internal caches to eliminate redundant synchronous file I/O
        self._project_cache: dict[str, ProjectGraph] = {}
        self._node_cache: dict[tuple[str, str], NodeData] = {}

    def invalidate(self, project_id: str | None = None) -> None:
        """Drop cached graph data so re-reads see freshly-written files.

        Evaluation finalize can write node status (e.g. provisional) after a
        reader has already cached the project; frontier re-checks in the same
        tick must not read the stale snapshot."""
        if project_id is None:
            self._project_cache.clear()
            self._node_cache.clear()
            return
        self._project_cache.pop(project_id, None)
        self._node_cache = {
            key: value
            for key, value in self._node_cache.items()
            if key[0] != project_id
        }

    def load_project(self, project_id: str) -> ProjectGraph:
        if project_id in self._project_cache:
            return self._project_cache[project_id]

        project_yaml = self.config_path / "graphs" / project_id / "project.yaml"
        if not project_yaml.exists():
            raise FileNotFoundError(f"No project graph found: {project_yaml}")

        with open(project_yaml) as f:
            data = yaml.safe_load(f)

        graph = ProjectGraph(
            project_id=data["project_id"],
            project_name=data["project_name"],
            repo=data["repo"],
            nodes=data.get("nodes", []),
            execution_policy=parse_execution_policy(
                data.get("execution_policy", {})
            ),
        )
        self._project_cache[project_id] = graph
        return graph

    def invalidate(self, project_id: str) -> None:
        """Drop cached project/node state after external graph-file writes.

        System writers (provisional_status, frontier) rewrite node/project
        YAML on disk; the runner must see fresh state within the same tick.
        """
        self._project_cache.pop(project_id, None)
        for key in [k for k in self._node_cache if k[0] == project_id]:
            self._node_cache.pop(key, None)

    def list_projects(self) -> list[ProjectGraph]:
        """Return every valid project graph in stable project-id order."""
        graphs_dir = self.config_path / "graphs"
        projects = []
        for project_file in sorted(graphs_dir.glob("*/project.yaml")):
            if project_file.parent.name.startswith("_"):
                continue
            projects.append(self.load_project(project_file.parent.name))
        return projects

    def load_node(self, project_id: str, node_id: str) -> NodeData:
        cache_key = (project_id, node_id)
        if cache_key in self._node_cache:
            return self._node_cache[cache_key]

        node_file = self.config_path / "graphs" / project_id / "nodes" / f"{node_id}.yaml"
        if not node_file.exists():
            raise FileNotFoundError(f"No node file found: {node_file}")

        with open(node_file) as f:
            data = yaml.safe_load(f)

        node = NodeData(
            node_id=data["node_id"],
            title=data["title"],
            status=data.get("status", "pending"),
            type=data.get("type", "capability"),
            why=data.get("why", ""),
            depends_on=data.get("depends_on", []),
            acceptance_criteria=data.get("acceptance_criteria", []),
            constraints=data.get("constraints", []),
            allowed_execution_modes=validate_node_execution_modes(
                data.get("allowed_execution_modes", ["jules"]),
                self.execution_mode_allowlist,
            ),
            required_artifacts=data.get("required_artifacts", []),
            priority=data.get("priority", "normal"),
            unlocks=data.get("unlocks", []),
        )
        self._node_cache[cache_key] = node
        return node

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
