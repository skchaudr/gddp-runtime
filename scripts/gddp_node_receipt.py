#!/usr/bin/env python3
"""Append independently observed per-node git evidence to a JSONL ledger."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


RECEIPTS_PATH_ENV = "GDDP_RECEIPTS_PATH"


class GitContextError(RuntimeError):
    """Raised when the current checkout cannot provide receipt evidence."""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gddp-node-receipt")
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--result", required=True)
    return parser.parse_args(argv)


def _git_value(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else exc
        raise GitContextError(str(detail)) from exc
    value = completed.stdout.strip()
    if not value:
        raise GitContextError(f"git {' '.join(args)} returned no value")
    return value


def _observe_git_context() -> dict[str, str]:
    return {
        "git_head": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("rev-parse", "--abbrev-ref", "HEAD"),
        "git_toplevel": _git_value("rev-parse", "--show-toplevel"),
    }


def _append_line(path: Path, line: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        remaining = memoryview(line)
        while remaining:
            written = os.write(descriptor, remaining)
            if written == 0:
                raise OSError("receipt append wrote zero bytes")
            remaining = remaining[written:]
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configured_path = os.environ.get(RECEIPTS_PATH_ENV)
    if not configured_path:
        print(f"error: {RECEIPTS_PATH_ENV} is not set", file=sys.stderr)
        return 2

    try:
        git_context = _observe_git_context()
    except GitContextError as exc:
        print(f"error: could not observe git context: {exc}", file=sys.stderr)
        return 1

    receipt = {
        "node_id": args.node_id,
        "base": args.base,
        "result": args.result,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **git_context,
    }
    serialized = json.dumps(receipt, sort_keys=True)
    try:
        _append_line(Path(configured_path).expanduser(), f"{serialized}\n".encode())
    except OSError as exc:
        print(f"error: could not append receipt: {exc}", file=sys.stderr)
        return 1

    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
