"""Fail-closed git push policy and auditable mission-worker wrapper."""

from __future__ import annotations

import json
import os
import shutil
import stat
import textwrap
from pathlib import Path


def install_push_guard(directory: str | Path) -> Path:
    """Install a ``git`` wrapper that delegates reads and guards every push."""
    guard_dir = Path(directory).resolve()
    guard_dir.mkdir(parents=True, exist_ok=True)
    real_git = shutil.which("git")
    if real_git is None:
        raise RuntimeError("git executable is not available")
    wrapper = guard_dir / "git"
    wrapper.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import datetime
            import json
            import os
            import subprocess
            import sys

            REAL_GIT = {real_git!r}

            def append_audit(path, record):
                line = json.dumps(
                    record, sort_keys=True, separators=(",", ":")
                ) + "\\n"
                descriptor = os.open(
                    path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
                )
                try:
                    os.write(descriptor, line.encode())
                finally:
                    os.close(descriptor)

            def main():
                argv = sys.argv[1:]
                if "push" not in argv:
                    os.execv(REAL_GIT, [REAL_GIT, *argv])

                branch = os.environ.get("GDDP_ENGAGEMENT_BRANCH", "")
                audit_path = os.environ.get("GDDP_PUSH_AUDIT_PATH", "")
                push_index = argv.index("push")
                push_args = argv[push_index:]
                expected_refspec = f"HEAD:refs/heads/{{branch}}"
                force_tokens = {{"--force", "-f", "--force-with-lease"}}
                force_used = any(
                    item in force_tokens
                    or item.startswith("--force-with-lease=")
                    or item.startswith("+")
                    for item in argv
                )
                exact_target = (
                    bool(branch)
                    and push_args == ["push", "origin", expected_refspec]
                    and push_index == 0
                )
                allowed = bool(audit_path) and exact_target and not force_used
                reason = None
                if not audit_path:
                    reason = "GDDP_PUSH_AUDIT_PATH is not configured"
                elif force_used:
                    reason = "force-push syntax is forbidden"
                elif not exact_target:
                    reason = (
                        "push must target only origin "
                        f"{{expected_refspec}}"
                    )

                head_process = subprocess.run(
                    [REAL_GIT, "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                head = (
                    head_process.stdout.strip()
                    if head_process.returncode == 0
                    else None
                )
                returncode = None
                if allowed:
                    returncode = subprocess.run(
                        [REAL_GIT, *argv], check=False
                    ).returncode
                record = {{
                    "timestamp_utc": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat().replace("+00:00", "Z"),
                    "argv": argv,
                    "remote": (
                        push_args[1] if len(push_args) > 1 else None
                    ),
                    "source": "HEAD" if exact_target else None,
                    "destination": (
                        f"refs/heads/{{branch}}" if exact_target else (
                            push_args[-1].split(":", 1)[-1]
                            if len(push_args) > 1 else None
                        )
                    ),
                    "head": head,
                    "allowed": allowed,
                    "returncode": returncode,
                    "reason": reason,
                }}
                if audit_path:
                    append_audit(audit_path, record)
                if not allowed:
                    print(
                        f"git push policy rejected: {{reason}}",
                        file=sys.stderr,
                    )
                    return 2
                return returncode

            raise SystemExit(main())
            """
        )
    )
    wrapper.chmod(
        wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    return guard_dir


def read_push_audit(path: str | Path) -> list[dict[str, object]]:
    """Read valid push audit records, ignoring malformed partial evidence."""
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return []
    records: list[dict[str, object]] = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records
