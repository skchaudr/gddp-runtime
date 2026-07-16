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
import shutil
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


def verify_job_return(
    project_id: str,
    node_id: str,
    merge_commit_sha: str | None = None,
    pr_ref: str | None = None,
    job_id: str | None = None,
    attempt: int | None = None,
) -> dict:
    """Run verification for a returned job. Always returns a dict, never raises.

    Success: {"verification_status": "ok", "receipt_path", "verdict",
              "criteria_confidence", "required_next_action"}
    Failure: {"verification_status": "error", "error": <why>}
    Subject-mismatch: {"verification_status": "subject_mismatch", "error": <why>}

    Transient failures (timeout, crash, garbled output) get exactly one retry;
    missing config/repo paths do not — those need a human, not a rerun.
    """
    first = _verify_once(project_id, node_id, merge_commit_sha, pr_ref, job_id, attempt)
    if first["verification_status"] == "ok" or first.get("retryable") is False:
        first.pop("retryable", None)
        return first
    second = _verify_once(project_id, node_id, merge_commit_sha, pr_ref, job_id, attempt)
    second.pop("retryable", None)
    if second["verification_status"] == "error":
        second["error"] = f"(after 1 retry) {second['error']}; first attempt: {first['error']}"
    return second


def _verify_once(
    project_id: str,
    node_id: str,
    merge_commit_sha: str | None = None,
    pr_ref: str | None = None,
    job_id: str | None = None,
    attempt: int | None = None,
) -> dict:
    if not project_id or not node_id:
        return {
            "verification_status": "error",
            "retryable": False,
            "error": f"job missing project_id/node_id (project_id={project_id!r}, node_id={node_id!r})",
        }

    config_root = _config_root()
    node_yaml = config_root / "graphs" / project_id / "nodes" / f"{node_id}.yaml"
    project_yaml = config_root / "graphs" / project_id / "project.yaml"
    repo = _repos_root() / project_id
    receipt_dir = config_root / "verification-runtime-live"

    for path, label in ((node_yaml, "node yaml"), (project_yaml, "project yaml"), (repo, "repo")):
        if not path.exists():
            return {
                "verification_status": "error",
                "retryable": False,
                "error": f"{label} not found: {path}",
            }

    # A receipt without a pinned merge SHA could judge mutable repository state
    # and appear valid for code that was never evaluated.
    if not merge_commit_sha:
        return {
            "verification_status": "subject_mismatch",
            "retryable": False,
            "error": "merge_commit_sha is required to pin the evaluation subject",
        }

    worktree_path = _create_worktree(repo, merge_commit_sha)
    if worktree_path is None:
        return {
            "verification_status": "subject_mismatch",
            "retryable": False,
            "error": f"could not materialize merge_commit_sha {merge_commit_sha} in worktree",
        }
    try:
        return _run_cli(
            worktree_path, node_yaml, project_yaml, config_root, receipt_dir,
            merge_commit_sha, pr_ref, job_id, attempt,
        )
    finally:
        _remove_worktree(repo, worktree_path)


def _create_worktree(repo: Path, commit_sha: str) -> Path | None:
    """Create an isolated git worktree at the given commit. Returns path or None."""
    import tempfile
    try:
        tmpdir = tempfile.mkdtemp(prefix="gddp-eval-wt-")
        # Remove the empty dir so git worktree add can create it
        import os
        os.rmdir(tmpdir)
        proc = subprocess.run(
            ["git", "worktree", "add", "--detach", tmpdir, commit_sha],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return Path(tmpdir)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _remove_worktree(repo: Path, path: Path) -> None:
    """Clean up an isolated worktree. Best-effort."""
    removed = False
    try:
        proc = subprocess.run(
            ["git", "worktree", "remove", str(path), "--force"],
            cwd=str(repo),
            capture_output=True,
            timeout=15,
            check=False,
        )
        removed = proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pass

    if removed:
        return

    shutil.rmtree(path, ignore_errors=True)
    try:
        subprocess.run(
            ["git", "worktree", "prune", "--expire", "now"],
            cwd=str(repo),
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _run_cli(eval_repo, node_yaml, project_yaml, config_root, receipt_dir, merge_commit_sha, pr_ref, job_id, attempt) -> dict:
    semantic_args = shlex.split(
        os.environ.get("GDDP_VERIFY_SEMANTIC_ARGS", DEFAULT_SEMANTIC_ARGS)
    )
    cmd = [
        sys.executable,
        str(_RUNTIME_ROOT / "scripts" / "runtime" / "verification" / "cli.py"),
        "--node-yaml", str(node_yaml),
        "--project-yaml", str(project_yaml),
        "--repo", str(eval_repo),
        "--config-root", str(config_root),
        "--receipt-dir", str(receipt_dir),
        *semantic_args,
        "--integrity", "off" if os.environ.get("GDDP_INTEGRITY_MODE", "on").lower() == "off" else "on",
    ]
    # Phase 1 provenance: pass merge commit SHA, PR ref, and job_id to the CLI.
    if merge_commit_sha:
        cmd += ["--merge-commit-sha", merge_commit_sha]
    if pr_ref:
        cmd += ["--pr-ref", pr_ref]
    if job_id:
        cmd += ["--job-id", job_id]
    if attempt is not None:
        cmd += ["--attempt", str(attempt)]

    env = dict(os.environ)
    env["PYTHONPATH"] = str(_RUNTIME_ROOT)
    # The evaluator pi runs with a sandboxed HOME (no ~/.pi/agent/models.json),
    # so it can only resolve the DeepSeek key from the environment. Cron and
    # other non-login contexts don't source the shell secrets, so fetch the key
    # from an external source when the env lacks it. The source command is
    # configurable via GDDP_DEEPSEEK_KEY_CMD (default: the `pass` password
    # manager, which is Big Pi-specific). Best-effort: if the fetch fails, the
    # verifier's own error surfaces in the error record.
    if not env.get("DEEPSEEK_API_KEY"):
        key_cmd = os.environ.get("GDDP_DEEPSEEK_KEY_CMD", "pass show api/deepseek")
        parts = shlex.split(key_cmd)
        binary = parts[0] if parts else ""
        if not binary or shutil.which(binary) is None:
            print(
                f"[bridge] DEEPSEEK_API_KEY not set and credential command binary "
                f"{binary!r} not found on PATH (GDDP_DEEPSEEK_KEY_CMD={key_cmd!r}); "
                f"continuing without key",
                file=sys.stderr,
            )
        else:
            try:
                cred_proc = subprocess.run(
                    parts,
                    capture_output=True, text=True, timeout=15, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                print(
                    f"[bridge] credential fetch command failed ({exc!r}); "
                    f"continuing without DEEPSEEK_API_KEY",
                    file=sys.stderr,
                )
            else:
                key = cred_proc.stdout.strip()
                if cred_proc.returncode != 0 or not key:
                    print(
                        f"[bridge] credential fetch command exited "
                        f"{cred_proc.returncode} with no usable key "
                        f"(GDDP_DEEPSEEK_KEY_CMD={key_cmd!r}); "
                        f"continuing without DEEPSEEK_API_KEY",
                        file=sys.stderr,
                    )
                else:
                    env["DEEPSEEK_API_KEY"] = key

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
