"""
bridge.py — Invoke the verifier automatically on the executor return path.

E1 keystone: when a job's merged PR comes back, the runtime runs the same
verification CLI a human would run and attaches the receipt summary to the
review result. The verdict is evidence for the human reviewer; it never
advances graph truth and it never blocks routing to awaiting_review — a
verification crash produces an explicit error record, not a stuck job.

Runs the CLI as a subprocess (not in-process) so an evaluator crash, hang, or
pi failure cannot take down the return router.
"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

# Same semantic settings proven in live runs; override via env for reruns.
DEFAULT_SEMANTIC_ARGS = (
    "--semantic-mode live --semantic-harness pi --semantic-provider deepseek "
    "--semantic-pi-model deepseek-v4-flash --semantic-thinking medium"
)
VERIFY_TIMEOUT_SECONDS = int(os.environ.get("GDDP_VERIFY_TIMEOUT_SECONDS", "1500"))

_RUNTIME_ROOT = Path(__file__).resolve().parents[3]


def _config_root() -> Path:
    return Path(os.environ.get("GDDP_CONFIG_PATH", str(_RUNTIME_ROOT.parent / "gddp-config")))


def _repos_root() -> Path:
    return Path(os.environ.get("GDDP_REPOS_ROOT", str(_RUNTIME_ROOT.parent)))


def verify_job_return(project_id: str, node_id: str) -> dict:
    """Run verification for a returned job. Always returns a dict, never raises.

    Success: {"verification_status": "ok", "receipt_path", "verdict",
              "criteria_confidence", "required_next_action"}
    Failure: {"verification_status": "error", "error": <why>}
    """
    if not project_id or not node_id:
        return {
            "verification_status": "error",
            "error": f"job missing project_id/node_id (project_id={project_id!r}, node_id={node_id!r})",
        }

    config_root = _config_root()
    node_yaml = config_root / "graphs" / project_id / "nodes" / f"{node_id}.yaml"
    project_yaml = config_root / "graphs" / project_id / "project.yaml"
    repo = _repos_root() / project_id
    receipt_dir = config_root / "verification-runtime-live"

    for path, label in ((node_yaml, "node yaml"), (project_yaml, "project yaml"), (repo, "repo")):
        if not path.exists():
            return {"verification_status": "error", "error": f"{label} not found: {path}"}

    semantic_args = shlex.split(
        os.environ.get("GDDP_VERIFY_SEMANTIC_ARGS", DEFAULT_SEMANTIC_ARGS)
    )
    cmd = [
        sys.executable,
        str(_RUNTIME_ROOT / "scripts" / "runtime" / "verification" / "cli.py"),
        "--node-yaml", str(node_yaml),
        "--project-yaml", str(project_yaml),
        "--repo", str(repo),
        "--config-root", str(config_root),
        "--receipt-dir", str(receipt_dir),
        *semantic_args,
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_RUNTIME_ROOT)

    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=VERIFY_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "verification_status": "error",
            "error": f"verifier timed out after {VERIFY_TIMEOUT_SECONDS}s",
        }
    except OSError as exc:
        return {"verification_status": "error", "error": f"verifier spawn failed: {exc}"}

    if proc.returncode != 0:
        return {
            "verification_status": "error",
            "error": f"verifier exited {proc.returncode}: {proc.stderr.strip()[-500:]}",
        }

    summary = _parse_cli_summary(proc.stdout)
    if summary is None:
        return {
            "verification_status": "error",
            "error": "verifier produced no parseable receipt summary",
        }
    return {"verification_status": "ok", **summary}


def _parse_cli_summary(stdout: str) -> dict | None:
    """The CLI prints one JSON object last; pi streaming may precede it."""
    # Walk backward to the last line that opens a JSON object.
    lines = stdout.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith("{"):
            try:
                return json.loads("\n".join(lines[i:]))
            except json.JSONDecodeError:
                continue
    return None
