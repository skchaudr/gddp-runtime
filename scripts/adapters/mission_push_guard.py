"""Enforce and audit mission worker pushes at the git executable boundary."""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_AUDIT_ENV = "GDDP_PUSH_AUDIT_PATH"
_BRANCH_ENV = "GDDP_ENGAGEMENT_BRANCH"
_REAL_GIT_ENV = "GDDP_REAL_GIT"


def install_git_push_guard(
    guard_dir: str | Path,
    *,
    engagement_branch: str,
    audit_path: str | Path,
    base_env: Mapping[str, str],
) -> dict[str, str]:
    """Create a PATH shim and return the environment for a mission process."""
    original_path = base_env.get("PATH", os.defpath)
    real_git = shutil.which("git", path=original_path)
    if real_git is None:
        raise RuntimeError("git executable could not be resolved for push guard")

    directory = Path(guard_dir)
    directory.mkdir(parents=True, exist_ok=False)
    wrapper = directory / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"exec {shlex.quote(sys.executable)} "
        f"{shlex.quote(str(Path(__file__).resolve()))} \"$@\"\n"
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    guarded = dict(base_env)
    guarded.update(
        {
            _AUDIT_ENV: str(Path(audit_path).resolve()),
            _BRANCH_ENV: engagement_branch,
            _REAL_GIT_ENV: real_git,
            "PATH": f"{directory.resolve()}{os.pathsep}{original_path}",
        }
    )
    return guarded


def run_guarded_git(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
) -> int:
    """Delegate ordinary git commands and enforce the one allowed push shape."""
    configured = os.environ if env is None else env
    real_git = configured.get(_REAL_GIT_ENV)
    if not real_git:
        print(f"{_REAL_GIT_ENV} is required", file=sys.stderr)
        return 126

    arguments = list(argv)
    try:
        push_index = arguments.index("push")
    except ValueError:
        os.execv(real_git, [real_git, *arguments])

    engagement_branch = configured.get(_BRANCH_ENV, "")
    audit_path = configured.get(_AUDIT_ENV)
    expected = [
        "origin",
        f"HEAD:refs/heads/{engagement_branch}",
    ]
    push_arguments = arguments[push_index + 1 :]
    rejection = _push_rejection(push_arguments, expected)
    head = _git_head(real_git, arguments[:push_index])

    if rejection is not None:
        _append_audit(
            audit_path,
            {
                "argv": ["git", *arguments],
                "allowed": False,
                "reason": rejection,
                "engagement_branch": engagement_branch,
                "commit_sha": head,
                "origin_containing_refs": [],
                "returncode": 2,
                "timestamp_utc": _timestamp(),
            },
        )
        print(f"mission push rejected: {rejection}", file=sys.stderr)
        return 2

    process = subprocess.run([real_git, *arguments], check=False)
    origin_containing_refs = (
        _origin_refs_containing(real_git, arguments[:push_index], head)
        if process.returncode == 0 and head is not None
        else ()
    )
    _append_audit(
        audit_path,
        {
            "argv": ["git", *arguments],
            "allowed": True,
            "reason": None,
            "engagement_branch": engagement_branch,
            "commit_sha": head,
            "origin_containing_refs": list(origin_containing_refs),
            "returncode": process.returncode,
            "timestamp_utc": _timestamp(),
        },
    )
    return process.returncode


def _push_rejection(push_arguments: list[str], expected: list[str]) -> str | None:
    for argument in push_arguments:
        if argument.startswith("+"):
            return "leading + refspecs are forbidden"
        if argument.startswith("--force"):
            return f"{argument} is forbidden"
        if (
            argument.startswith("-")
            and not argument.startswith("--")
            and "f" in argument[1:]
        ):
            return f"{argument} is a force-push option and is forbidden"
    if push_arguments != expected:
        return (
            "push must target only "
            f"`{expected[0]} {expected[1]}`"
        )
    return None


def _git_head(real_git: str, global_arguments: list[str]) -> str | None:
    try:
        process = subprocess.run(
            [real_git, *global_arguments, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    head = process.stdout.strip()
    return head if process.returncode == 0 and head else None


def _origin_refs_containing(
    real_git: str,
    global_arguments: list[str],
    commit_sha: str,
) -> tuple[str, ...]:
    try:
        process = subprocess.run(
            [
                real_git,
                *global_arguments,
                "branch",
                "-r",
                "--contains",
                commit_sha,
                "--format=%(refname:short)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if process.returncode != 0:
        return ()
    return tuple(
        line.strip()
        for line in process.stdout.splitlines()
        if line.strip()
    )


def _append_audit(path_value: str | None, record: Mapping[str, object]) -> None:
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        os.write(descriptor, encoded)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    return run_guarded_git(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
