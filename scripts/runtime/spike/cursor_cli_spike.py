#!/usr/bin/env python3
"""Spike: verify cursor-agent -p as a per-turn executor transport.

Go/no-go evidence for a cursor_cli adapter: one subprocess per turn,
continuity via --resume <session_id>, observability via stream-json.
Mirrors pi_rpc_persistent_spike.py. Stdlib only.

Proves, in order:
  1. cold turn: session_id + result event + usage telemetry
  2. resume after clean process exit (cross-process continuity)
  3. tool_call event schema (read tool: args.path, result.success)
  4. SIGTERM mid-turn: prompt death, session resumable afterwards
  5. SIGKILL mid-turn: same, for the host-reboot case
  6. failure classification surface: invalid model name

Cannot prove in one session: resume durability across hours/days
(Cursor-side chat storage retention). That remains an open risk note.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

MODEL = os.environ.get("CURSOR_SPIKE_MODEL")  # None -> CLI default
SCRATCH = Path(os.environ.get("CURSOR_SPIKE_DIR", "/tmp/cursor-cli-spike"))
RESULTS_PATH = Path(os.environ.get(
    "CURSOR_SPIKE_RESULTS",
    str(Path(__file__).resolve().parent / "cursor_cli_spike_results.json"),
))
TURN_TIMEOUT_S = float(os.environ.get("CURSOR_SPIKE_TIMEOUT", "120"))
BINARY = os.environ.get("CURSOR_SPIKE_BINARY", "cursor-agent")

COLD_TOKEN = "SPIKE7-COLD"


class TurnResult:
    def __init__(self, label: str):
        self.label = label
        self.session_id: str | None = None
        self.model: str | None = None
        self.event_types: dict[str, int] = {}
        self.tool_calls: list[dict] = []
        self.result_event: dict | None = None
        self.exit_code: int | None = None
        self.wall_s: float = 0.0
        self.stderr_tail: str = ""
        self.assistant_text: str = ""

    def to_json(self) -> dict:
        return {
            "label": self.label,
            "session_id": self.session_id,
            "model": self.model,
            "event_types": self.event_types,
            "tool_calls": self.tool_calls,
            "result_event": self.result_event,
            "exit_code": self.exit_code,
            "wall_s": round(self.wall_s, 2),
            "assistant_text": self.assistant_text[:300],
            "stderr_tail": self.stderr_tail[-500:],
        }


def _cmd(prompt: str, *, resume: str | None, model: str | None) -> list[str]:
    cmd = [
        BINARY, "-p", "--trust",
        "--output-format", "stream-json",
        "--stream-partial-output",
    ]
    if model:
        cmd.extend(["--model", model])
    if resume:
        cmd.extend(["--resume", resume])
    cmd.append(prompt)
    return cmd


def _absorb(line: str, out: TurnResult) -> None:
    try:
        evt = json.loads(line)
    except json.JSONDecodeError:
        return
    etype = evt.get("type", "?")
    subtype = evt.get("subtype")
    key = f"{etype}/{subtype}" if subtype else etype
    # Deltas are counted but flood anything else; everything else is kept small.
    out.event_types[key] = out.event_types.get(key, 0) + 1
    if etype == "system" and subtype == "init":
        out.session_id = evt.get("session_id")
        out.model = evt.get("model")
    elif etype == "tool_call":
        call = evt.get("tool_call") or {}
        tool_key = next((k for k in call if k.endswith("ToolCall")), None)
        entry: dict = {"subtype": subtype, "tool_key": tool_key, "call_id": evt.get("call_id")}
        body = call.get(tool_key) or {} if tool_key else {}
        args = body.get("args") or {}
        if "path" in args:
            entry["path"] = args["path"]
        result = body.get("result")
        if isinstance(result, dict):
            entry["result_keys"] = sorted(result.keys())
        out.tool_calls.append(entry)
    elif etype == "assistant" and not subtype:
        content = (evt.get("message") or {}).get("content") or []
        out.assistant_text += "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    elif etype == "result":
        out.result_event = evt


def run_turn(label: str, prompt: str, *, resume: str | None = None,
             model: str | None = MODEL, timeout: float = TURN_TIMEOUT_S) -> TurnResult:
    out = TurnResult(label)
    start = time.time()
    proc = subprocess.Popen(
        _cmd(prompt, resume=resume, model=model),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=str(SCRATCH),
    )
    assert proc.stdout is not None
    deadline = start + timeout
    for line in proc.stdout:
        _absorb(line, out)
        if time.time() > deadline:
            proc.kill()
            out.stderr_tail += f"\n[spike] killed after {timeout}s timeout"
            break
    proc.wait(timeout=15)
    out.exit_code = proc.returncode
    out.wall_s = time.time() - start
    if proc.stderr:
        out.stderr_tail += proc.stderr.read()[-400:]
    return out


def run_killed_turn(label: str, prompt: str, *, sig: int, after_events: int = 8) -> tuple[TurnResult, float]:
    """Start a long turn, send sig after `after_events` non-delta events.

    Returns (partial TurnResult, seconds from signal to process death).
    """
    out = TurnResult(label)
    proc = subprocess.Popen(
        _cmd(prompt, resume=None, model=MODEL),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=str(SCRATCH), start_new_session=True,
    )
    assert proc.stdout is not None
    seen = 0
    start = time.time()
    sent_at: float | None = None
    death_s = -1.0
    for line in proc.stdout:
        _absorb(line, out)
        seen += 1
        if seen >= after_events and sent_at is None:
            sent_at = time.time()
            os.killpg(proc.pid, sig)
        if sent_at is not None and proc.poll() is not None:
            death_s = time.time() - sent_at
            break
        if time.time() - start > 60:
            break
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)
    if sent_at is not None and death_s < 0:
        death_s = time.time() - sent_at
    out.exit_code = proc.returncode
    out.wall_s = time.time() - start
    return out, death_s


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    target = SCRATCH / "spike-target.txt"
    target.write_text("spikeword the rest of this line\n")

    results: dict[str, dict] = {}
    hard_fails: list[str] = []

    # 1. cold turn
    t = run_turn("cold_turn", f"Reply with exactly: {COLD_TOKEN}")
    results["cold_turn"] = t.to_json()
    if not t.session_id:
        hard_fails.append("cold_turn: no session_id in system/init")
    if not (t.result_event and t.result_event.get("is_error") is False):
        hard_fails.append("cold_turn: missing or error result event")
    sid = t.session_id

    # 2. resume after clean exit
    if sid:
        t = run_turn(
            "resume_after_exit",
            "Earlier in this chat I asked you to reply with a specific token. "
            "Reply with only that token.",
            resume=sid,
        )
        results["resume_after_exit"] = t.to_json()
        if COLD_TOKEN not in t.assistant_text and COLD_TOKEN not in json.dumps(t.result_event or {}):
            hard_fails.append("resume_after_exit: token not recalled — resume lost history")

    # 3. tool events
    t = run_turn(
        "tool_events",
        f"Use your read tool on {target} and reply with only the first word of the file.",
    )
    results["tool_events"] = t.to_json()
    started = [c for c in t.tool_calls if c["subtype"] == "started"]
    completed = [c for c in t.tool_calls if c["subtype"] == "completed"]
    if not (started and completed and started[0].get("path") == str(target)):
        hard_fails.append("tool_events: read tool_call started/completed with args.path not observed")

    # 4+5. kill mid-turn, then prove the session still resumes
    long_prompt = (
        "Count from 1 to 300, one number per line. Take your time; "
        "think briefly between each number."
    )
    for sig, name in ((signal.SIGTERM, "sigterm_mid_turn"), (signal.SIGKILL, "sigkill_mid_turn")):
        killed, death_s = run_killed_turn(name, long_prompt, sig=sig)
        results[name] = killed.to_json()
        results[name]["seconds_signal_to_death"] = round(death_s, 2)
        if killed.session_id:
            t = run_turn(
                f"{name}_resume_check",
                "Reply with exactly: ALIVE",
                resume=killed.session_id,
            )
            results[f"{name}_resume_check"] = t.to_json()
            if not (t.result_event and t.result_event.get("is_error") is False):
                hard_fails.append(f"{name}: session not resumable after kill")

    # 6. failure classification: invalid model
    t = run_turn("invalid_model", "Reply with exactly: UNREACHABLE", model="definitely/not-a-model-zzz")
    results["invalid_model"] = t.to_json()
    ie = (t.result_event or {}).get("is_error")
    if t.exit_code == 0 and ie is False:
        hard_fails.append("invalid_model: unexpectedly succeeded — failure surface unobserved")

    summary = {
        "binary": BINARY,
        "model_defaulted": MODEL is None,
        "scratch": str(SCRATCH),
        "turns": results,
        "hard_fails": hard_fails,
        "verdict": "GO" if not hard_fails else "NO-GO",
        "open_risks": [
            "resume durability across hours/days not provable in one session",
            "provider/API failure classification not exercised (only invalid-model)",
            "write/shell tool_call variants not exercised (read only)",
        ],
    }
    RESULTS_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps({k: v.get("exit_code") for k, v in results.items()}, indent=2))
    print(f"verdict: {summary['verdict']}  (results: {RESULTS_PATH})")
    for fail in hard_fails:
        print(f"  HARD FAIL: {fail}")
    return 0 if not hard_fails else 1


if __name__ == "__main__":
    sys.exit(main())
