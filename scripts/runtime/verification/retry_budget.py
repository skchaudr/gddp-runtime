"""Retry budget logic for the evaluator-to-executor retry loop.

When the evaluator produces a non-pass verdict with evidence-referenced
findings, and the project's retry budget has room, the return_router
re-dispatches the same node with findings injected into the issue body.

Budget check is ONE wrappable function so modes (V2) can replace the
heuristic later without touching the return_router.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any


# Heuristic: a finding has "evidence references" if its summary or the
# integrity output's reasoning mentions a file path (e.g. src/foo.py,
# lib/common.zsh, scripts/runtime/bridge.py) or a line reference (foo.py:42).
_FILE_REF_RE = re.compile(r'[\w/]+\.\w+(?::\d+)?')


def has_evidence_references(integrity_output: dict | None) -> bool:
    """Check whether integrity findings contain actionable evidence references.

    Findings without evidence references (e.g. "the code feels wrong") route
    to awaiting_review, never retry — the executor needs something concrete
    to fix.
    """
    if integrity_output is None:
        return False

    # Check findings' summaries
    findings = integrity_output.get("findings", [])
    for finding in findings:
        summary = finding.get("summary", "") if isinstance(finding, dict) else str(finding)
        if _FILE_REF_RE.search(summary):
            return True

    # Check the integrity output's reasoning
    reasoning = integrity_output.get("reasoning", "")
    if reasoning and _FILE_REF_RE.search(reasoning):
        return True

    return False


def should_retry(
    *,
    verdict: str,
    integrity: dict | None,
    job: dict,
    project_yaml: dict,
) -> bool:
    """Determine whether a non-pass verdict should trigger an executor retry.

    Conditions (all must be true):
    1. Combined verdict is non-pass (not "pass")
    2. Integrity findings have evidence references
    3. retry_budget > 0 (project-level, human-owned in project.yaml)
    4. attempt < max_attempts (existing columns on jobs table)

    Returns True if the job should be re-dispatched, False if it should
    route to awaiting_review.
    """
    if verdict == "pass":
        return False

    if not has_evidence_references(integrity):
        return False

    execution_policy = project_yaml.get("execution_policy", {})
    retry_budget = execution_policy.get("retry_budget", 0)
    if retry_budget <= 0:
        return False

    attempt = job.get("attempt", 0)
    max_attempts = job.get("max_attempts", 3)
    if attempt >= max_attempts:
        return False

    return True
