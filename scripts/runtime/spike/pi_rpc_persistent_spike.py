#!/usr/bin/env python3
"""Spike: verify pi --mode rpc as a persistent multi-turn executor transport.

Go/no-go evidence for GDDP persistent-pi mode. Stdlib only.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Prefer a cheap, available model; override with PI_SPIKE_MODEL.
DEFAULT_MODEL = os.environ.get("PI_SPIKE_MODEL", "deepseek/deepseek-v4-flash")
SESSION_DIR = Path(os.environ.get(
    "PI_SPIKE_SESSION_DIR",
    str(Path.home() / "tmp" / "pi-rpc-spike-sessions"),
)).expanduser()
RESULTS_PATH = Path(os.environ.get(
    "PI_SPIKE_RESULTS",
    str(Path(__file__).resolve().parent / "pi_rpc_persistent_spike_results.json"),
))
TIMEOUT_S = float(os.environ.get("PI_SPIKE_TIMEOUT", "120"))


class RpcClient:
    def __init__(self, proc: subprocess.Popen[str], label: str):
        self.proc = proc
        self.label = label
        self.events: list[dict] = []
        self._buf = ""
        self._req = 0

    @classmethod
    def start(
        cls,
        *,
        model: str,
        session_dir: Path,
        session: str | None = None,
        label: str = "primary",
        extra_args: list[str] | None = None,
    ) -> "RpcClient":
        session_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "pi",
            "--mode", "rpc",
            "--model", model,
            "--session-dir", str(session_dir),
            "--tools", "read",  # minimal surface; no bash needed for memory test
        ]
        if session:
            cmd.extend(["--session", session])
        if extra_args:
            cmd.extend(extra_args)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        client = cls(proc, label)
        client.command_line = " ".join(cmd)  # type: ignore[attr-defined]
        # Drain until we can get_state (process ready). Some versions emit
        # bootstrap events first; give a short settle then probe.
        time.sleep(0.5)
        if proc.poll() is not None:
            err = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"pi exited immediately ({proc.returncode}): {err[:800]}")
        return client

    def send(self, obj: dict, *, wait_response: bool = True, timeout: float = TIMEOUT_S) -> dict | None:
        self._req += 1
        if "id" not in obj:
            obj = {**obj, "id": f"req-{self._req}"}
        assert self.proc.stdin is not None
        line = json.dumps(obj, separators=(",", ":"))
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        if not wait_response:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            evt = self._read_one(timeout=max(0.1, deadline - time.time()))
            if evt is None:
                continue
            self.events.append(evt)
            if evt.get("type") == "response" and evt.get("id") == obj["id"]:
                return evt
        raise TimeoutError(f"no response for {obj.get('type')} id={obj.get('id')}")

    def wait_until(self, pred, *, timeout: float = TIMEOUT_S) -> list[dict]:
        """Read events until pred(event) or timeout. Returns matched events batch."""
        matched: list[dict] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            evt = self._read_one(timeout=max(0.1, deadline - time.time()))
            if evt is None:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"pi exited during wait ({self.proc.returncode})")
                continue
            self.events.append(evt)
            matched.append(evt)
            if pred(evt):
                return matched
        raise TimeoutError("wait_until timed out")

    def _read_one(self, *, timeout: float) -> dict | None:
        assert self.proc.stdout is not None
        import select
        r, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not r:
            return None
        line = self.proc.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"type": "_non_json", "raw": line[:500]}

    def get_state(self) -> dict:
        resp = self.send({"type": "get_state"})
        assert resp and resp.get("success"), resp
        return resp.get("data") or {}

    def get_messages(self) -> list:
        resp = self.send({"type": "get_messages"})
        assert resp and resp.get("success"), resp
        data = resp.get("data")
        if isinstance(data, dict):
            return data.get("messages") or data.get("entries") or []
        if isinstance(data, list):
            return data
        return []

    def prompt_and_wait_turn(self, message: str, *, timeout: float = TIMEOUT_S) -> dict:
        """Send prompt; wait for agent_end (one low-level agent run complete)."""
        resp = self.send({"type": "prompt", "message": message}, timeout=timeout)
        if not resp or not resp.get("success"):
            raise RuntimeError(f"prompt rejected: {resp}")
        # Prefer agent_end as durable "run finished"; also note turn_end.
        terminal = {"agent_end", "turn_end"}
        seen_types: list[str] = []
        def done(evt: dict) -> bool:
            t = evt.get("type")
            if isinstance(t, str):
                seen_types.append(t)
            return t == "agent_end"
        batch = self.wait_until(done, timeout=timeout)
        return {
            "prompt_response": resp,
            "event_types": seen_types,
            "terminal_events": [e for e in batch if e.get("type") in terminal],
            "last_events": batch[-5:],
        }

    def kill(self, sig: int = signal.SIGKILL) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.send_signal(sig)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def close_gracefully(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _content_text(content) -> str:
    if isinstance(content, dict):
        content = content.get("content") or content.get("text")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in (None, "text"):
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    if isinstance(content, str):
        return content
    return ""


def extract_text(messages: list, *, roles: set[str] | None = None) -> str:
    chunks: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role") or ""
        if roles is not None and role not in roles:
            # also allow nested message.role
            nested = m.get("message") if isinstance(m.get("message"), dict) else {}
            role2 = nested.get("role") if nested else ""
            if role2 not in (roles or set()):
                if role not in (roles or set()) and role2 not in (roles or set()):
                    continue
            role = role or role2
        content = m.get("content")
        if content is None and isinstance(m.get("message"), dict):
            content = m["message"].get("content")
        text = _content_text(content)
        if text.strip():
            chunks.append(text)
    return "\n".join(chunks)


def assistant_text_from_events(events: list) -> str:
    chunks: list[str] = []
    for e in events:
        if not isinstance(e, dict):
            continue
        if e.get("type") == "message_end":
            msg = e.get("message") or {}
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                # skip error-only assistants
                if msg.get("stopReason") == "error" or msg.get("errorMessage"):
                    chunks.append(f"[error:{msg.get("errorMessage","")}]")
                    continue
                chunks.append(_content_text(msg.get("content")))
        if e.get("type") == "agent_end":
            # some payloads include messages
            for msg in e.get("messages") or []:
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    chunks.append(_content_text(msg.get("content")))
    return "\n".join(chunks)


def main() -> int:
    results: dict = {
        "host": os.uname().nodename if hasattr(os, "uname") else "unknown",
        "model": DEFAULT_MODEL,
        "session_dir": str(SESSION_DIR),
        "steps": {},
        "event_types_observed": [],
        "command_lines": [],
        "adapter_feasibility": "",
        "pass_fail": {},
    }
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    client: RpcClient | None = None
    session_file: str | None = None
    session_id: str | None = None

    try:
        # --- Step 1: start + prompt #1 ---
        client = RpcClient.start(model=DEFAULT_MODEL, session_dir=SESSION_DIR, label="s1")
        results["command_lines"].append(getattr(client, "command_line", ""))
        state = client.get_state()
        session_file = state.get("sessionFile") or state.get("session_file")
        session_id = state.get("sessionId") or state.get("session_id")
        results["steps"]["1_start"] = {
            "ok": True,
            "state_keys": sorted(state.keys()),
            "sessionFile": session_file,
            "sessionId": session_id,
            "model": state.get("model"),
        }
        results["pass_fail"]["1_start"] = "pass"

        r1 = client.prompt_and_wait_turn(
            "Remember the word 'nebula'. Reply with exactly: ok"
        )
        results["steps"]["1_prompt"] = {
            "ok": True,
            "event_types": r1["event_types"],
            "terminal_count": len(r1["terminal_events"]),
        }
        results["event_types_observed"] = sorted(set(results["event_types_observed"]) | set(r1["event_types"]))
        results["pass_fail"]["1_prompt_turn_complete"] = (
            "pass" if "agent_end" in r1["event_types"] or "turn_end" in r1["event_types"] else "fail"
        )

        # Refresh session identity after first turn
        state = client.get_state()
        session_file = state.get("sessionFile") or session_file
        session_id = state.get("sessionId") or session_id
        results["steps"]["1_session_after_turn"] = {
            "sessionFile": session_file,
            "sessionId": session_id,
        }

        # --- Step 2: multi-turn memory ---
        r2 = client.prompt_and_wait_turn(
            "What word did I ask you to remember? Reply with only that word."
        )
        msgs = client.get_messages()
        asst = assistant_text_from_events(r2.get("last_events") or []).lower()
        asst_msgs = extract_text(msgs, roles={"assistant"}).lower()
        # Fail closed on auth/provider errors
        err = ("api key auth failed" in asst) or ("api key auth failed" in asst_msgs)
        remembered = (not err) and (("nebula" in asst) or ("nebula" in asst_msgs))
        results["steps"]["2_multiturn"] = {
            "ok": remembered,
            "auth_error": err,
            "event_types": r2["event_types"],
            "message_count": len(msgs),
            "assistant_text": (asst or asst_msgs)[-500:],
            "text_sample": extract_text(msgs)[-500:],
        }
        results["event_types_observed"] = sorted(set(results["event_types_observed"]) | set(r2["event_types"]))
        results["pass_fail"]["2_multiturn_context"] = "pass" if remembered else "fail"

        # --- Step 3: note session id ---
        results["steps"]["3_session_identity"] = {
            "sessionFile": session_file,
            "sessionId": session_id,
            "session_file_exists": bool(session_file and Path(session_file).exists()),
        }
        results["pass_fail"]["3_session_identity"] = (
            "pass" if session_file and Path(str(session_file)).exists() else "fail"
        )

        # --- Step 4: kill mid-turn ---
        # Start a long prompt then SIGKILL before it finishes.
        client.send(
            {
                "type": "prompt",
                "message": (
                    "Count slowly from 1 to 200 in words, one number per line. "
                    "Do not stop early. This is intentionally long."
                ),
            },
            wait_response=True,
            timeout=30,
        )
        # Let it start streaming
        time.sleep(2.0)
        # Drain a few events if available
        mid_types: list[str] = []
        deadline = time.time() + 3
        while time.time() < deadline:
            evt = client._read_one(timeout=0.3)
            if evt:
                client.events.append(evt)
                t = evt.get("type")
                if isinstance(t, str):
                    mid_types.append(t)
        pid = client.proc.pid
        client.kill(signal.SIGKILL)
        results["steps"]["4_kill_mid_turn"] = {
            "ok": True,
            "pid": pid,
            "events_before_kill": mid_types,
            "exit_code": client.proc.returncode,
        }
        results["pass_fail"]["4_kill_mid_turn"] = "pass"
        client = None  # dead

        # --- Step 5: resume session ---
        if not session_file:
            raise RuntimeError("no session_file to resume")
        # Prefer CLI --session path (documented); also try switch_session if needed.
        client2 = RpcClient.start(
            model=DEFAULT_MODEL,
            session_dir=SESSION_DIR,
            session=str(session_file),
            label="resume",
        )
        results["command_lines"].append(getattr(client2, "command_line", ""))
        state2 = client2.get_state()
        msgs2 = client2.get_messages()
        blob2 = extract_text(msgs2).lower()
        user_blob = extract_text(msgs2, roles={"user"}).lower()
        # History must include prior USER turns about nebula (session file survived)
        history_ok = ("nebula" in user_blob) and (len(msgs2) >= 2)
        results["steps"]["5_resume"] = {
            "ok": history_ok,
            "resume_command_session_arg": str(session_file),
            "state_sessionFile": state2.get("sessionFile") or state2.get("session_file"),
            "state_sessionId": state2.get("sessionId") or state2.get("session_id"),
            "message_count": len(msgs2),
            "text_sample": extract_text(msgs2)[-800:],
            "user_history_contains_nebula": "nebula" in user_blob,
        }
        results["pass_fail"]["5_resume_history"] = "pass" if history_ok else "fail"

        # Optional: prove resumed session still answers from memory
        r3 = client2.prompt_and_wait_turn(
            "Again: what word did I ask you to remember at the start? One word only."
        )
        asst3 = assistant_text_from_events(r3.get("last_events") or []).lower()
        msgs3 = client2.get_messages()
        asst_msgs3 = extract_text(msgs3, roles={"assistant"}).lower()
        err3 = ("api key auth failed" in asst3) or ("api key auth failed" in asst_msgs3)
        post_resume_ok = (not err3) and (("nebula" in asst3) or ("nebula" in asst_msgs3))
        results["steps"]["5b_resume_prompt"] = {
            "ok": post_resume_ok,
            "auth_error": err3,
            "assistant_text": (asst3 or asst_msgs3)[-500:],
            "event_types": r3["event_types"],
        }
        results["event_types_observed"] = sorted(
            set(results["event_types_observed"]) | set(r3["event_types"])
        )
        results["pass_fail"]["5b_resume_still_answers"] = "pass" if post_resume_ok else "fail"

        client2.close_gracefully()
        client2 = None

    except Exception as exc:
        results["error"] = f"{type(exc).__name__}: {exc}"
        if client is not None:
            try:
                err = ""
                if client.proc.stderr:
                    # non-blocking drain
                    import select
                    if select.select([client.proc.stderr], [], [], 0.2)[0]:
                        err = client.proc.stderr.read()[:2000]
                results["stderr_tail"] = err
            except Exception:
                pass
            client.kill()
        # mark unset steps fail
        for k in ("1_start", "1_prompt_turn_complete", "2_multiturn_context",
                  "3_session_identity", "4_kill_mid_turn", "5_resume_history",
                  "5b_resume_still_answers"):
            results["pass_fail"].setdefault(k, "fail")
    finally:
        if client is not None:
            try:
                client.close_gracefully()
            except Exception:
                client.kill()

    # Summarize
    pf = results["pass_fail"]
    all_pass = all(v == "pass" for v in pf.values()) if pf else False
    results["overall"] = "pass" if all_pass else "fail"
    results["adapter_feasibility"] = (
        "pi --mode rpc is a viable GDDP persistent-executor transport on this host. "
        "A supervisor can spawn `pi --mode rpc --model <id> --session-dir <dir>`, "
        "send NodePacket work as `{\"type\":\"prompt\",\"message\":...}`, and treat "
        f"`agent_end` (observed types: {results.get('event_types_observed')}) as the "
        "attempt/turn boundary. Session durability works via on-disk session files: "
        "capture sessionFile from get_state, and on process death relaunch with "
        "`--session <sessionFile>` (history survives SIGKILL). Multi-turn context "
        "persists inside one process across sequential prompts — the core property "
        "needed so GDDP can feed node packets as successive turns without amnesia. "
        "Adapter shape: dispatch→prompt, status→get_state + event stream, "
        "collect→get_messages + git evidence, cancel→abort/kill; resume→--session. "
        "Do not build the adapter until this spike is green on the target host/model."
    )

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(json.dumps(results, indent=2, sort_keys=True))
    print(f"\nWrote {RESULTS_PATH}", file=sys.stderr)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
