"""Run a local agent in a detached worktree and hand off a commit-ref result."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_WORKTREE_PREFIX = "gddp-agent-wt-"
HANDOFF_SCHEMA = "gddp.local_result.v1"
_REF_SAFE = re.compile(r"[^A-Za-z0-9._/-]+")


def load_packet(raw: str) -> dict[str, Any]:
    """Load just enough of the raw packet to select the worktree base."""
    try:
        packet = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"stdin is not valid JSON: {exc}") from exc
    if not isinstance(packet, dict):
        raise ValueError("packet JSON must be an object")
    if not packet.get("expected_base_commit_sha"):
        raise ValueError("packet missing expected_base_commit_sha")
    return packet


def create_worktree(repo: Path, base_sha: str) -> Path:
    tmpdir = tempfile.mkdtemp(prefix=_WORKTREE_PREFIX)
    # git worktree add wants to create the path itself
    os.rmdir(tmpdir)
    proc = subprocess.run(
        ["git", "worktree", "add", "--detach", tmpdir, base_sha],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed at {base_sha}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return Path(tmpdir)


def remove_worktree(repo: Path, path: Path) -> None:
    proc = subprocess.run(
        ["git", "worktree", "remove", str(path), "--force"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode == 0:
        return
    shutil.rmtree(path, ignore_errors=True)
    subprocess.run(
        ["git", "worktree", "prune", "--expire", "now"],
        cwd=str(repo),
        capture_output=True,
        timeout=15,
        check=False,
    )


def attempt_ref_name(packet: dict[str, Any]) -> str:
    """Stable per-attempt ref name from packet fields (not session uuid)."""
    raw = (
        packet.get("execution_attempt_id")
        or packet.get("job_id")
        or "unknown"
    )
    safe = _REF_SAFE.sub("-", str(raw)).strip("-") or "unknown"
    return f"gddp/attempt-{safe}"


def emit_diff(worktree: Path) -> str:
    """Optional debug helper: stage changes and return unified diff text.

    Not used as transport. Commit-ref handoff is the production path.
    """
    add = subprocess.run(
        ["git", "add", "-A"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr.strip()}")
    diff = subprocess.run(
        ["git", "diff", "--cached", "--binary"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if diff.returncode != 0:
        raise RuntimeError(f"git diff failed: {diff.stderr.strip()}")
    return diff.stdout


def _run_git(
    args: Sequence[str],
    *,
    cwd: Path,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def persist_result(worktree: Path, packet: dict[str, Any]) -> dict[str, Any]:
    """Stage, commit, and create a durable per-attempt ref in the shared object store.

    On success returns a gddp.local_result.v1 handoff with result_commit_sha/ref.
    On failure returns the same schema with worktree_path + error (caller must
    keep the worktree).
    """
    base_sha = str(packet["expected_base_commit_sha"])
    ref_name = attempt_ref_name(packet)
    job_id = packet.get("job_id") or "unknown"
    attempt = packet.get("execution_attempt_id") or packet.get("attempt_index") or "0"
    commit_msg = f"result(job={job_id}, attempt={attempt})"

    try:
        add = _run_git(["git", "add", "-A"], cwd=worktree)
        if add.returncode != 0:
            raise RuntimeError(f"git add failed: {add.stderr.strip()}")

        # Empty tree: allow empty commit so the attempt still has a durable SHA.
        staged = _run_git(["git", "diff", "--cached", "--quiet"], cwd=worktree)
        commit_cmd = [
            "git",
            "-c",
            "user.name=gddp-local-agent",
            "-c",
            "user.email=gddp-local-agent@localhost",
            "commit",
            "-m",
            commit_msg,
        ]
        if staged.returncode == 0:
            commit_cmd.append("--allow-empty")

        commit = _run_git(commit_cmd, cwd=worktree)
        if commit.returncode != 0:
            raise RuntimeError(f"git commit failed: {commit.stderr.strip()}")

        rev = _run_git(["git", "rev-parse", "HEAD"], cwd=worktree)
        if rev.returncode != 0:
            raise RuntimeError(f"git rev-parse failed: {rev.stderr.strip()}")
        result_sha = rev.stdout.strip()
        if not result_sha:
            raise RuntimeError("git rev-parse returned empty SHA")

        ancestor = _run_git(
            ["git", "merge-base", "--is-ancestor", base_sha, result_sha],
            cwd=worktree,
        )
        if ancestor.returncode != 0:
            raise RuntimeError(
                f"result {result_sha} does not descend from expected base {base_sha}"
            )

        # Shared object store with main repo; ref must land before worktree removal.
        update_ref = _run_git(
            ["git", "update-ref", f"refs/heads/{ref_name}", result_sha],
            cwd=worktree,
        )
        if update_ref.returncode != 0:
            raise RuntimeError(
                f"git update-ref {ref_name} failed: {update_ref.stderr.strip()}"
            )

        return {
            "schema": HANDOFF_SCHEMA,
            "result_commit_sha": result_sha,
            "result_ref": ref_name,
            "expected_base_commit_sha": base_sha,
            "worktree_path": None,
        }
    except Exception as exc:
        return {
            "schema": HANDOFF_SCHEMA,
            "result_commit_sha": None,
            "result_ref": None,
            "expected_base_commit_sha": base_sha,
            "worktree_path": str(worktree),
            "error": str(exc),
        }


def write_handoff(handoff: dict[str, Any]) -> None:
    """Emit machine-readable commit-ref handoff on stdout (not a unified diff)."""
    sys.stdout.write(json.dumps(handoff, separators=(",", ":"), sort_keys=True))
    sys.stdout.write("\n")


def run_agent(argv: Sequence[str], packet_raw: str, worktree: Path) -> int:
    """Pipe the unchanged packet to the selected agent inside the worktree."""
    proc = subprocess.run(
        list(argv),
        cwd=str(worktree),
        input=packet_raw,
        text=True,
        stdout=sys.stderr,
        stderr=sys.stderr,
        check=False,
    )
    return proc.returncode


def run(
    packet_raw: str,
    agent_argv: Sequence[str],
    *,
    repo: Path | None = None,
    run_agent_fn=run_agent,
) -> int:
    """Run the selected agent and emit a commit-ref handoff on stdout."""
    if not agent_argv:
        raise ValueError("agent CLI argv is required")
    repo = repo or Path(__file__).resolve().parent.parent
    packet = load_packet(packet_raw)

    worktree: Path | None = None
    keep_worktree = False
    try:
        worktree = create_worktree(repo, str(packet["expected_base_commit_sha"]))
        agent_code = run_agent_fn(agent_argv, packet_raw, worktree)
        handoff = persist_result(worktree, packet)
        # Set keep policy before stdout write so a write_handoff failure
        # cannot undo persist-fail recovery (worktree must survive).
        keep_worktree = not bool(handoff.get("result_commit_sha"))
        write_handoff(handoff)
        if handoff.get("result_commit_sha"):
            # Persist succeeded; safe to remove worktree A.
            return agent_code
        # Persist failed: keep worktree for operator recovery; fail closed.
        return agent_code if agent_code != 0 else 1
    finally:
        if worktree is not None and not keep_worktree:
            remove_worktree(repo, worktree)


def main(argv: Sequence[str] | None = None) -> int:
    selected_argv = list(argv) if argv is not None else sys.argv[1:]
    if selected_argv[:1] == ["--"]:
        selected_argv = selected_argv[1:]
    return run(sys.stdin.read(), selected_argv)


if __name__ == "__main__":
    raise SystemExit(main())
