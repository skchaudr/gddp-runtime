"""Neutral session/issue instruction rendering for executor adapters.

Owned by neither Jules transport. API (and any other direct transport) builds
the operator-facing prompt here so adapters do not borrow helpers across
transport modules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from adapters.executor_protocol import NodePacket


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

    header = f"[GDDP] {packet.title}" if packet.title else "GDDP task"
    return (
        f"{header}\n\n"
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
