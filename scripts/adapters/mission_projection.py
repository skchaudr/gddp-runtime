"""Project GDDP graph nodes into a Factory mission specification."""

from __future__ import annotations

import json
import shlex
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.adapters.executor_protocol import _thaw_json
from scripts.runtime.heartbeat.graph_reader import NodeData

DEFAULT_MILESTONE_ID = "gddp-engagement"
DEFAULT_ENGAGEMENT_BRANCH = "gddp/<engagement-id>"

# Mission-readiness guidance emitted into the mission spec so the droid
# mission planner has the explicit command catalog it demands and does not
# block planning on a start-stack script or user-facing QA. Override per
# engagement via ``project_mission(..., mission_readiness=...)``.
DEFAULT_MISSION_READINESS: tuple[str, ...] = (
    "Validation command: `python3 -m pytest -q` (the executable validation path).",
    "No application services to start or stop: this is a CLI/library repo, not a web stack. Do not invent a start script.",
    "User-facing QA is disabled (`missionModelSettings.skipUserTesting=true`); validators must stay read-only and must not attempt to drive a UI.",
    "Environment is already provisioned; no `init.sh` setup step is required.",
    "Do not block mission planning on a missing start-stack command.",
)

READ_ONLY_AUDIT_MISSION_READINESS: tuple[str, ...] = (
    "Mission type: read-only repository audit. Do not implement fixes or modify source/config files.",
    "No application services need to start or stop; do not invent a start script or `init.sh`.",
    "User-facing QA and scrutiny are disabled; validation is limited to required report artifacts and a clean diff check.",
)


@dataclass(frozen=True)
class PlanningVerification:
    """Decision at the planning boundary before mission execution proceeds."""

    proceed: bool
    demanded_ids: tuple[str, ...]
    observed_ids: tuple[str, ...] | None
    reason: str

    @property
    def park_for_review(self) -> bool:
        return not self.proceed


