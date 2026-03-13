"""
jules_action_adapter.py — Option A dispatch adapter.

Dispatches a job to Jules by creating a GitHub issue with the `jules` label.
The jules-action in the target repo detects the label and triggers Jules.

Requires: gh CLI authenticated (gh auth status)

Usage:
    from adapters.jules_action_adapter import JulesActionAdapter
    adapter = JulesActionAdapter(repo="skchaudr/test-project")
    result = adapter.dispatch(job)
"""

import json
import subprocess
from dataclasses import dataclass


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

    def build_issue_body(self, job: dict) -> str:
        """
        Format the job packet as a structured issue body.
        Jules reads this as its task instructions.
        """
        constraints = json.loads(job.get("constraints") or "[]")
        criteria    = json.loads(job.get("acceptance_criteria") or "[]")

        constraints_text = "\n".join(f"- {c}" for c in constraints)
        criteria_text    = "\n".join(f"- [ ] {c}" for c in criteria)

        return f"""## Goal
{job['goal']}

## Why
{job['why']}

## Constraints
{constraints_text}

## Acceptance Criteria
{criteria_text}

## Output Requirements
- Implement the change
- Add or update tests
- Open a PR with a clear summary of the implementation choice
- Note any ambiguity or remaining risks

---
*Dispatched by GDAD control plane — job_id: {job['job_id']} — node: {job['node_id']}*
"""

    def dispatch(self, job: dict) -> DispatchResult:
        title = f"[GDAD] {job['title']}"
        body  = self.build_issue_body(job)

        cmd = [
            "gh", "issue", "create",
            "--repo",  self.repo,
            "--title", title,
            "--body",  body,
            "--label", "jules",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
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
