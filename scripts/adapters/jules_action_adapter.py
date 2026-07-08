"""
jules_action_adapter.py — Option A dispatch adapter.

Dispatches a job to Jules by creating a GitHub issue with the `jules` label.
The jules-action in the target repo detects the label and triggers Jules.

Requires:
    - gh CLI installed
    - GITHUB_TOKEN or GH_TOKEN set to a GitHub PAT with issue write access

Usage:
    from adapters.jules_action_adapter import JulesActionAdapter
    adapter = JulesActionAdapter(repo="skchaudr/test-project")
    result = adapter.dispatch(job)
"""

import json
import os
import subprocess
from dataclasses import dataclass


def _flatten(item) -> str:
    """Convert any YAML value (str, dict, list) to a readable string."""
    if isinstance(item, dict):
        # e.g. {'method returns a dict with': 'key1, key2'} → 'method returns a dict with: key1, key2'
        return " — ".join(f"{k}: {v}" for k, v in item.items())
    if isinstance(item, list):
        return ", ".join(str(i) for i in item)
    return str(item)


@dataclass
class DispatchResult:
    success: bool
    issue_url: str | None
    issue_number: int | None
    error: str | None


class JulesActionAdapter:
    """
    Dispatches a job to Jules via a GitHub issue labeled 'jules'.
    Jules's GitHub Action detects the label and runs the task.
    """

    def __init__(self, repo: str):
        self.repo = repo

    @staticmethod
    def _github_token() -> str | None:
        return os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

    def build_issue_body(self, job: dict) -> str:
        """
        Format the job packet as a structured issue body.
        Jules reads this as its task instructions.
        """
        constraints = json.loads(job.get("constraints") or "[]")
        criteria    = json.loads(job.get("acceptance_criteria") or "[]")

        constraints_text = "\n".join(f"- {_flatten(c)}" for c in constraints)
        criteria_text    = "\n".join(f"- [ ] {_flatten(c)}" for c in criteria)

        findings = job.get("_previous_findings")
        findings_section = ""
        if findings:
            findings_list = "\n".join(
                f"- [{f.get('severity', '?')}] {f.get('summary', '')}"
                for f in findings.get("findings", [])
            )
            findings_section = f"""
## Previous Attempt Findings (attempt {job.get('attempt', 0)})

The previous implementation was reviewed and the following issues were found:

**Verdict:** {findings.get('verdict', 'unknown')}
**Integrity verdict:** {findings.get('integrity_verdict', 'unknown')}
**Reasoning:** {findings.get('reasoning', '')}

### Findings
{findings_list}

Please address these findings in your implementation.
"""

        return f"""## Goal
{job['goal']}

## Why
{job['why']}

## Constraints
{constraints_text}

## Acceptance Criteria
{criteria_text}
{findings_section}
## Output Requirements
- Implement the change
- Add or update tests
- Open a PR with a clear summary of the implementation choice
- Note any ambiguity or remaining risks
- **Required: include the following metadata block verbatim at the end of the PR description:**

```
node: {job['node_id']}
job: {job['job_id']}
```

This block is parsed by the GDDP return router to create a structured review receipt when the PR merges. It does not advance graph truth automatically. Missing or malformed metadata prevents the runtime from linking the PR back to the job for review.

---
*Dispatched by GDDP control plane — job_id: {job['job_id']} — node: {job['node_id']}*
"""

    def dispatch(self, job: dict) -> DispatchResult:
        token = self._github_token()
        if not token:
            return DispatchResult(
                success=False,
                issue_url=None,
                issue_number=None,
                error="Missing GitHub token: set GITHUB_TOKEN or GH_TOKEN",
            )

        title = f"[GDDP] {job['title']}"
        body  = self.build_issue_body(job)

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
                    issue_url=None,
                    issue_number=None,
                    error=result.stderr.strip(),
                )
            # gh issue create prints the issue URL on success
            issue_url    = result.stdout.strip()
            issue_number = int(issue_url.rstrip("/").split("/")[-1])
            return DispatchResult(
                success=True,
                issue_url=issue_url,
                issue_number=issue_number,
                error=None,
            )
        except subprocess.TimeoutExpired:
            return DispatchResult(
                success=False, issue_url=None, issue_number=None,
                error="gh CLI timed out"
            )
        except Exception as e:
            return DispatchResult(
                success=False, issue_url=None, issue_number=None,
                error=str(e)
            )
