"""
run_verification.py — verification pipeline.

Verification pipeline: receipt in, verdict out. No state, no persistence between calls.
It discovers jobs awaiting review, gathers data, runs structural
validation, derives a verdict, and proposes graph advancement when
the verdict is ACCEPT.

In this wave (Task 3), the semantic evaluator is not yet wired in —
decide() is always called with semantic=None. Task 4 will plug in
the semantic evaluator by changing one line.
"""

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import yaml

from .graph_updater import open_evidence_pr
from .results_store import DB_PATH
from .review_queue import claim_for_verification, complete_verification
from .verification.decision_engine import decide
from .verification.structural import run_structural_validator


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_verification(result_id: str, config_path: str | None = None) -> dict:
    """Main entry point. Run verification for one result.

    Returns {"ok": True, "verdict": ..., ...} on success.
    Returns {"ok": False, "error": str} on any failure.
    Never raises — always returns a dict.
    """
    try:
        # 1. Load receipt
        receipt = _load_receipt(result_id)
        if receipt is None:
            return {"ok": False, "error": f"Result not found: {result_id}"}

        # 2. Claim for verification
        if not claim_for_verification(result_id):
            return {"ok": False, "error": f"Could not claim {result_id} for verification"}

        # 3. Parse github_action for PR metadata
        gh_data = _parse_github_action(receipt)
        if gh_data is None:
            return {"ok": False, "error": f"No github_action data in {result_id}"}

        node_id = gh_data.get("node_id")
        repo_name = gh_data.get("repo_name")
        pr_number = gh_data.get("pr_number")
        merged_pr_url = gh_data.get("merged_pr_url", "")

        if not node_id or not repo_name or not pr_number:
            return {"ok": False, "error": f"Missing PR metadata in {result_id}"}

        # 4. Resolve gddp-config path
        resolved_config = _resolve_config_path(config_path)
        if resolved_config is None:
            return {"ok": False, "error": "gddp-config path not resolved"}

        # 5. Infer project ID and load node spec
        project_id = _infer_project_id(repo_name, resolved_config)
        node_spec = load_node_spec(project_id, node_id, str(resolved_config))

        # 6. Load project graph
        graph = _load_project_graph(project_id, str(resolved_config))

        # 7. Gather changed files from PR
        changed_files = gather_changed_files(repo_name, str(pr_number))

        # 8. Build acceptance lists
        acceptance_before = node_spec.get("acceptance", [])
        acceptance_after = node_spec.get("acceptance", [])  # v0: same as before

        # 9. Run structural validator
        structural_output = run_structural_validator(
            graph=graph,
            node=node_spec,
            changed_files=changed_files,
            present_paths=changed_files,  # v0: PR file list as proxy
            acceptance_before=acceptance_before,
            acceptance_after=acceptance_after,
        )

        # 10. Derive verdict
        verdict = decide(structural_output, semantic=None)

        # 11. Persist verdict
        structural_results = [r.model_dump() for r in structural_output.results]
        complete_verification(
            result_id=result_id,
            verdict=verdict.verdict,
            reason=verdict.reason,
            severity=verdict.severity,
            matrix_row=verdict.matrix_row,
            structural_passed=structural_output.all_passed,
            structural_results=structural_results,
        )

        # 12. If ACCEPT, propose graph advancement
        if verdict.verdict == "ACCEPT":
            evidence = _build_evidence(structural_output, verdict, changed_files)
            open_evidence_pr(
                node_id=node_id,
                project_id=project_id,
                source_pr_number=int(pr_number),
                source_pr_url=merged_pr_url,
                evidence=evidence,
                config_path=str(resolved_config),
            )

        return {
            "ok": True,
            "verdict": verdict.verdict,
            "reason": verdict.reason,
            "matrix_row": verdict.matrix_row,
            "result_id": result_id,
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Public helpers (testable in isolation)
# ---------------------------------------------------------------------------

def load_node_spec(project_id: str, node_id: str, config_path: str) -> dict:
    """Read the node YAML from gddp-config.

    Looks for: config_path / graphs / project_id / nodes / node_id.yaml
    Falls back to inline node spec in project.yaml.

    Returns dict (possibly empty if nothing found).
    """
    node_file = Path(config_path) / "graphs" / project_id / "nodes" / f"{node_id}.yaml"
    if node_file.exists():
        with open(node_file) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data

    project_file = Path(config_path) / "graphs" / project_id / "project.yaml"
    if project_file.exists():
        with open(project_file) as f:
            project = yaml.safe_load(f)
        if isinstance(project, dict):
            for node in project.get("nodes", []):
                if isinstance(node, dict) and node.get("id") == node_id:
                    return node

    return {}


def gather_changed_files(repo_name: str, pr_number: str) -> list[str]:
    """Get the list of files changed in a PR via gh CLI.

    Runs: gh pr diff --name-only --repo repo_name pr_number
    Returns list of file paths, or [] on any failure.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", "--name-only", "--repo", repo_name, str(pr_number)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        return []
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_receipt(result_id: str) -> dict | None:
    """Load a result row from the results table."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM results WHERE result_id = ?", (result_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def _parse_github_action(receipt: dict) -> dict | None:
    """Parse the github_action JSON from a receipt row."""
    raw = receipt.get("github_action")
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def _resolve_config_path(config_path: str | None) -> Path | None:
    """Resolve the gddp-config path from arg, env, or sibling repo."""
    if config_path:
        p = Path(config_path)
        if p.exists():
            return p
    env_path = os.environ.get("GDDP_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
    sibling = Path(__file__).parent.parent.parent.parent / "gddp-config"
    if sibling.exists():
        return sibling
    return None


def _infer_project_id(repo_name: str, config_path: Path) -> str:
    """Infer the project ID from repo name by scanning gddp-config graphs."""
    graphs_dir = config_path / "graphs"
    if graphs_dir.exists():
        for project_dir in graphs_dir.iterdir():
            if project_dir.is_dir():
                project_file = project_dir / "project.yaml"
                if project_file.exists():
                    with open(project_file) as f:
                        project = yaml.safe_load(f)
                    if isinstance(project, dict) and project.get("repo") == repo_name:
                        return project_dir.name
    return repo_name.split("/")[-1]


def _load_project_graph(project_id: str, config_path: str) -> dict:
    """Load the project graph as a nodes dict from gddp-config."""
    project_file = Path(config_path) / "graphs" / project_id / "project.yaml"
    if not project_file.exists():
        return {"nodes": {}}

    with open(project_file) as f:
        project = yaml.safe_load(f)

    if not isinstance(project, dict):
        return {"nodes": {}}

    nodes = {}
    for node in project.get("nodes", []):
        if isinstance(node, dict) and "id" in node:
            nodes[node["id"]] = node

    return {"nodes": nodes}


def _build_evidence(structural_output, verdict, changed_files: list[str]) -> dict:
    """Build evidence packet for graph_updater.open_evidence_pr()."""
    return {
        "acceptance_check": [
            {"name": r.check, "passed": r.passed, "evidence": r.evidence}
            for r in structural_output.results
        ],
        "scope_verification": {
            "in_scope": changed_files,
            "out_of_scope": [],
        },
        "test_status": {
            "overall": "passed" if structural_output.all_passed else "failed",
        },
        "risks": (
            f"Verdict: {verdict.verdict}, "
            f"reason: {verdict.reason}, "
            f"severity: {verdict.severity}"
        ),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="runtime.run_verification",
        description="GDDP verification pipeline — run structural verification on review receipts.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--poll",
        action="store_true",
        help="List all results awaiting verification review.",
    )
    group.add_argument(
        "--result-id",
        type=str,
        help="Run verification on a specific result.",
    )
    parser.add_argument(
        "--config-path",
        type=str,
        default=None,
        help="Path to gddp-config repo (or set GDDP_CONFIG_PATH).",
    )
    args = parser.parse_args()

    if args.poll:
        from .review_queue import poll_awaiting_review

        jobs = poll_awaiting_review()
        if not jobs:
            print("No jobs awaiting review.")
            sys.exit(0)

        print(f"Jobs awaiting review ({len(jobs)}):\n")
        for j in jobs:
            print(f"  {j['result_id']}")
            print(f"    job_id:    {j['job_id']}")
            print(f"    status:    {j['status']}")
            print(f"    executor:  {j['executor']}")
            # Try to extract node_id from github_action
            gh = j.get("github_action")
            if gh:
                try:
                    gh_data = json.loads(gh) if isinstance(gh, str) else gh
                    print(f"    node_id:   {gh_data.get('node_id', '?')}")
                    print(f"    repo:      {gh_data.get('repo_name', '?')}")
                    print(f"    PR:        #{gh_data.get('pr_number', '?')}")
                except (json.JSONDecodeError, AttributeError):
                    pass
            print()

    else:
        result = run_verification(args.result_id, config_path=args.config_path)
        if result["ok"]:
            print(f"Verdict:  {result['verdict']}")
            print(f"Reason:   {result['reason']}")
            print(f"Matrix:   row {result['matrix_row']}")
            print(f"Result:   {result['result_id']}")
            sys.exit(0)
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)

