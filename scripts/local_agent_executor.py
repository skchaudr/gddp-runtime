"""Run a local agent in a detached worktree and return its patch."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_WORKTREE_PREFIX = "gddp-agent-wt-"


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


def emit_diff(worktree: Path) -> str:
    """Stage all worktree changes and return unified diff text."""
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
    """Run the selected agent and emit only its worktree diff on stdout."""
    if not agent_argv:
        raise ValueError("agent CLI argv is required")
    repo = repo or Path(__file__).resolve().parent.parent
    packet = load_packet(packet_raw)

    worktree: Path | None = None
    try:
        worktree = create_worktree(repo, str(packet["expected_base_commit_sha"]))
        agent_code = run_agent_fn(agent_argv, packet_raw, worktree)
        sys.stdout.write(emit_diff(worktree))
        return agent_code
    finally:
        if worktree is not None:
            remove_worktree(repo, worktree)


def main(argv: Sequence[str] | None = None) -> int:
    selected_argv = list(argv) if argv is not None else sys.argv[1:]
    if selected_argv[:1] == ["--"]:
        selected_argv = selected_argv[1:]
    return run(sys.stdin.read(), selected_argv)


if __name__ == "__main__":
    raise SystemExit(main())
