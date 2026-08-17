"""Neutral session/issue instruction rendering for executor adapters.

Owned by neither Jules transport. API (and any other direct transport) builds
the operator-facing prompt here so adapters do not borrow helpers across
transport modules.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from adapters.executor_protocol import NodePacket

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
)
_VOLATILE_PROMPT_KEYS = (
    "job_id",
    "execution_attempt_id",
    "attempt_index",
    "expected_base_commit_sha",
    "previous_findings",
)


def split_packet_zones(packet: Mapping[str, object]) -> tuple[str, str]:
    """Split a transport packet mapping into (stable, volatile) JSON zones.

    The stable zone is byte-identical across retries of the same node, so a
    retry reuses the cached prefix instead of re-billing the whole packet.
    Unknown keys fall into the volatile zone so a future packet field is never
    silently dropped from the prompt.
    """

    def _dump(keys: tuple[str, ...]) -> str:
        return json.dumps(
            {key: packet[key] for key in keys if key in packet},
            sort_keys=False,
            separators=(",", ":"),
        )

    known = set(_STABLE_PROMPT_KEYS) | set(_VOLATILE_PROMPT_KEYS)
    extra = tuple(sorted(key for key in packet if key not in known))
    return _dump(_STABLE_PROMPT_KEYS), _dump(_VOLATILE_PROMPT_KEYS + extra)


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
