"""Shared subprocess helpers for the semantic verification pi-harness runners.

Both the criteria-lane runner (pi_runner.py) and the integrity-lane runner
(integrity_runner.py) spawn `pi` as a subprocess and need the same four
operations:

  - tee stdout/stderr to the operator's terminal *and* durable log files
    (live visibility + receipt evidence),
  - read the tail of a log file for crash error messages,
  - read the JSONL tool-trace file produced by the guard extension,
  - terminate the whole process group on timeout so no descendant survives.

These were previously duplicated verbatim across the two runners. They live
here to prevent drift. Behavior is unchanged from the originals.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


def tee_subprocess(cmd, env, cwd, stdout_path, stderr_path, timeout_seconds):
    """Run a subprocess, teeing stdout/stderr to terminal + durable log files.

    Live output goes to ``sys.stdout``/``sys.stderr`` (operator visibility).
    A durable copy goes to ``stdout_path``/``stderr_path`` (receipt evidence).

    ``timeout_seconds`` is required and has no default: each lane passes its
    own budget (``PI_TIMEOUT_SECONDS``) explicitly so this module stays free
    of project-specific config.

    On timeout the process group is terminated (see :func:`terminate_process_group`)
    and ``subprocess.TimeoutExpired`` is re-raised so the caller can produce a
    typed fallback verdict instead of crashing.
    """
    proc = subprocess.Popen(
        cmd, env=env, cwd=cwd, stdin=None,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )

    def _tee(stream, file_path, out_stream):
        with open(file_path, "w", encoding="utf-8") as f:
            for line in iter(stream.readline, b""):
                text = line.decode("utf-8", errors="replace")
                f.write(text)
                out_stream.write(text)
                out_stream.flush()
        stream.close()

    t_out = threading.Thread(target=_tee, args=(proc.stdout, stdout_path, sys.stdout), daemon=True)
    t_err = threading.Thread(target=_tee, args=(proc.stderr, stderr_path, sys.stderr), daemon=True)
    t_out.start()
    t_err.start()
    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        terminate_process_group(proc)
        raise
    finally:
        t_out.join(timeout=5)
        t_err.join(timeout=5)
    return proc


def terminate_process_group(proc) -> None:
    """Terminate the pi process group so a timed-out pi child cannot survive.

    On POSIX the leader is signaled with SIGTERM and given a grace window; the
    group is then SIGKILLed regardless so a descendant that ignores SIGTERM
    cannot outlive the timed-out run. On non-POSIX ``proc.terminate()`` is the
    fallback.
    """
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            return
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        # The leader can exit on SIGTERM while a descendant ignores it. Kill
        # the group anyway so that descendant cannot outlive the timed-out run.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    else:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def read_trace(trace_path: str) -> list[dict[str, Any]]:
    """Read a JSONL tool-trace file produced by the guard extension.

    Returns ``[]`` when the file is absent (no tools were recorded). Malformed
    lines are skipped so a partially-written trace still yields the valid
    prefix.
    """
    p = Path(trace_path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_tail(path: str, max_chars: int = 500) -> str:
    """Read the last ``max_chars`` characters of a file. Best-effort.

    Returns ``""`` if the file is missing or unreadable.
    """
    try:
        p = Path(path)
        if not p.exists():
            return ""
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:] if len(text) > max_chars else text
    except OSError:
        return ""
