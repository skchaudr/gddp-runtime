"""Neutral session/issue instruction rendering for executor adapters.

Owned by neither Jules transport. API (and any other direct transport) builds
the operator-facing prompt here so adapters do not borrow helpers across
transport modules.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from adapters.executor_protocol import NodePacket
from prompt_topology import TurnPrompt

# Prefix caching only discounts a byte-identical prompt prefix. Per-attempt
# identifiers must therefore be serialized AFTER the node content, never sorted
# into the middle of it (which is what json.dumps(sort_keys=True) does: it
# hoists attempt_index and execution_attempt_id to keys 2 and 4). Key order
# below is explicit and load-bearing — do not alphabetize.
_STABLE_PROMPT_KEYS = (
    "node_id",
    "title",
    "goal",
    "why",
    "constraints",
    "acceptance_criteria",
    "required_artifacts",
    "depends_on",
    "unlocks",
)
_VOLATILE_PROMPT_KEYS = (
    "job_id",
    "execution_attempt_id",
    "attempt_index",
    "expected_base_commit_sha",
    "previous_findings",
)
# Rendered as text in the prompt's PROJECT zone (least volatile, ahead of the
# node zone). Keeping it out of both JSON zones avoids duplicating it into the
# volatile tail, where a graph-stable pointer list does not belong.
_PROJECT_ZONE_KEYS = ("context_pointers",)


def split_packet_zones(packet: Mapping[str, object]) -> tuple[str, str]:
    """Split a transport packet mapping into (stable, volatile) JSON zones.

    The stable zone is byte-identical across retries of the same node, so a
    retry reuses the cached prefix instead of re-billing the whole packet.
    Unknown keys fall into the volatile zone so a future packet field is never
    silently dropped from the prompt; ``_PROJECT_ZONE_KEYS`` are the exception,
    rendered separately ahead of both zones.
    """

    def _dump(keys: tuple[str, ...]) -> str:
        return json.dumps(
            {key: packet[key] for key in keys if key in packet},
            sort_keys=False,
            separators=(",", ":"),
        )

    known = (
        set(_STABLE_PROMPT_KEYS)
        | set(_VOLATILE_PROMPT_KEYS)
        | set(_PROJECT_ZONE_KEYS)
    )
    extra = tuple(sorted(key for key in packet if key not in known))
    return _dump(_STABLE_PROMPT_KEYS), _dump(_VOLATILE_PROMPT_KEYS + extra)


_POINTER_HEADER = (
    "Project context pointers (read these files; a read is evidence, an "
    "embedded blob is not):"
)


def merged_turn_pointers(packets: Sequence[Mapping[str, object]]) -> dict[str, str]:
    """Union of the packets' context_pointers — what one turn actually offers.

    First writer wins per key, so a batch turn offering the same key from two
    packets renders (and is measured against) one value.
    """
    pointers: dict[str, str] = {}
    for packet in packets:
        carried = packet.get("context_pointers")
        if not isinstance(carried, Mapping):
            continue
        for key, value in carried.items():
            pointers.setdefault(str(key), str(value))
    return pointers


def build_project_zone(packets: Sequence[Mapping[str, object]]) -> str:
    """Render the packets' canonical context pointers as the project zone.

    Paths only — never file contents. Sorted by key so the block is
    byte-identical across retries of the same packet(s), and empty when no
    packet carries pointers (old packets, unreachable gddp-config), which
    leaves the zone absent rather than failing the turn. UNAVAILABLE markers
    are passed through verbatim: knowing a canonical doc is missing is
    context too.
    """
    pointers = merged_turn_pointers(packets)
    if not pointers:
        return ""
    lines = [f"{key}: {pointers[key]}" for key in sorted(pointers)]
    return "\n".join([_POINTER_HEADER, *lines])


def build_turn_prompt(
    *,
    worktree: Path,
    packets: Sequence[Mapping[str, object]],
    preamble: str,
    turn_note: str,
) -> TurnPrompt:
    """Four-zone TurnPrompt for one executor turn, on any transport.

    protocol  = the transport's protocol text (nearly immutable, shared by
                every turn on that transport)
    project   = canonical context pointers for this node's project (paths
                only, graph-stable — see build_project_zone); empty when the
                packet carries none
    node      = stable node JSON blocks (retry-stable per node)
    attempt   = volatile envelopes (attempt ids + worktree) + turn note

    Emitting protocol->project->node->attempt means a retry of the same node
    reuses protocol+project+node and a sibling node in the same project
    reuses protocol+project.

    ``preamble`` and ``turn_note`` are parameters rather than constants
    because the protocol zone is where a harness's own capabilities show up:
    pi's text instructs subagent fan-out, which an executor that declares
    native_subagents=False must not be told to do. Zone assembly itself is
    GDDP policy and identical for every transport.
    """
    node_blocks: list[str] = []
    envelopes: list[str] = []
    for idx, packet in enumerate(packets, start=1):
        stable_zone, volatile_zone = split_packet_zones(packet)
        node_blocks.append(
            f"### NODE {idx} (authoritative GDDP NodePacket)\n{stable_zone}"
        )
        envelopes.append(
            f"### ATTEMPT ENVELOPE {idx}\n{volatile_zone}\n"
            f"worktree_path: {worktree}"
        )
    return TurnPrompt(
        protocol=preamble,
        project=build_project_zone(packets),
        node="\n\n".join(node_blocks),
        attempt="\n\n".join(envelopes) + f"\n\n{turn_note}\n",
    )


def flatten(item) -> str:
    """Convert an immutable packet value to readable text."""
    if isinstance(item, Mapping):
        return " — ".join(f"{key}: {value}" for key, value in item.items())
    if isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
        return ", ".join(str(value) for value in item)
    return str(item)


def build_session_instructions(packet: NodePacket) -> str:
    """Build the neutral instruction string for a Jules session (or equivalent)."""
    constraints_text = "\n".join(
        f"- {flatten(constraint)}" for constraint in packet.constraints
    )
    criteria_text = "\n".join(
        f"- [ ] {flatten(criterion)}" for criterion in packet.acceptance_criteria
    )

    artifacts_section = ""
    if packet.required_artifacts:
        artifacts_text = "\n".join(
            f"- `{artifact}`" for artifact in packet.required_artifacts
        )
        artifacts_section = (
            "\n## Required Artifacts\n"
            "The result must include:\n"
            f"{artifacts_text}\n"
        )

    findings_section = ""
    findings = packet.previous_findings
    if findings:
        raw_findings = findings.get("findings", ())
        findings_list = "\n".join(
            (
                f"- [{finding.get('severity', '?')}] "
                f"{finding.get('summary', '')}"
            )
            for finding in raw_findings
            if isinstance(finding, Mapping)
        )
        raw_criteria_findings = findings.get("criteria_findings", ())
        criteria_findings_list = "\n".join(
            (
                f"- [{finding.get('judgment', '?')}] "
                f"{finding.get('criterion_id', '')}\n"
                f"  Reasoning: {finding.get('reasoning', '')}\n"
                f"  Evidence: {flatten(finding.get('evidence', ()))}"
            )
            for finding in raw_criteria_findings
            if isinstance(finding, Mapping)
        )
        findings_section = (
            f"\n## Previous Attempt Findings (attempt {packet.attempt_index})\n"
            f"**Verdict:** {findings.get('verdict', 'unknown')}\n"
            f"**Integrity verdict:** "
            f"{findings.get('integrity_verdict', 'unknown')}\n"
            f"**Reasoning:** {findings.get('reasoning', '')}\n\n"
            f"### Findings\n{findings_list}\n"
            f"\n### Criteria Findings\n{criteria_findings_list}\n"
        )

    # Byte-stable across every node and project so the framing text below it
    # can share a cached prefix. The node title lives in the body instead.
    header = "[GDDP] node execution request"
    title_line = f"## Node\n{packet.title}\n\n" if packet.title else ""
    return (
        f"{header}\n\n"
        f"{title_line}"
        f"## Goal\n{packet.goal}\n\n"
        f"## Why\n{packet.why}\n\n"
        f"## Constraints\n{constraints_text}\n\n"
        f"## Acceptance Criteria\n{criteria_text}\n"
        f"{artifacts_section}"
        f"{findings_section}\n"
        f"---\n"
        f"node: {packet.node_id}\n"
        f"job: {packet.job_id}\n"
        f"attempt: {packet.attempt_index}\n"
        f"execution_attempt_id: {packet.execution_attempt_id}\n"
    )
