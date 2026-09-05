"""
orchestrator_wake.py — Run one orchestrator wake (G6 + the wake mechanics).

A wake is an attempt with no node: it gets its own spool root and its own
record kind so the jobs table and executor_sessions stay purely about node
work, and a wake never consumes a max_concurrent_jobs slot.

One wake, synchronously:

    assemble pack -> build prompt -> one fresh cursor-agent turn
    -> parse the decision from the turn's final text -> apply it

The turn reuses the spike-proven argv (build_argv) and the proven stream
parser (CursorStreamTranslator) — the delta/re-emission trap in cursor's
partial output is measured, and re-deriving it here would invent a second
answer to a solved question.

Every wake leaves a directory under the wake spool root:

    <spool>/<project_id>/<wake_id>/
        prompt.txt   the exact prompt sent
        raw.jsonl    the raw stream-json lines
        wake.json    our record: exit, timing, decision, outcome, error

Usage stays behind GDDP_ORCHESTRATOR_WAKE in runner.py; this module on its
own runs nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from adapters.cursor_cli_adapter import build_argv, resolve_model
from adapters.events_cursor_cli import CursorStreamTranslator

from .orchestrator_decision import (
    Applied,
    _mint_wake_id,
    apply_decision,
    parse_decision,
)
from .orchestrator_pack import assemble_pack
from .orchestrator_prompt import build_wake_prompt

_default_root = Path(__file__).parent.parent.parent.parent
RUNTIME_ROOT = Path(
    os.environ.get("GDDP_RUNTIME_ROOT") or os.environ.get("OPCLAW_ROOT", _default_root)
)
# G6: wakes spool here, beside — never inside — the executor attempt spools.
WAKE_SPOOL_ROOT = RUNTIME_ROOT / "jobs" / "orchestrator-wakes"

_BINARY_ENV = "GDDP_CURSOR_CLI_BINARY"  # same binary the executor turns use
_TIMEOUT_ENV = "GDDP_ORCHESTRATOR_WAKE_TIMEOUT_S"
_DEFAULT_TIMEOUT_S = 600.0
# Measured in the cursor spike: SIGTERM -> death 1.16s. Grace above that.
_KILL_GRACE_S = 3.0


def _assistant_text(lines: list[dict]) -> tuple[str, bool]:
    """Final text and completion from a decoded stream, via the proven parser."""
    translator = CursorStreamTranslator()
    texts: list[str] = []
    for raw in lines:
        for event in translator.translate(raw):
            if event.type == "assistant_message":
                texts.append(str(event.fields.get("text", "")))
    for event in translator.flush_text():
        if event.type == "assistant_message":
            texts.append(str(event.fields.get("text", "")))
    return "".join(texts), translator.completed_work


def _decision_json(text: str) -> dict:
    """The first JSON object in the turn's final text, wherever it sits."""
    start = text.find("{")
    if start < 0:
        raise ValueError("wake answered without a JSON object")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("wake's JSON answer is not an object")
    return obj


def _spawn_turn(
    argv: list[str], attempt_dir: Path, timeout_s: float
) -> tuple[int, str | None, list[dict]]:
    """Run cursor-agent to completion, returning (returncode, error, stream).

    Synchronous by design: the wake is one short turn inside a heartbeat
    tick, and blocking the tick on it keeps ordering trivial. A timeout is
    SIGTERM, then SIGKILL after the measured grace.
    """
    proc = subprocess.Popen(
        argv,
        cwd=attempt_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.communicate(timeout=_KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
        return -15, f"wake exceeded {timeout_s}s and was killed", []
    if stderr:
        (attempt_dir / "stderr.log").write_bytes(stderr)
    lines: list[dict] = []
    for raw_line in stdout.splitlines():
        try:
            decoded = json.loads(raw_line)
        except ValueError:
            continue
        if isinstance(decoded, dict):
            lines.append(decoded)
    return proc.returncode, None, lines


def run_wake(
    con,
    reader,
    project,
    *,
    now: datetime | None = None,
    spool_root: Path | None = None,
    timeout_s: float | None = None,
    receipts_root: Path | None = None,
) -> Applied | None:
    """One wake: pack, prompt, turn, decision, application. None on failure.

    Failures are recorded in wake.json and reported to the caller as None —
    a broken wake is loud in its own spool and must never take the tick down
    with it.
    """
    now = now or datetime.now(timezone.utc)
    timeout_s = (
        timeout_s
        if timeout_s is not None
        else float(os.environ.get(_TIMEOUT_ENV, str(_DEFAULT_TIMEOUT_S)))
    )
    wake_id = _mint_wake_id(now)
    attempt_dir = (spool_root or WAKE_SPOOL_ROOT) / project.project_id / wake_id
    attempt_dir.mkdir(parents=True, exist_ok=False)

    record: dict[str, object] = {
        "kind": "orchestrator_wake",
        "wake_id": wake_id,
        "project_id": project.project_id,
        "started_at": now.isoformat(),
    }

    def _finish(**fields: object) -> None:
        record.update(fields)
        record["elapsed_s"] = round(
            (datetime.now(timezone.utc) - now).total_seconds(), 3
        )
        (attempt_dir / "wake.json").write_text(
            json.dumps(record, indent=2, sort_keys=True)
        )

    pack = assemble_pack(con, reader, project.project_id, now=now, receipts_root=receipts_root)
    run_block = project.execution_policy.get("orchestrator_run_block") or ""
    prompt = build_wake_prompt(pack, run_block=str(run_block))
    (attempt_dir / "prompt.txt").write_text(prompt)

    model = resolve_model("orchestrator", project.execution_policy)
    argv = build_argv(
        binary=os.environ.get(_BINARY_ENV) or "cursor-agent",
        prompt=prompt,
        model=model,
    )
    record["model"] = model

    returncode, error, lines = _spawn_turn(argv, attempt_dir, timeout_s)
    (attempt_dir / "raw.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines)
    )
    record["returncode"] = returncode
    if error:
        _finish(error=error)
        print(f"  → orchestrator wake {wake_id}: {error}", file=sys.stderr)
        return None

    text, completed_work = _assistant_text(lines)
    record["completed_work"] = completed_work
    if not completed_work:
        _finish(error=f"turn ended without completed work (rc={returncode})")
        print(
            f"  → orchestrator wake {wake_id}: turn did not complete",
            file=sys.stderr,
        )
        return None

    try:
        decision = parse_decision(_decision_json(text), wake_id=wake_id)
    except (ValueError, TypeError) as exc:
        _finish(error=f"unreadable decision: {exc}", answer=text[:2000])
        print(
            f"  → orchestrator wake {wake_id}: unreadable decision: {exc}",
            file=sys.stderr,
        )
        return None

    applied = apply_decision(con, project, decision, now=now, receipts_root=receipts_root)
    _finish(decision=decision.to_json_value(), applied=applied.to_json_value())
    return applied