def project_mission(
    nodes: Sequence[NodeData],
    *,
    milestone_id: str = DEFAULT_MILESTONE_ID,
    engagement_branch: str = DEFAULT_ENGAGEMENT_BRANCH,
    mission_readiness: Sequence[str] | None = None,
) -> str:
    """Return a mission specification containing one feature per node."""
    projected = _topological_nodes(nodes)
    readiness = (
        _default_mission_readiness(projected)
        if mission_readiness is None
        else tuple(mission_readiness)
    )
    lines = [
        "# GDDP graph engagement",
        "",
        "Project only the supplied graph nodes.",
        f"Create exactly {len(projected)} features with the exact ids listed below.",
        "Do not add, remove, rename, split, merge, or reorder these features.",
        "",
        "## Milestone",
        "",
        f"- Id: `{milestone_id}`",
        f"- Name: `{milestone_id}`",
        "",
    ]
    if readiness:
        lines.extend(["## Mission readiness", "", *_item_lines(readiness), ""])
    lines.extend(["## Features", ""])

    for node in projected:
        lines.extend(
            [
                f"### Feature `{node.node_id}`",
                "",
                f"Milestone: `{milestone_id}`",
                f"Source node title: {node.title}",
                "",
                "#### Node intent",
                "",
                node.why or "Not supplied.",
                "",
                "#### Acceptance criteria",
                "",
                *_item_lines(node.acceptance_criteria),
                "",
                "#### Constraints",
                "",
                *_item_lines(node.constraints),
                "",
                "#### Required artifacts",
                "",
                *_item_lines(node.required_artifacts),
                "",
                "#### Execution contract",
                "",
                "- Capture the starting SHA before changing the worktree.",
                "- Make exactly one commit for this feature.",
                (
                    "- End the commit message with the exact trailer "
                    f"`GDDP-Node-Id: {node.node_id}`."
                ),
                (
                    "- After committing, run "
                    f"`gddp receipt --node-id {node.node_id} "
                    "--base <starting SHA> --result <commit SHA>`."
                ),
                (
                    "- This feature is not complete until that receipt command "
                    "exits successfully."
                ),
                (
                    "- Push this feature's commit immediately and only to the "
                    f"engagement work branch with `git push origin "
                    f"HEAD:refs/heads/{engagement_branch}`."
                ),
                "- Do not defer or batch this push with a later feature.",
                (
                    "- Never push to `main`, the repository default branch, "
                    "or any shared or release branch."
                ),
                (
                    "- Never force-push: do not use `--force`, `-f`, "
                    "`--force-with-lease`, a leading `+` refspec, or any other "
                    "non-fast-forward override."
                ),
                (
                    "- After the push, run "
                    "`git branch -r --contains <commit SHA>`; its output must "
                    f"list `origin/{engagement_branch}`."
                ),
                (
                    "- This feature is not complete and must not report "
                    "success until its own commit is reachable from that "
                    "origin ref."
                ),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def verify_planned_feature_ids(
    features_path: str | Path,
    demanded_node_ids: Sequence[str],
) -> PlanningVerification:
    """Compare Factory's planned feature ids with the demanded ordered ids."""
    demanded = tuple(demanded_node_ids)
    try:
        payload = json.loads(Path(features_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return PlanningVerification(
            proceed=False,
            demanded_ids=demanded,
            observed_ids=None,
            reason=f"Cannot verify planned feature ids: {exc}",
        )

    features = payload.get("features") if isinstance(payload, Mapping) else None
    if not isinstance(features, list):
        return PlanningVerification(
            proceed=False,
            demanded_ids=demanded,
            observed_ids=None,
            reason="Cannot verify planned feature ids: features must be a list",
        )

    observed_values: list[str] = []
    for feature in features:
        feature_id = feature.get("id") if isinstance(feature, Mapping) else None
        if not isinstance(feature_id, str):
            return PlanningVerification(
                proceed=False,
                demanded_ids=demanded,
                observed_ids=None,
                reason="Cannot verify planned feature ids: every feature needs a string id",
            )
        observed_values.append(feature_id)
    observed = tuple(observed_values)

    if observed == demanded:
        return PlanningVerification(
            proceed=True,
            demanded_ids=demanded,
            observed_ids=observed,
            reason="Planned feature ids exactly match demanded node ids",
        )
    return PlanningVerification(
        proceed=False,
        demanded_ids=demanded,
        observed_ids=observed,
        reason=(
            "Feature id drift requires human review: "
            f"demanded {list(demanded)!r}, observed {list(observed)!r}"
        ),
    )


def _default_mission_readiness(nodes: Sequence[NodeData]) -> tuple[str, ...]:
    """Select an explicit validation path without inventing repo commands."""
    if nodes and all(
        any("read-only" in str(item).casefold() for item in node.constraints)
        for node in nodes
    ):
        artifacts = [
            artifact
            for node in nodes
            for artifact in node.required_artifacts
        ]
        report_checks = " && ".join(
            f"test -s {shlex.quote(str(artifact))}" for artifact in artifacts
        )
        validation = " && ".join(
            part for part in (report_checks, "git diff --check") if part
        )
        return (
            *READ_ONLY_AUDIT_MISSION_READINESS,
            f"Validation command: `{validation}`.",
        )
    return DEFAULT_MISSION_READINESS


def _topological_nodes(nodes: Sequence[NodeData]) -> list[NodeData]:
    """Order selected nodes stably while ignoring dependencies outside the selection."""
    projected = list(nodes)
    by_id = {node.node_id: node for node in projected}
    if len(by_id) != len(projected):
        raise ValueError("duplicate node ids cannot be projected")

    selected_ids = set(by_id)
    indegree = {node.node_id: 0 for node in projected}
    dependents: dict[str, list[str]] = {node.node_id: [] for node in projected}
    for node in projected:
        for dependency in dict.fromkeys(node.depends_on):
            if dependency not in selected_ids:
                continue
            indegree[node.node_id] += 1
            dependents[dependency].append(node.node_id)

    ready = deque(
        node.node_id for node in projected if indegree[node.node_id] == 0
    )
    ordered: list[NodeData] = []
    while ready:
        node_id = ready.popleft()
        ordered.append(by_id[node_id])
        for dependent in dependents[node_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)

    if len(ordered) != len(projected):
        raise ValueError("selected graph contains a dependency cycle")
    return ordered


def _item_lines(items: Sequence[object]) -> list[str]:
    if not items:
        return ["- None supplied."]
    return [f"- {_render_item(item)}" for item in items]


def _render_item(item: object) -> str:
    if isinstance(item, str):
        return item
    # NodePacket freezes nested criteria/constraints as MappingProxyType +
    # tuples. Thaw at this exact dumps boundary so projection never leaks
    # frozen packet values into JSON serialization.
    if isinstance(item, Mapping | tuple):
        item = _thaw_json(item)  # type: ignore[arg-type]
    return json.dumps(item, ensure_ascii=False, sort_keys=True)
