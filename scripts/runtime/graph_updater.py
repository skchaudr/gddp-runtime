"""
graph_updater.py — Opens evidence-packaged PRs against gddp-config.

The decision loop never mutates graph truth directly. When a node passes
review, the loop calls open_evidence_pr() to propose the change as a PR
against gddp-config. A human merges, or doesn't.

This replaces the previous disabled-stub design where runtime was permanently
blocked from advancing graph state. The proposal model lets the system go
live from day one: machines propose, humans approve.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def open_evidence_pr(
    node_id: str,
    project_id: str,
    source_pr_number: int,
    source_pr_url: str,
    evidence: Dict[str, Any],
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Open a PR against gddp-config proposing to mark `node_id` complete.

    The PR body carries the full evidence packet: acceptance criteria verdicts,
    scope verification, test status, and a link back to the source PR. The
    human reading the PR has everything they need to approve or decline.

    Returns:
        {"ok": True, "evidence_pr_url": "...", "evidence_pr_number": 42}
        {"ok": False, "reason": "..."}
    """
    gddp_config_path = _resolve_config_path(config_path)

    evidence_block = _format_evidence_block(
        node_id=node_id,
        project_id=project_id,
        source_pr_number=source_pr_number,
        source_pr_url=source_pr_url,
        evidence=evidence,
    )

    branch_name = f"evidence/{project_id}/{node_id}-complete"

    try:
        _ensure_config_repo_clean(gddp_config_path)

        # Create or reset the evidence branch from main
        subprocess.run(
            ["git", "-C", str(gddp_config_path), "checkout", "main"],
            capture_output=True, text=True, timeout=15,
        )
        subprocess.run(
            ["git", "-C", str(gddp_config_path), "branch", "-D", branch_name],
            capture_output=True, text=True, timeout=15,
        )
        subprocess.run(
            ["git", "-C", str(gddp_config_path), "checkout", "-b", branch_name],
            capture_output=True, text=True, timeout=15,
        )

        # Update the node YAML
        _mark_node_complete_in_yaml(gddp_config_path, project_id, node_id, source_pr_number)

        # Commit and push
        subprocess.run(
            ["git", "-C", str(gddp_config_path), "add", "."],
            capture_output=True, text=True, timeout=15,
        )
        commit_msg = f"evidence: propose {node_id} complete (PR #{source_pr_number})"
        result = subprocess.run(
            ["git", "-C", str(gddp_config_path), "commit", "-m", commit_msg],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            # No changes to commit — node might already be complete
            return {
                "ok": False,
                "reason": f"no_changes_to_commit: node {node_id} may already be complete",
            }

        subprocess.run(
            ["git", "-C", str(gddp_config_path), "push", "-u", "origin", branch_name, "--force"],
            capture_output=True, text=True, timeout=30,
        )

        # Open the PR via gh CLI
        pr_title = f"Evidence: mark {project_id}/{node_id} as complete"
        pr_body = evidence_block

        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--repo", _config_repo_slug(),
                "--title", pr_title,
                "--body", pr_body,
                "--base", "main",
                "--head", branch_name,
            ],
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode != 0:
            return {
                "ok": False,
                "reason": f"gh_pr_create_failed: {result.stderr.strip()}",
            }

        pr_url = result.stdout.strip()
        pr_number = int(pr_url.rstrip("/").split("/")[-1])

        # Return to main
        subprocess.run(
            ["git", "-C", str(gddp_config_path), "checkout", "main"],
            capture_output=True, text=True, timeout=15,
        )

        return {
            "ok": True,
            "evidence_pr_url": pr_url,
            "evidence_pr_number": pr_number,
        }

    except subprocess.TimeoutExpired as e:
        return {"ok": False, "reason": f"timeout: {e}"}
    except Exception as e:
        return {"ok": False, "reason": f"exception: {e}"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_config_path(config_path: Optional[str]) -> Path:
    if config_path:
        return Path(config_path)
    env_path = os.environ.get("GDDP_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    raise FileNotFoundError(
        "GDDP_CONFIG_PATH not set and no config_path argument provided"
    )


def _config_repo_slug() -> str:
    return os.environ.get("GDDP_CONFIG_REPO", "skchaudr/gddp-config")


def _ensure_config_repo_clean(config_path: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(config_path), "status", "--porcelain"],
        capture_output=True, text=True, timeout=10,
    )
    if result.stdout.strip():
        raise RuntimeError(
            f"gddp-config working tree is dirty — aborting evidence PR: {result.stdout.strip()}"
        )


