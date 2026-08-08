# Graph reader

> Restored from the 2026-07-13 wiki. Cross-check implementation details against newer sibling pages, especially [Heartbeat](heartbeat.md), before operational use.

The runtime reads nodes and execution policy from `gddp-config` YAML through `scripts/runtime/heartbeat/graph_reader.py`. The `GraphReader` class itself only reads. The runtime as a whole is not read-only: `provisional_gate.py` and `frontier.py` write scheduler-visible statuses and then invalidate this reader's cache.

## Path resolution

`GraphReader.__init__` resolves the `gddp-config` checkout path with a three-step fallback:

1. **Constructor argument.** `GraphReader(config_path="/some/path")` wins if passed.
2. **Environment variable.** `GDDP_CONFIG_PATH` is checked next. This is the canonical mechanism on the Pi and in deployment.
3. **Sibling directory convention.** If neither is set, the reader assumes `gddp-config` lives next to `gddp-runtime` under the same parent directory (`~/repos/`), computed as `runtime_root.parent / "gddp-config"`.

If the resolved path does not exist, the constructor raises `FileNotFoundError` immediately with a message naming the path it tried and the two ways to fix it (set the env var or pass the argument). No silent fallback, no defaulting to an empty graph.

## NodeData

```python
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
```

`NodeData` is the materialized form of a single node YAML file. `status` defaults to `pending`, `type` to `capability`, `allowed_execution_modes` to `["jules"]`, and list fields to empty lists. Loading validates execution modes against `DEFAULT_EXECUTION_MODE_ALLOWLIST`; it does not perform complete config-schema validation.

## ProjectGraph

```python
@dataclass
class ProjectGraph:
    project_id: str
    project_name: str
    repo: str
    nodes: list[dict]           # summary rows from project.yaml
    execution_policy: dict
```

`ProjectGraph` holds project metadata plus raw node-summary dicts. `execution_policy` is normalized by `parse_execution_policy()`, which validates positive mission sizing and supplies defaults.

## Caching

Two in-memory caches eliminate redundant synchronous file I/O within a single runner invocation:

- `_project_cache: dict[str, ProjectGraph]` keyed by `project_id`
- `_node_cache: dict[tuple[str, str], NodeData]` keyed by `(project_id, node_id)`

Both are populated on first access and returned on subsequent accesses. `invalidate(project_id)` clears project and node entries after system writers change graph files, so a heartbeat can observe provisional/frontier writes during the same tick.

## load_project

Reads `graphs/<project_id>/project.yaml` under the config root, raises `FileNotFoundError` if the file is missing, parses with `yaml.safe_load`, and constructs a `ProjectGraph`. The result is cached and returned. The `nodes` field comes from `data.get("nodes", [])` and `execution_policy` from `data.get("execution_policy", {})`, so a project YAML that omits either still loads cleanly.

## load_node

Reads `graphs/<project_id>/nodes/<node_id>.yaml`, raises `FileNotFoundError` if missing, parses with `yaml.safe_load`, and constructs a `NodeData`. Cached by `(project_id, node_id)`. This is the call that promotes a summary row into a full node with criteria, constraints, artifacts, and dependencies.

## get_ready_nodes

Returns the list of `NodeData` objects that are both marked `status: ready` in `project.yaml` and have a corresponding node YAML file on disk. It does not verify `depends_on` at this layer; that is the scope checker's job. The walk is:

1. `load_project(project_id)` to get the summary list.
2. For each summary where `status == "ready"`, call `load_node(project_id, summary["id"])`.
3. If `load_node` raises `FileNotFoundError` (the node is ready in the project file but has no detail file yet), skip it silently.

The silent skip is intentional. A node can be marked ready in `project.yaml` before its detail file exists, and the runtime should not crash on that; it should just not consider the node dispatchable yet.

## Reader boundary

The class has no write methods. Separate runtime modules currently rewrite node/project YAML to `provisional` or `ready`; only the human writes accepted `complete`. This mixes scheduler state and human-owned graph files, so do not infer a repository-wide read-only boundary from the class name.

## Key source files

| File | Role |
|---|---|
| `scripts/runtime/heartbeat/graph_reader.py` | `GraphReader`, `NodeData`, `ProjectGraph`, path resolution, caching |

## Related pages

- [overview/architecture.md](../overview/architecture.md) for where the reader sits in the system flow
- [systems/heartbeat.md](heartbeat.md) for who calls `get_ready_nodes`
- [features/provisional-and-frontier.md](../features/provisional-and-frontier.md) for the live system writers
