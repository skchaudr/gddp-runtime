"""
jules_action_adapter.py — Option A dispatch adapter.

Dispatches a job to Jules by creating a GitHub issue with the `jules` label.
The jules-action in the target repo detects the label and triggers Jules.

Requires:
    - gh CLI installed
    - GITHUB_TOKEN/GH_TOKEN set, or gh CLI authenticated with issue write access

Usage:
    from adapters.jules_action_adapter import JulesActionAdapter
    adapter = JulesActionAdapter(repo="skchaudr/test-project")
    result = adapter.dispatch(job)
"""

import os
import subprocess
from collections.abc import Mapping, Sequence

from adapters.executor_protocol import DispatchResult, NodePacket


def _flatten(item) -> str:
    """Convert an immutable packet value to readable text."""
    if isinstance(item, Mapping):
        return " — ".join(f"{key}: {value}" for key, value in item.items())
    if isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
        return ", ".join(str(value) for value in item)
    return str(item)




class JulesActionAdapter:
    """
    Dispatches a job to Jules via a GitHub issue labeled 'jules'.
    Jules's GitHub Action detects the label and runs the task.
    """

    def __init__(self, repo: str):
        self.repo = repo

    @staticmethod
    def _github_token() -> str | None:
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if token:
            return token

        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def build_issue_body(self, packet: NodePacket) -> str:
        """Format one immutable node attempt as structured issue instructions."""
        constraints_text = "\n".join(
            f"- {_flatten(constraint)}" for constraint in packet.constraints
        )
        criteria_text = "\n".join(
            f"- [ ] {_flatten(criterion)}"
            for criterion in packet.acceptance_criteria
        )

        findings = packet.previous_findings
        findings_section = ""
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
            findings_section = f"""
## Previous Attempt Findings (attempt {packet.attempt_index})

The previous implementation was reviewed and the following issues were found:

**Verdict:** {findings.get('verdict', 'unknown')}
**Integrity verdict:** {findings.get('integrity_verdict', 'unknown')}
**Reasoning:** {findings.get('reasoning', '')}

### Findings
{findings_list}

Please address these findings in your implementation.
"""

        artifacts_section = ""
        if packet.required_artifacts:
            artifacts_text = "\n".join(
                f"- `{artifact}`" for artifact in packet.required_artifacts
            )
            artifacts_section = f"""
## Required Artifacts
Your PR must include the following files in the repo root:
{artifacts_text}

These files are checked by the deterministic verification gate. Missing artifacts will cause the job to fail verification and be re-dispatched. Include all of them in your PR.

(Alternative: a single `executor-receipt.md` covering the rationale, summary, and diff overview is also accepted.)
"""

        metadata_reminder = (
            f"\n"
            f"---\n"
            f"*Dispatched by GDDP control plane — job_id: {packet.job_id} — "
            f"node: {packet.node_id} — attempt: {packet.attempt_index}*\n"
            f"\n"
            f"**CRITICAL — PR Metadata Block Required:**\n"
            f"Your PR description MUST end with this exact block:\n"
            f"```\n"
            f"node: {packet.node_id}\n"
            f"job: {packet.job_id}\n"
            f"attempt: {packet.attempt_index}\n"
            f"```\n"
            f"Without this block, the GDDP return router cannot link your PR back to this job. "
            f"The PR will be rejected and the work will not be reviewed. This is not optional.\n"
        )

        return f"""## Goal
{packet.goal}

## Why
{packet.why}

## Constraints
{constraints_text}

## Acceptance Criteria
{criteria_text}
{artifacts_section}
{findings_section}
## Output Requirements
- Implement the change
- Add or update tests
- Open a PR with a clear summary of the implementation choice
- Note any ambiguity or remaining risks
- **Required: include the following metadata block verbatim at the end of the PR description:**

```
node: {packet.node_id}
job: {packet.job_id}
attempt: {packet.attempt_index}
```

This block is parsed by the GDDP return router to create a structured review receipt when the PR merges. It does not advance graph truth automatically. Missing or malformed metadata prevents the runtime from linking the PR back to the job for review.
{metadata_reminder}"""

    def dispatch(self, packet: NodePacket) -> DispatchResult:
        token = self._github_token()
        if not token:
            return DispatchResult(
                success=False,
                error="Missing GitHub token: set GITHUB_TOKEN/GH_TOKEN or authenticate gh",
            )

        title = f"[GDDP] {packet.title}"
        body = self.build_issue_body(packet)

        cmd = [
            "gh", "issue", "create",
            "--repo",  self.repo,
            "--title", title,
            "--body",  body,
            "--label", "jules",
        ]

        try:
            env = os.environ.copy()
            # Pass auth explicitly so dispatch does not depend on ambient gh login state.
            env["GH_TOKEN"] = token
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            if result.returncode != 0:
                return DispatchResult(
                    success=False,
                    error=result.stderr.strip(),
                )
            # gh issue create prints the issue URL on success.
            issue_url = result.stdout.strip()
            return DispatchResult(success=True, issue_url=issue_url)
        except subprocess.TimeoutExpired:
            return DispatchResult(success=False, error="gh CLI timed out")
        except Exception as e:
            return DispatchResult(success=False, error=str(e))