def _mark_node_complete_in_yaml(
    config_path: Path, project_id: str, node_id: str, source_pr_number: int
) -> None:
    """Set status: complete in the project.yaml nodes list for this node."""
    project_yaml = config_path / "graphs" / project_id / "project.yaml"
    if not project_yaml.exists():
        raise FileNotFoundError(f"project.yaml not found: {project_yaml}")

    lines = project_yaml.read_text().splitlines()
    new_lines = []
    in_target_node = False

    for line in lines:
        if not in_target_node and line.strip() == f"- id: {node_id}":
            in_target_node = True
            new_lines.append(line)
            continue

        if in_target_node and line.strip().startswith("status:") and "complete" not in line:
            new_lines.append(f"    status: complete  # evidence PR: #{source_pr_number}")
            continue

        if in_target_node and line.strip().startswith("- id:"):
            in_target_node = False

        new_lines.append(line)

    project_yaml.write_text("\n".join(new_lines) + "\n")


def _format_evidence_block(
    node_id: str,
    project_id: str,
    source_pr_number: int,
    source_pr_url: str,
    evidence: Dict[str, Any],
) -> str:
    """Format the evidence packet as a markdown PR body."""
    acceptance = evidence.get("acceptance_check", [])
    scope = evidence.get("scope_verification", {})
    tests = evidence.get("test_status", {})
    risks = evidence.get("risks", "")

    acceptance_lines = ""
    if isinstance(acceptance, list):
        for item in acceptance:
            if isinstance(item, dict):
                status_icon = "PASS" if item.get("passed") else "FAIL"
                acceptance_lines += f"- [{status_icon}] {item.get('criterion', item.get('name', str(item)))}\n"
            else:
                acceptance_lines += f"- [ ] {item}\n"
    elif isinstance(acceptance, str):
        acceptance_lines = acceptance

    scope_summary = ""
    if isinstance(scope, dict):
        in_scope = scope.get("in_scope", [])
        out_of_scope = scope.get("out_of_scope", [])
        scope_summary = f"**In scope:** {', '.join(in_scope) if in_scope else 'none'}\n"
        if out_of_scope:
            scope_summary += f"**Out of scope (untouched):** {', '.join(out_of_scope)}\n"

    tests_summary = ""
    if isinstance(tests, dict):
        tests_summary = f"**Tests passed:** {tests.get('passed', tests.get('overall', 'unknown'))}\n"

    risks_section = ""
    if risks:
        risks_section = f"## Risks\n{risks}\n"

    return f"""## Evidence Packet

**Node:** `{node_id}`
**Project:** `{project_id}`
**Source PR:** [#{source_pr_number}]({source_pr_url})

---

## Acceptance Criteria

{acceptance_lines}

## Scope Verification

{scope_summary}
{tests_summary}
{risks_section}
## Decision

This PR proposes marking `{project_id}/{node_id}` as **complete** based on the
evidence above. The decision loop produced this proposal. The human decides.

**Action:** Review the evidence. Merge to advance the graph, or close to reject.

---
*Generated by gddp-runtime graph_updater — machine proposes, human approves.*
"""


# ---------------------------------------------------------------------------
# Legacy compatibility stub
# ---------------------------------------------------------------------------

def update_graph_node_complete(*_args, **_kwargs) -> Dict[str, Any]:
    """
    Legacy compatibility stub. Superseded by open_evidence_pr().

    Returns a disabled response — direct graph mutation is not supported.
    Use open_evidence_pr() to propose changes via PR.
    """
    return {
        "ok": False,
        "reason": "graph_mutation_disabled_use_open_evidence_pr",
    }
