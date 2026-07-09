# Graph reader

The runtime needs to know which nodes are ready, what each node demands, and what the project's execution policy is. It gets all of that from `gddp-config` YAML. `scripts/runtime/heartbeat/graph_reader.py` is the only module that reads that YAML, and it only reads. It never writes, never proposes changes, never mutates graph truth. That boundary is the load-bearing one in the whole system: graph truth is human-owned, and the runtime is a reader of it.

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

`NodeData` is the materialized form of a single node YAML file. Defaults are permissive: `status` defaults to `pending`, `type` to `capability`, `allowed_execution_modes` to `["jules"]`, and the list fields to empty lists. The dataclass does not validate against the schema in `gddp-config/schemas/v1/`; it trusts the YAML and reads what is there.

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

`ProjectGraph` holds the project-level metadata plus the `nodes` list as raw summary dicts straight from `project.yaml`. The summaries are not promoted to `NodeData` here; that happens lazily in `load_node` and `get_ready_nodes`. `execution_policy` is passed through as a dict for the decision loop to read.

## Caching

Two in-memory caches eliminate redundant synchronous file I/O within a single runner invocation:

- `_project_cache: dict[str, ProjectGraph]` keyed by `project_id`
- `_node_cache: dict[tuple[str, str], NodeData]` keyed by `(project_id, node_id)`

Both are populated on first access and returned directly on subsequent accesses. The caches are per-instance, not shared across processes, which is fine because the heartbeat runner and the decision loop each construct their own `GraphReader`. The cache is never invalidated; if `gddp-config` changes mid-run, a new process picks it up.

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

## Read-only by design

The class has no write methods, no `update_node`, no `mark_complete`. The only way graph truth changes is through a human merging a PR against `gddp-config`. The runtime's path to influencing that is the [graph updater](graph-updater.md), which proposes via PR, never writes directly. Keeping the reader and the proposer as separate modules makes the boundary visible in the code layout, not just in the prose.

## Key source files

| File | Role |
|---|---|
| `scripts/runtime/heartbeat/graph_reader.py` | `GraphReader`, `NodeData`, `ProjectGraph`, path resolution, caching |

## Related pages

- [overview/architecture.md](../overview/architecture.md) for where the reader sits in the system flow
- [systems/heartbeat.md](heartbeat.md) for who calls `get_ready_nodes`
- [systems/graph-updater.md](graph-updater.md) for the write side of the same config repo
