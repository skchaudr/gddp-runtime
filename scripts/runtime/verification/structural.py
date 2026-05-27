"""structural.py — Pure structural invariant checks for the GDDP runtime.

All checks are deterministic, side-effect-free functions that accept plain
Python data structures and return InvariantResult instances.  No filesystem,
git, network, or database access is performed.
"""

from typing import Dict, List, Set

from scripts.runtime.verification.invariant_schema import (
    InvariantResult,
    StructuralOutput,
)


def check_graph_legality(graph: dict) -> InvariantResult:
    """Every depends_on entry must reference an existing node id."""
    nodes: Dict = graph.get("nodes", {})
    node_ids: Set[str] = set(nodes.keys())
    missing: List[str] = []

    for node_id, node_data in nodes.items():
        for dep in node_data.get("depends_on", []):
            if dep not in node_ids:
                missing.append(f"node '{node_id}' depends on unknown node '{dep}'")

    if missing:
        return InvariantResult(
            check="graph_legality",
            passed=False,
            evidence="Missing dependencies: " + "; ".join(missing),
        )
    return InvariantResult(
        check="graph_legality",
        passed=True,
        evidence="All dependency references resolve to existing nodes.",
    )


def check_acyclic(graph: dict) -> InvariantResult:
    """depends_on edges must form a DAG. Detect cycles via DFS."""
    nodes: Dict = graph.get("nodes", {})

    WHITE, GRAY, BLACK = 0, 1, 2
    colour: Dict[str, int] = {nid: WHITE for nid in nodes}
    cycle_node: str = ""

    def dfs(node_id: str) -> bool:
        nonlocal cycle_node
        colour[node_id] = GRAY
        for dep in nodes[node_id].get("depends_on", []):
            if dep not in colour:
                continue
            if colour[dep] == GRAY:
                cycle_node = dep
                return True
            if colour[dep] == WHITE:
                if dfs(dep):
                    return True
        colour[node_id] = BLACK
        return False

    for nid in nodes:
        if colour[nid] == WHITE:
            if dfs(nid):
                return InvariantResult(
                    check="graph_acyclic",
                    passed=False,
                    evidence=f"Cycle detected involving node '{cycle_node}'",
                )
    return InvariantResult(
        check="graph_acyclic",
        passed=True,
        evidence="The dependency graph is acyclic.",
    )


def check_artifacts_exist(
    declared_artifacts: List[str],
    present_paths: List[str],
) -> InvariantResult:
    """Every declared artifact must appear in present_paths."""
    if not declared_artifacts:
        return InvariantResult(
            check="artifacts_exist",
            passed=True,
            evidence="No artifacts declared; vacuously satisfied.",
        )
    present_set: Set[str] = set(present_paths)
    missing = [a for a in declared_artifacts if a not in present_set]
    if missing:
        return InvariantResult(
            check="artifacts_exist",
            passed=False,
            evidence=f"Missing artifacts: {', '.join(missing)}",
        )
    return InvariantResult(
        check="artifacts_exist",
        passed=True,
        evidence="All declared artifacts are present.",
    )


def check_files_in_scope(
    changed_files: List[str],
    allowed_paths: List[str],
) -> InvariantResult:
    """Every changed file must be under at least one allowed_paths prefix."""
    if not changed_files:
        return InvariantResult(
            check="files_in_scope",
            passed=True,
            evidence="No changed files; vacuously satisfied.",
        )
    if not allowed_paths:
        return InvariantResult(
            check="files_in_scope",
            passed=False,
            evidence="No allowed paths configured.",
        )
    out_of_scope = [f for f in changed_files
                    if not any(f.startswith(p) for p in allowed_paths)]
    if out_of_scope:
        return InvariantResult(
            check="files_in_scope",
            passed=False,
            evidence=f"Files outside allowed scope: {', '.join(out_of_scope)}",
        )
    return InvariantResult(
        check="files_in_scope",
        passed=True,
        evidence="All changed files are within the allowed scope.",
    )


def check_acceptance_not_weakened(
    acceptance_before: List[str],
    acceptance_after: List[str],
) -> InvariantResult:
    """No criterion in _before may be absent from _after."""
    if not acceptance_before:
        return InvariantResult(
            check="acceptance_not_weakened",
            passed=True,
            evidence="No prior acceptance criteria; vacuously satisfied.",
        )
    removed = sorted(set(acceptance_before) - set(acceptance_after))
    if removed:
        return InvariantResult(
            check="acceptance_not_weakened",
            passed=False,
            evidence=f"Removed acceptance criteria: {', '.join(removed)}",
        )
    return InvariantResult(
        check="acceptance_not_weakened",
        passed=True,
        evidence="All prior acceptance criteria are preserved.",
    )


def run_structural_validator(
    *,
    graph: dict,
    node: dict,
    changed_files: list[str],
    present_paths: list[str],
    acceptance_before: list[str],
    acceptance_after: list[str],
) -> StructuralOutput:
    """Run all 5 structural checks and collect results."""
    declared_artifacts: list[str] = node.get("artifacts", [])
    allowed_paths: list[str] = node.get("allowed_paths", [])

    results: List[InvariantResult] = [
        check_graph_legality(graph),
        check_acyclic(graph),
        check_artifacts_exist(declared_artifacts, present_paths),
        check_files_in_scope(changed_files, allowed_paths),
        check_acceptance_not_weakened(acceptance_before, acceptance_after),
    ]

    return StructuralOutput(
        all_passed=all(r.passed for r in results),
        results=results,
    )
