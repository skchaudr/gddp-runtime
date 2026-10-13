"""GDAD node journal, decision packets, and the pi-workflow executor.

``python3 -m gdad_run journal PROJECT NODE TYPE`` is the only writer of
``status`` and ``journal.jsonl``. One flock covers the append and the status
rewrite. ``status`` is the last journal line.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_VERSION = 1
MD_CAP_BYTES = 2048
DEFAULT_DECIDER_MODEL = "claude-fable-5-1"
DEFAULT_WORKER_MODEL = "openrouter/deepseek/deepseek-v4-flash"
WHO = {
    "dispatch": "gdad-executor",
    "pause": "pi-workflow",
    "resume": "sab",
    "packet": "pi-workflow",
    "review": "gdad-executor",
    "verdict": "claude-opus",
    "steer": "sab",
    "gate": "gdad-executor",
    "blocked": "gdad-executor",
    "decision": "fable",
}
# Implicit empty journal counts as pending.
LEGAL = {
    "dispatch": {"pending", "blocked"},
    "pause": {"running"},
    "resume": {"paused"},
    "packet": {"paused", "review"},
    "review": {"running"},
    "verdict": {"review"},
    "steer": {"running", "paused", "review", "awaiting-decision"},
    "gate": {"accepted"},
    "blocked": {"pending", "running", "paused", "review", "awaiting-decision"},
    "decision": {"awaiting-decision", "blocked"},
}
DECISION_WHOS = {"fable", "sab"}


class JournalError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def runtime_root() -> Path:
    env = os.environ.get("GDDP_RUNTIME_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def config_root() -> Path:
    env = os.environ.get("GDDP_CONFIG_PATH")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    parts = here.parts
    if ".worktrees" in parts:
        idx = parts.index(".worktrees")
        name = parts[idx + 1]
        candidate = Path.home() / "gddp-config" / ".worktrees" / name
        if candidate.is_dir():
            return candidate
    sibling = Path.home() / "gddp-config"
    return sibling


def node_dir(project: str, node: str, root: Path | None = None) -> Path:
    return (root or runtime_root()) / "gdad" / project / node


def definition_dir(project: str, node: str, root: Path | None = None) -> Path:
    return (root or config_root()) / "graphs" / project / "gdad" / node


def _lock_path(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return directory / ".lock"


def _read_lines(directory: Path) -> list[dict]:
    path = directory / "journal.jsonl"
    if not path.is_file():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        lines.append(json.loads(raw))
    return lines


def _state_of(lines: list[dict]) -> str:
    if not lines:
        return "pending"
    return str(lines[-1].get("state") or "pending")


def _alloc_run_id(node: str, lines: list[dict]) -> str:
    prefix = f"{node}-"
    nums = []
    for line in lines:
        rid = str(line.get("run_id") or "")
        if rid.startswith(prefix) and rid[len(prefix):].isdigit():
            nums.append(int(rid[len(prefix):]))
    return f"{node}-{max(nums, default=0) + 1}"


def _run_id_for(node: str, lines: list[dict], typ: str, reply: dict | None) -> str:
    if typ == "decision" and reply and reply.get("reply") == "redispatch":
        return _alloc_run_id(node, lines)
    if typ == "dispatch":
        if lines and lines[-1].get("type") == "decision" and lines[-1].get("state") == "pending":
            return str(lines[-1]["run_id"])
        return _alloc_run_id(node, lines)
    if not lines:
        raise JournalError(f"{typ} needs an open run")
    return str(lines[-1]["run_id"])


def _open_dispatch(lines: list[dict], run_id: str) -> dict | None:
    found = None
    for line in lines:
        if line.get("type") == "dispatch" and line.get("run_id") == run_id:
            found = line
    return found


def _decision_state(reply: dict, lines: list[dict]) -> str:
    kind = reply.get("reply")
    if kind == "resume":
        return "running"
    if kind == "redispatch":
        return "pending"
    if kind == "next":
        verdict = _latest_verdict(lines)
        if verdict == "accept":
            return "accepted"
        return "rejected"
    raise JournalError(f"unknown reply {kind}")


def _latest_verdict(lines: list[dict]) -> str | None:
    found = None
    for line in lines:
        if line.get("type") == "verdict":
            found = line
    if not found:
        return None
    note = str(found.get("note") or "")
    if note.startswith("accept"):
        return "accept"
    if note.startswith("reject"):
        return "reject"
    return None


def _render_status(line: dict, lines: list[dict]) -> str:
    dispatch = _open_dispatch(lines, str(line.get("run_id") or ""))
    if line.get("type") == "dispatch":
        request_id = str(line.get("request_id") or "")
        wid = str(line.get("wid") or "")
    elif dispatch:
        request_id = str(dispatch.get("request_id") or "")
        wid = str(dispatch.get("wid") or "")
    else:
        request_id = ""
        wid = ""
    return (
        f"state: {line['state']}\n"
        f"who: {line['who']}\n"
        f"when: {line['ts']}\n"
        f"run_id: {line['run_id']}\n"
        f"request_id: {request_id}\n"
        f"wid: {wid}\n"
    )


def _write_status(directory: Path, text: str) -> None:
    target = directory / "status"
    tmp = directory / f".status.{os.getpid()}.tmp"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def validate_reply(obj: object, packet_id: str | None = None) -> dict:
    """Return the reply dict or raise JournalError. Matches reply.schema.json."""
    if not isinstance(obj, dict):
        raise JournalError("reply must be a JSON object")
    reply = obj.get("reply")
    pid = obj.get("packet_id")
    if not isinstance(pid, str) or not pid:
        raise JournalError("reply.packet_id is required")
    if packet_id is not None and pid != packet_id:
        raise JournalError(f"reply packet_id {pid} does not match {packet_id}")
    keys = set(obj)
    if reply == "resume":
        if keys == {"reply", "packet_id", "option_id"} and isinstance(obj.get("option_id"), str) and obj["option_id"]:
            return obj
        if keys == {"reply", "packet_id", "decision"} and isinstance(obj.get("decision"), str) and obj["decision"]:
            return obj
        raise JournalError("resume reply needs option_id or decision, and no other fields")
    if reply == "redispatch":
        if keys == {"reply", "packet_id", "changes"} and isinstance(obj.get("changes"), str) and obj["changes"]:
            return obj
        raise JournalError("redispatch reply needs changes, and no other fields")
    if reply == "next":
        if keys != {"reply", "packet_id", "workflow"}:
            raise JournalError("next reply needs workflow and no other fields")
        workflow = obj.get("workflow")
        if workflow is None or (isinstance(workflow, str) and workflow):
            return obj
        raise JournalError("next workflow must be a string or null")
    raise JournalError("reply must be resume, redispatch, or next")


def journal(
    project: str,
    node: str,
    typ: str,
    *,
    note: str | None = None,
    artifacts: list[str] | None = None,
    who: str | None = None,
    request_id: str | None = None,
    wid: str | None = None,
    reply: dict | None = None,
    verdict: str | None = None,
    repo: Path | str | None = None,
    verdict_path: Path | str | None = None,
    root: Path | None = None,
) -> dict:
    """Append one journal line and rewrite status. Raises JournalError with no write."""
    if typ not in LEGAL:
        raise JournalError(f"unknown journal type {typ}")
    directory = node_dir(project, node, root)
    lock = _lock_path(directory)
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            line = _journal_locked(
                directory, project, node, typ,
                note=note, artifacts=artifacts, who=who,
                request_id=request_id, wid=wid,
                reply=reply, verdict=verdict, repo=repo, verdict_path=verdict_path,
            )
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    if _pi_work_finished(line):
        release_pi_pane(project, node, root)
    return line


def _journal_locked(
    directory: Path,
    project: str,
    node: str,
    typ: str,
    *,
    note: str | None,
    artifacts: list[str] | None,
    who: str | None,
    request_id: str | None,
    wid: str | None,
    reply: dict | None,
    verdict: str | None,
    repo: Path | str | None,
    verdict_path: Path | str | None,
) -> dict:
    lines = _read_lines(directory)
    state = _state_of(lines)
    if state not in LEGAL[typ]:
        raise JournalError(f"{typ} is illegal from {state}")
    actor = WHO[typ]
    if typ == "decision":
        if reply is None:
            raise JournalError("decision requires a reply")
        reply = validate_reply(reply)
        if who is not None and who not in DECISION_WHOS:
            raise JournalError("decision who must be fable or sab")
        actor = who or "fable"
        new_state = _decision_state(reply, lines)
        note = note or f"{reply['reply']}: {reply.get('changes') or reply.get('option_id') or reply.get('decision') or reply.get('workflow')}"
    elif typ == "verdict":
        if verdict not in ("accept", "reject"):
            raise JournalError("verdict requires accept or reject")
        new_state = "review"
        note = verdict if not note else f"{verdict}: {note}"
    elif typ == "steer":
        new_state = state
    else:
        if who is not None and who != actor:
            raise JournalError(f"{typ} who is {actor}")
        new_state = {
            "dispatch": "running",
            "pause": "paused",
            "resume": "running",
            "packet": "awaiting-decision",
            "review": "review",
            "gate": "accepted",
            "blocked": "blocked",
        }[typ]
    if typ == "dispatch":
        if not request_id or not wid:
            raise JournalError("dispatch requires request_id and wid")
    run_id = _run_id_for(node, lines, typ, reply)
    arts = list(artifacts or [])
    token_path = None
    if typ == "gate":
        token_path = _issue_gate(repo, node, verdict_path)
        arts = [str(token_path)]
    line = {
        "v": JOURNAL_VERSION,
        "ts": _utc_now(),
        "type": typ,
        "who": actor,
        "state": new_state,
        "run_id": run_id,
        "artifacts": arts,
    }
    if note:
        line["note"] = note
    if typ == "dispatch":
        line["request_id"] = request_id
        line["wid"] = wid
    journal_path = directory / "journal.jsonl"
    previous = journal_path.stat().st_size if journal_path.is_file() else 0
    payload = json.dumps(line, separators=(",", ":")) + "\n"
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        _write_status(directory, _render_status(line, lines + [line]))
    except Exception:
        with journal_path.open("a+", encoding="utf-8") as handle:
            handle.truncate(previous)
        raise
    if typ == "decision" and reply is not None:
        _mark_packet_resolved(directory, str(reply["packet_id"]))
    return line


def _issue_gate(repo: Path | str | None, node: str, verdict_path: Path | str | None) -> Path:
    if repo is None or verdict_path is None:
        raise JournalError("gate requires repo and verdict_path")
    verdict = Path(verdict_path)
    if not verdict.is_file():
        raise JournalError(f"verdict file missing: {verdict}")
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from runtime.gate_tokens import write_gate

    written = write_gate(repo, node, verdict_receipt_path=str(verdict))
    if written is None:
        raise JournalError("gate token was not written")
    return Path(written)


def _mark_packet_resolved(directory: Path, packet_id: str) -> None:
    path = directory / "packets" / f"{packet_id}.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data["open"] = False
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_status(project: str, node: str, root: Path | None = None) -> dict:
    directory = node_dir(project, node, root)
    lines = _read_lines(directory)
    if not lines:
        return {"state": "pending", "who": "", "when": "", "run_id": "", "request_id": "", "wid": ""}
    text = (directory / "status").read_text(encoding="utf-8")
    out = {}
    for line in text.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            out[key] = value
    return out


def current_state(project: str, node: str, root: Path | None = None) -> str:
    return _state_of(_read_lines(node_dir(project, node, root)))


def ensure_pause(project: str, node: str, note: str, root: Path | None = None) -> dict | None:
    state = current_state(project, node, root)
    if state == "running":
        return journal(project, node, "pause", note=note, root=root)
    if state in {"paused", "awaiting-decision"}:
        return None
    raise JournalError(f"pause is illegal from {state}")


def mark_resumed(project: str, node: str, root: Path | None = None) -> dict | None:
    """Journal resume only when the decider has not already moved the node to running."""
    state = current_state(project, node, root)
    if state == "paused":
        return journal(project, node, "resume", root=root)
    if state == "running":
        return None
    raise JournalError(f"resume is illegal from {state}")


def _next_packet_id(directory: Path) -> str:
    packets = directory / "packets"
    packets.mkdir(parents=True, exist_ok=True)
    nums = []
    for path in packets.glob("pkt-*.json"):
        suffix = path.stem.split("-", 1)[-1]
        if suffix.isdigit():
            nums.append(int(suffix))
    return f"pkt-{max(nums, default=0) + 1}"


def _render_packet_md(packet: dict, suggested: str) -> str:
    done = packet["done"][:5]
    option_lines = [f"- {opt['id']}: {opt['label']} ({opt['consequence']})" for opt in packet["options"]]
    evidence = packet["evidence"]
    if not isinstance(evidence, str):
        evidence = json.dumps(evidence)
    parts = [
        f"# {packet['kind']} {packet['packet_id']}",
        f"project `{packet['project']}` node `{packet['node']}` run `{packet['run_id']}`",
        "",
        "## Question",
        packet["question"],
        "",
        "## Reply",
        "Answer with exactly one JSON object and no other text.",
        suggested,
        "",
        "## Done",
        *[f"- {item}" for item in done],
        "",
        "## Options",
        *option_lines,
        "",
        "## Evidence",
        evidence,
        "",
        "## Artifacts",
        *[f"- {path}" for path in packet["artifacts"]],
        "",
        "## Resume",
        json.dumps(packet["resume_handle"]),
        "",
    ]
    text = "\n".join(parts)
    raw = text.encode("utf-8")
    if len(raw) > MD_CAP_BYTES:
        text = raw[: MD_CAP_BYTES - 1].decode("utf-8", errors="ignore") + "\n"
    return text


def write_packet(
    project: str,
    node: str,
    *,
    kind: str,
    question: str,
    done: list[str],
    options: list[dict],
    evidence: str,
    artifacts: list[str],
    checkpoint: str,
    suggested: str,
    root: Path | None = None,
) -> dict:
    if kind not in {"verdict", "ambiguity", "acceptance"}:
        raise JournalError(f"unknown packet kind {kind}")
    directory = node_dir(project, node, root)
    status = read_status(project, node, root)
    packet_id = _next_packet_id(directory)
    packet = {
        "packet_id": packet_id,
        "project": project,
        "node": node,
        "run_id": status.get("run_id") or "",
        "kind": kind,
        "done": done[:5],
        "question": question,
        "options": options,
        "evidence": evidence,
        "artifacts": artifacts,
        "resume_handle": {
            "wid": status.get("wid") or "",
            "qid": "",
            "rev": 0,
        },
        "open": True,
    }
    rendered = _render_packet_md(packet, suggested)
    folder = directory / "packets"
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / f"{packet_id}.json"
    md_path = folder / f"{packet_id}.md"
    json_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(rendered, encoding="utf-8")
    try:
        journal(
            project, node, "packet",
            note=f"{packet_id} {kind}",
            artifacts=[str(md_path)],
            root=root,
        )
    except Exception:
        json_path.unlink(missing_ok=True)
        md_path.unlink(missing_ok=True)
        raise
    return packet


def load_packet(project: str, node: str, packet_id: str, root: Path | None = None) -> dict:
    path = node_dir(project, node, root) / "packets" / f"{packet_id}.json"
    if not path.is_file():
        raise JournalError(f"packet {packet_id} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def find_packet_node(packet_id: str, root: Path | None = None) -> tuple[str, str]:
    base = (root or runtime_root()) / "gdad"
    if not base.is_dir():
        raise JournalError(f"packet {packet_id} not found")
    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        for node_path in project_dir.iterdir():
            candidate = node_path / "packets" / f"{packet_id}.json"
            if candidate.is_file():
                return project_dir.name, node_path.name
    raise JournalError(f"packet {packet_id} not found")


def open_packets(project: str | None = None, node: str | None = None, root: Path | None = None) -> list[dict]:
    base = (root or runtime_root()) / "gdad"
    found = []
    if not base.is_dir():
        return found
    projects = [base / project] if project else list(base.iterdir())
    for project_dir in projects:
        if not project_dir.is_dir():
            continue
        nodes = [project_dir / node] if node else list(project_dir.iterdir())
        for node_path in nodes:
            folder = node_path / "packets"
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("pkt-*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("open") is True:
                    found.append(data)
    return found


def _artifact_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def claude_invocation_argv(model: str, prompt: str, *, tools: str) -> list[str]:
    return [
        "claude",
        "-p",
        "--model",
        model,
        "--output-format",
        "json",
        "--tools",
        tools,
        prompt,
    ]


def _run_claude(model: str, prompt: str, *, tools: str) -> tuple[int, str]:
    proc = subprocess.run(
        claude_invocation_argv(model, prompt, tools=tools),
        text=True,
        capture_output=True,
        check=False,
    )
    raw = proc.stdout or ""
    if not raw.strip() and proc.stderr:
        raw = proc.stderr
    return proc.returncode, raw


def parse_claude_envelope(raw: str) -> dict:
    start = raw.find("{")
    if start < 0:
        raise JournalError("claude returned no JSON envelope")
    try:
        env = json.loads(raw[start:])
    except json.JSONDecodeError as exc:
        raise JournalError(f"claude envelope is not JSON: {exc}") from exc
    if env.get("type") != "result" or env.get("is_error") or env.get("subtype") != "success":
        raise JournalError("claude envelope is not a successful result")
    result = env.get("result")
    if not isinstance(result, str):
        raise JournalError("claude result is not a string")
    try:
        obj = json.loads(result)
    except json.JSONDecodeError as exc:
        raise JournalError(f"claude result is not JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise JournalError("claude result JSON is not an object")
    return obj


def parse_verdict_object(obj: dict) -> dict:
    verdict = obj.get("verdict")
    reasons = obj.get("reasons")
    if verdict not in {"accept", "reject"}:
        raise JournalError("verdict must be accept or reject")
    if not isinstance(reasons, list) or not reasons or not all(isinstance(item, str) and item for item in reasons):
        raise JournalError("reasons must be a non-empty list of strings")
    if set(obj) != {"verdict", "reasons"}:
        raise JournalError("verdict object has unexpected fields")
    return obj


def review_node(project: str, node: str, root: Path | None = None, cfg: Path | None = None) -> dict:
    """Run the Opus reviewer. A bad parse journals blocked and never accepts."""
    cfg = cfg or config_root()
    runtime = root or runtime_root()
    status = read_status(project, node, runtime)
    run_id = status.get("run_id") or ""
    artifacts = node_dir(project, node, runtime) / "runs" / run_id / "artifacts"
    hello = artifacts / "hello.txt"
    listing = sorted(str(path.relative_to(node_dir(project, node, runtime))) for path in artifacts.rglob("*") if path.is_file()) if artifacts.is_dir() else []
    brief = (definition_dir(project, node, cfg) / "BRIEF.md").read_text(encoding="utf-8")
    template = (cfg / "schemas" / "gdad" / "review-prompt.md").read_text(encoding="utf-8")
    body = hello.read_text(encoding="utf-8") if hello.is_file() else ""
    count = len(_artifact_lines(hello))
    prompt = template
    for key, value in {
        "brief": brief,
        "listing": "\n".join(listing) or "(none)",
        "hello": body or "(missing)",
        "count": str(count),
        "verdict_path": str(artifacts / "verdict.json"),
    }.items():
        prompt = prompt.replace("{" + key + "}", value)
    journal(project, node, "review", artifacts=[str(hello)] if hello.is_file() else [], root=runtime)
    code, raw = _run_claude("opus", prompt, tools="")
    raw_path = artifacts / "review-raw.txt"
    artifacts.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(raw, encoding="utf-8")
    verdict_path = artifacts / "verdict.json"
    try:
        if code != 0:
            raise JournalError(f"claude exited {code}")
        obj = parse_verdict_object(parse_claude_envelope(raw))
        verdict_path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    except (JournalError, json.JSONDecodeError, OSError) as exc:
        journal(project, node, "blocked", note=str(exc), artifacts=[str(raw_path)], root=runtime)
        raise
    journal(
        project, node, "verdict",
        verdict=obj["verdict"],
        note="; ".join(obj["reasons"]),
        artifacts=[str(verdict_path)],
        root=runtime,
    )
    _write_review_packet(project, node, obj, listing, runtime)
    return obj


def _write_review_packet(project: str, node: str, verdict: dict, listing: list[str], root: Path) -> dict:
    reasons = "; ".join(verdict["reasons"])
    if verdict["verdict"] == "reject":
        changes = (
            "Worker A: write exactly one line, the single word one, to hello-a.txt and no other file. "
            "Worker B: write exactly one line, the single word two, to hello-b.txt and no other file. "
            "Do not write hello.txt."
        )
        return _packet_with_suggestion(
            project, node, root,
            kind="verdict",
            question=f"hello.txt failed acceptance ({reasons}). Redispatch so the workers write exactly two lines.",
            done=[f"Opus rejected: {reasons}"],
            options=[{"id": "redispatch", "label": "Redispatch", "consequence": "New run writes exactly two lines"}],
            evidence=reasons,
            artifacts=listing,
            checkpoint="",
            changes=changes,
        )
    return _packet_with_suggestion(
        project, node, root,
        kind="acceptance",
        question="Opus accepted hello.txt. Close this node with next and workflow null.",
        done=[f"Opus accepted: {reasons}"],
        options=[{"id": "close", "label": "Close", "consequence": "Issue the gate and mark the node accepted"}],
        evidence=reasons,
        artifacts=listing,
        checkpoint="acceptance",
        changes=None,
    )


def _packet_with_suggestion(
    project: str,
    node: str,
    root: Path,
    *,
    kind: str,
    question: str,
    done: list[str],
    options: list[dict],
    evidence: str,
    artifacts: list[str],
    checkpoint: str,
    changes: str | None,
) -> dict:
    """Write the packet, then fill the suggested reply once the id exists."""
    directory = node_dir(project, node, root)
    status = read_status(project, node, root)
    packet_id = _next_packet_id(directory)
    if kind == "verdict":
        suggested = json.dumps({
            "reply": "redispatch",
            "packet_id": packet_id,
            "changes": changes,
        })
    else:
        suggested = json.dumps({
            "reply": "next",
            "packet_id": packet_id,
            "workflow": None,
        })
    packet = {
        "packet_id": packet_id,
        "project": project,
        "node": node,
        "run_id": status.get("run_id") or "",
        "kind": kind,
        "done": done[:5],
        "question": question,
        "options": options,
        "evidence": evidence,
        "artifacts": artifacts,
        "resume_handle": {
            "wid": status.get("wid") or "",
            "qid": "",
            "rev": 0,
        },
        "open": True,
    }
    rendered = _render_packet_md(packet, suggested)
    folder = directory / "packets"
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / f"{packet_id}.json"
    md_path = folder / f"{packet_id}.md"
    json_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(rendered, encoding="utf-8")
    try:
        journal(project, node, "packet", note=f"{packet_id} {kind}", artifacts=[str(md_path)], root=root)
    except Exception:
        json_path.unlink(missing_ok=True)
        md_path.unlink(missing_ok=True)
        raise
    return packet


def ambiguity_packet(project: str, node: str, root: Path | None = None) -> dict:
    """Journal pause, then write the after-workers ambiguity packet."""
    root = root or runtime_root()
    ensure_pause(project, node, "checkpoint after-workers", root=root)
    status = read_status(project, node, root)
    run_id = status.get("run_id") or ""
    artifacts = node_dir(project, node, root) / "runs" / run_id / "artifacts"
    listing = sorted(str(path) for path in artifacts.rglob("*") if path.is_file()) if artifacts.is_dir() else []
    directory = node_dir(project, node, root)
    packet_id = _next_packet_id(directory)
    suggested = json.dumps({"reply": "resume", "packet_id": packet_id, "option_id": "resume"})
    packet = {
        "packet_id": packet_id,
        "project": project,
        "node": node,
        "run_id": run_id,
        "kind": "ambiguity",
        "done": ["Workers finished", "hello.txt is the concatenation of hello-a.txt and hello-b.txt"],
        "question": "Workers finished. Resume the workflow so the reviewer can run?",
        "options": [{"id": "resume", "label": "Resume", "consequence": "Continue to the Opus review"}],
        "evidence": "checkpoint after-workers",
        "artifacts": listing,
        "resume_handle": {"wid": status.get("wid") or "", "qid": "", "rev": 0},
        "open": True,
    }
    rendered = _render_packet_md(packet, suggested)
    folder = directory / "packets"
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / f"{packet_id}.json"
    md_path = folder / f"{packet_id}.md"
    json_path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(rendered, encoding="utf-8")
    try:
        journal(project, node, "packet", note=f"{packet_id} ambiguity", artifacts=[str(md_path)], root=root)
    except Exception:
        json_path.unlink(missing_ok=True)
        md_path.unlink(missing_ok=True)
        raise
    return packet


def decide(
    packet_id: str,
    reply: dict,
    *,
    who: str = "fable",
    root: Path | None = None,
    perform: bool = True,
) -> dict:
    """Validate a reply, journal decision, and perform it. Invalid replies block once."""
    root = root or runtime_root()
    project, node = find_packet_node(packet_id, root)
    packet = load_packet(project, node, packet_id, root)
    if packet.get("open") is not True:
        raise JournalError(f"packet {packet_id} is already decided")
    try:
        reply = validate_reply(reply, packet_id)
    except JournalError as exc:
        journal(project, node, "blocked", note=f"invalid reply: {exc}", root=root)
        raise
    line = journal(project, node, "decision", reply=reply, who=who, artifacts=[str(node_dir(project, node, root) / "packets" / f"{packet_id}.json")], root=root)
    if not perform:
        return line
    kind = reply["reply"]
    if kind == "redispatch":
        _write_changes_prompt(project, node, line["run_id"], reply["changes"], root)
        return line
    if kind == "next":
        if line["state"] == "accepted":
            _gate_from_latest(project, node, root)
        return line
    if kind == "resume":
        _perform_resume(project, node, packet, root)
        if packet.get("kind") == "acceptance" and _latest_verdict(_read_lines(node_dir(project, node, root))) == "accept":
            _gate_from_latest(project, node, root)
        return line
    return line


def _write_changes_prompt(project: str, node: str, run_id: str, changes: str, root: Path) -> None:
    art = node_dir(project, node, root) / "runs" / run_id / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    text = (
        f"{changes.strip()}\n\n"
        f"Artifacts directory: {art}\n"
        "Create hello-a.txt and hello-b.txt in that directory and nowhere else.\n"
    )
    (node_dir(project, node, root) / "runs" / run_id / "prompt.txt").write_text(text, encoding="utf-8")


def _latest_verdict_path(project: str, node: str, root: Path) -> Path | None:
    lines = _read_lines(node_dir(project, node, root))
    for line in reversed(lines):
        if line.get("type") == "verdict":
            for art in line.get("artifacts") or []:
                path = Path(str(art))
                if path.is_file():
                    return path
    return None


def _gate_from_latest(project: str, node: str, root: Path) -> dict:
    verdict = _latest_verdict_path(project, node, root)
    if verdict is None:
        raise JournalError("no verdict file to pin the gate to")
    repo = _gate_repo()
    return journal(project, node, "gate", repo=repo, verdict_path=verdict, root=root)


def _gate_repo() -> Path:
    env = os.environ.get("GDAD_GATE_REPO")
    if env:
        return Path(env).expanduser().resolve()
    return config_root()


def decider_model() -> str:
    return _setting("GDAD_DECIDER_MODEL") or DEFAULT_DECIDER_MODEL


def worker_model() -> str:
    return _setting("GDAD_WORKER_MODEL") or DEFAULT_WORKER_MODEL


def _setting(name: str) -> str:
    raw = os.environ.get(name, "")
    if raw:
        return raw
    settings = config_root() / "runtime" / "settings.env"
    if not settings.is_file():
        return ""
    for line in settings.read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def pi_bin() -> Path:
    raw = _setting("GDAD_PI_BIN")
    if not raw:
        raise JournalError("GDAD_PI_BIN is empty")
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise JournalError(f"GDAD_PI_BIN is not a directory: {path}")
    return path


def dsa_cmd(*args: str, wait_ms: int | None = None) -> subprocess.CompletedProcess[str]:
    bindir = pi_bin()
    env = os.environ.copy()
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    command = [str(bindir / "pi-durable-subagents"), *args]
    if wait_ms is not None and "--wait-ms" not in args:
        command.extend(["--wait-ms", str(wait_ms)])
    return subprocess.run(command, text=True, capture_output=True, env=env, check=False)


def _dsa_json(proc: subprocess.CompletedProcess[str]) -> dict:
    raw = (proc.stdout or "").strip()
    start = raw.find("{")
    if start < 0:
        raise JournalError(proc.stderr.strip() or raw or f"pi-durable-subagents exited {proc.returncode}")
    try:
        return json.loads(raw[start:])
    except json.JSONDecodeError as exc:
        raise JournalError(f"pi-durable-subagents returned non-JSON: {exc}") from exc


def workflow_tool_name(extension_js: str | None = None) -> str:
    path = Path(extension_js or extensions()[0])
    text = path.read_text(encoding="utf-8", errors="replace")
    if 'name: "piewf_workflow"' in text or "name: 'piewf_workflow'" in text:
        return "piewf_workflow"
    return "workflow"


def _safe_part(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", value)


def discover_workflow_run_ids(session_id: str, name: str | None = None) -> list[str]:
    root = Path.home() / ".pi" / "workflows" / "projects"
    if not root.is_dir():
        return []
    sid = _safe_part(session_id)
    scored: list[tuple[float, str]] = []
    for runs in root.glob(f"*/sessions/{sid}/runs"):
        if not runs.is_dir():
            continue
        for child in runs.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            summary_path = child / "summary.json"
            wname = ""
            if summary_path.is_file():
                try:
                    wname = str(json.loads(summary_path.read_text(encoding="utf-8")).get("workflowName") or "")
                except (json.JSONDecodeError, OSError):
                    wname = ""
            if name and wname and wname != name:
                continue
            scored.append((child.stat().st_mtime, child.name))
    scored.sort()
    return [run_id for _, run_id in scored]


def workflow_failure(session_id: str, run_id: str) -> str | None:
    root = Path.home() / ".pi" / "workflows" / "projects"
    sid = _safe_part(session_id)
    for summary_path in root.glob(f"*/sessions/{sid}/runs/{run_id}/summary.json"):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if summary.get("state") == "failed":
            err = summary.get("error") or {}
            return str(err.get("message") or err or "workflow failed")
    return None


def wait_running(project: str, node: str, timeout: float = 180.0, root: Path | None = None) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if current_state(project, node, root) == "running":
            return
        time.sleep(0.5)
    raise JournalError("timed out waiting for running")


def _herdr_proc(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["herdr", *args], text=True, capture_output=True, check=False)


def _herdr_json(args: list[str]) -> dict:
    proc = _herdr_proc(args)
    if proc.returncode != 0:
        raise JournalError(proc.stderr.strip() or proc.stdout.strip() or f"herdr {' '.join(args)} failed")
    raw = proc.stdout.strip()
    start = raw.find("{")
    if start < 0:
        raise JournalError(f"herdr returned no JSON: {raw[:200]}")
    return json.loads(raw[start:])


def _focused_workspace() -> str:
    data = _herdr_json(["tab", "list"])
    tabs = data.get("result", {}).get("tabs", [])
    for tab in tabs:
        if tab.get("focused") is True:
            return str(tab["workspace_id"])
    if tabs:
        return str(tabs[0]["workspace_id"])
    raise JournalError("herdr has no workspace")


def _pane_alive(pane_id: str) -> bool:
    if not pane_id:
        return False
    proc = _herdr_proc(["pane", "get", pane_id])
    return proc.returncode == 0


def _pi_work_finished(line: dict) -> bool:
    """True when the pi pane has nothing left to host."""
    if line.get("state") in {"accepted", "rejected", "blocked"}:
        return True
    if line.get("type") != "packet":
        return False
    parts = str(line.get("note") or "").split(" ", 1)
    kind = parts[1] if len(parts) == 2 else ""
    return kind in {"verdict", "acceptance"}


def _tab_rows() -> list[dict]:
    data = _herdr_json(["tab", "list"])
    return [tab for tab in data.get("result", {}).get("tabs", []) if isinstance(tab, dict)]


def _close_tab(tab_id: str) -> None:
    if tab_id:
        _herdr_proc(["tab", "close", tab_id])


def _close_gdad_tabs(node: str, *, keep: str | None) -> None:
    label = f"gdad-{node}"
    try:
        rows = _tab_rows()
    except JournalError:
        return
    for tab in rows:
        if str(tab.get("label") or "") != label:
            continue
        tab_id = str(tab.get("tab_id") or "")
        if keep and tab_id == keep:
            continue
        _close_tab(tab_id)


def _pi_pids(pane_id: str) -> list[int]:
    proc = _herdr_proc(["pane", "process-info", "--pane", pane_id])
    if proc.returncode != 0:
        return []
    raw = proc.stdout or ""
    start = raw.find("{")
    if start < 0:
        return []
    try:
        data = json.loads(raw[start:])
    except json.JSONDecodeError:
        return []
    info = data.get("result", {}).get("process_info", {})
    pids: list[int] = []
    for item in info.get("foreground_processes") or []:
        if not isinstance(item, dict):
            continue
        argv = item.get("argv") or []
        name = str(item.get("name") or "")
        if name != "pi" and not (argv and argv[0] == "pi"):
            continue
        try:
            pid = int(item.get("pid") or 0)
        except (TypeError, ValueError):
            continue
        if pid > 1 and pid != os.getpid():
            pids.append(pid)
    return pids


def _stop_pi(pane_id: str) -> None:
    for pid in _pi_pids(pane_id):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def live_pane_id(project: str, node: str, root: Path | None = None) -> str:
    root = root or runtime_root()
    recorded = _load_pane(project, node, root)
    pane_id = str(recorded.get("pane_id") or "")
    if pane_id and _pane_alive(pane_id):
        return pane_id
    return "none"


def _load_pane(project: str, node: str, root: Path) -> dict:
    path = node_dir(project, node, root) / "pane.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_pane(project: str, node: str, root: Path, pane: dict) -> None:
    path = node_dir(project, node, root) / "pane.json"
    path.write_text(json.dumps(pane, indent=2) + "\n", encoding="utf-8")


def _pi_env(project: str, node: str, run_id: str, root: Path) -> dict[str, str]:
    art = node_dir(project, node, root) / "runs" / run_id / "artifacts"
    prompt = node_dir(project, node, root) / "runs" / run_id / "prompt.txt"
    scripts = str(Path(__file__).resolve().parent)
    return {
        "GDDP_RUNTIME_ROOT": str(root),
        "GDDP_CONFIG_PATH": str(config_root()),
        "GDAD_GATE_REPO": str(_gate_repo()),
        "PYTHONPATH": scripts,
        "GDAD_PROJECT": project,
        "GDAD_NODE": node,
        "GDAD_RUN_ID": run_id,
        "GDAD_PROMPT_FILE": str(prompt),
        "GDAD_ARTIFACTS": str(art),
        "GDAD_WORKER_SH": str(definition_dir(project, node) / "worker.sh"),
        "GDAD_SCRIPT": str(definition_dir(project, node) / "workflow.js"),
        "GDAD_REPLAY": str(node_dir(project, node, root) / "runs" / run_id / "replay.jsonl"),
        "GDAD_RELEASE": str(node_dir(project, node, root) / "runs" / run_id / "release"),
    }


def _prepare_prompt(project: str, node: str, run_id: str, root: Path, cfg: Path) -> None:
    run = node_dir(project, node, root) / "runs" / run_id
    art = run / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    prompt_path = run / "prompt.txt"
    if prompt_path.is_file():
        return
    first = definition_dir(project, node, cfg) / "first-prompt.txt"
    if not first.is_file():
        raise JournalError(f"missing {first}")
    text = first.read_text(encoding="utf-8").rstrip() + f"\n\nArtifacts directory: {art}\n"
    prompt_path.write_text(text, encoding="utf-8")


def _pi_pane_command(session_id: str) -> list[str]:
    bindir = pi_bin()
    extension = bindir.parent / "lib" / "node_modules" / "pi-durable-subagents" / "index.js"
    if not extension.is_file():
        raise JournalError(f"pi-durable-subagents extension missing: {extension}")
    return [
        str(bindir / "pi"), "-ne", "-e", str(extension),
        "--session-id", session_id,
        "This session hosts the line-pair workflow. Leave it running.",
    ]


def release_pi_pane(project: str, node: str, root: Path | None = None) -> None:
    """Close this node's gdad tab and stop its pi process. No-op without pane.json."""
    root = root or runtime_root()
    recorded = _load_pane(project, node, root)
    if not recorded:
        return
    pane_id = str(recorded.get("pane_id") or "")
    if pane_id and _pane_alive(pane_id):
        _stop_pi(pane_id)
    _close_gdad_tabs(node, keep=None)
    _close_tab(str(recorded.get("tab_id") or ""))
    (node_dir(project, node, root) / "pane.json").unlink(missing_ok=True)


def _run_pi_in_pane(pane_id: str, session_id: str) -> None:
    command = _pi_pane_command(session_id)
    proc = _herdr_proc(["pane", "run", pane_id, *command])
    if proc.returncode != 0:
        raise JournalError(proc.stderr.strip() or "herdr pane run failed")


def _create_pi_pane(project: str, node: str, run_id: str, session_id: str, root: Path) -> dict:
    _close_gdad_tabs(node, keep=None)
    _prepare_prompt(project, node, run_id, root, config_root())
    cwd_path = node_dir(project, node, root) / "pi-cwd"
    cwd_path.mkdir(parents=True, exist_ok=True)
    cwd = str(cwd_path)
    env_args: list[str] = []
    for key, value in _pi_env(project, node, run_id, root).items():
        env_args.extend(["--env", f"{key}={value}"])
    created = _herdr_json([
        "tab", "create",
        "--workspace", _focused_workspace(),
        "--cwd", cwd,
        "--label", f"gdad-{node}",
        "--no-focus",
        *env_args,
    ])
    pane = created["result"]["root_pane"]
    tab = created["result"]["tab"]
    if pane.get("focused") is True or tab.get("focused") is True:
        _close_tab(str(tab["tab_id"]))
        raise JournalError("herdr focused the new tab; closed it")
    _run_pi_in_pane(str(pane["pane_id"]), session_id)
    record = {"tab_id": tab["tab_id"], "pane_id": pane["pane_id"], "pi_session_id": session_id, "cwd": cwd}
    _save_pane(project, node, root, record)
    return record


def ensure_pi_pane(project: str, node: str, run_id: str, *, session_id: str | None = None, root: Path | None = None) -> dict:
    """Reuse pane.json's live pane. Otherwise close any older gdad tab and create one."""
    root = root or runtime_root()
    recorded = _load_pane(project, node, root)
    pane_id = str(recorded.get("pane_id") or "")
    tab_id = str(recorded.get("tab_id") or "")
    if pane_id and _pane_alive(pane_id):
        _close_gdad_tabs(node, keep=tab_id)
        if not _pi_pids(pane_id):
            session_id = str(recorded.get("pi_session_id") or session_id or uuid.uuid4())
            _run_pi_in_pane(pane_id, session_id)
            recorded["pi_session_id"] = session_id
            _save_pane(project, node, root, recorded)
        return _load_pane(project, node, root)
    _close_tab(tab_id)
    return _create_pi_pane(project, node, run_id, session_id or str(uuid.uuid4()), root)


def launch_pi(project: str, node: str, run_id: str, *, resume_prompt: str | None = None, session_id: str | None = None, root: Path | None = None) -> dict:
    return ensure_pi_pane(project, node, run_id, session_id=session_id, root=root)


def _perform_resume(project: str, node: str, packet: dict, root: Path) -> None:
    handle = packet.get("resume_handle") or {}
    wid = str(handle.get("wid") or read_status(project, node, root).get("wid") or "")
    qid = str(handle.get("qid") or "")
    rev = handle.get("rev")
    if not wid or not qid or rev is None:
        raise JournalError("resume handle needs wid, qid, and rev")
    message = str(packet.get("question") or "resume")
    # Request ids are global in pi-durable-subagents. Packet ids restart per node,
    # so key the answer on the question id or a later packet collides with an old one.
    request = f"answer-{qid}"
    pane = _load_pane(project, node, root)
    if pane.get("pane_id") and not _pane_alive(str(pane["pane_id"])):
        resumed = dsa_cmd("resume", wid)
        if resumed.returncode not in {0, 75}:
            raise JournalError(resumed.stderr.strip() or "resume was refused")
        if pane.get("pi_session_id"):
            launch_pi(project, node, packet["run_id"], session_id=str(pane["pi_session_id"]), root=root)
    target = str(handle.get("to") or f"{wid}/gate")
    proc = dsa_cmd(
        "send", "--request", request, "--to", target, "--kind", "answer",
        "--qid", qid, "--rev", str(rev), "--message", message, "--json",
        wait_ms=20000,
    )
    if proc.returncode not in {0, 75}:
        raise JournalError(proc.stderr.strip() or proc.stdout.strip() or "answer was refused")


def prompt_fable(packet_md: str, cfg: Path | None = None) -> dict:
    cfg = cfg or config_root()
    template = (cfg / "schemas" / "gdad" / "decider-prompt.md").read_text(encoding="utf-8")
    code, raw = _run_claude(decider_model(), template + "\n\n" + packet_md, tools="")
    if code != 0:
        raise JournalError(f"fable exited {code}")
    return parse_claude_envelope(raw)


def follow(project: str, node: str, *, decider: str, timeout: float, root: Path | None = None) -> str:
    """Print new journal lines. With fable, decide each new open packet once."""
    root = root or runtime_root()
    path = node_dir(project, node, root) / "journal.jsonl"
    pos = path.stat().st_size if path.is_file() else 0
    decided: set[str] = set()
    deadline = time.time() + timeout
    last_state = current_state(project, node, root)
    while time.time() < deadline:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if len(text) > pos:
                sys.stdout.write(text[pos:])
                sys.stdout.flush()
                pos = len(text)
            last_state = current_state(project, node, root)
        if last_state == "pending":
            lines = _read_lines(node_dir(project, node, root))
            if lines and lines[-1].get("type") == "decision" and lines[-1].get("state") == "pending":
                _launch_and_dispatch(project, node, str(lines[-1]["run_id"]), root)
                last_state = current_state(project, node, root)
                continue
        if last_state == "awaiting-decision":
            if decider == "none":
                return last_state
            if decider == "fable":
                opened = open_packets(project, node, root)
                fresh = [pkt for pkt in opened if pkt["packet_id"] not in decided]
                if not fresh:
                    time.sleep(0.5)
                    continue
                pkt = fresh[-1]
                decided.add(pkt["packet_id"])
                md = (node_dir(project, node, root) / "packets" / f"{pkt['packet_id']}.md").read_text(encoding="utf-8")
                try:
                    reply = prompt_fable(md)
                    decide(pkt["packet_id"], reply, who="fable", root=root)
                except JournalError as exc:
                    print(f"decider blocked: {exc}", file=sys.stderr)
                    return current_state(project, node, root)
                continue
        if last_state in {"accepted", "rejected", "blocked"}:
            return last_state
        if last_state in {"running", "paused"}:
            try:
                _advance_from_describe(project, node, root)
            except JournalError as exc:
                print(exc, file=sys.stderr)
                return current_state(project, node, root)
            last_state = current_state(project, node, root)
            if last_state == "awaiting-decision" and decider == "none":
                return last_state
        time.sleep(0.5)
    raise JournalError("follow timed out")


def _spec_for(project: str, node: str, run_id: str, root: Path, cfg: Path) -> Path:
    _prepare_prompt(project, node, run_id, root, cfg)
    run = node_dir(project, node, root) / "runs" / run_id
    art = run / "artifacts"
    prompt = (run / "prompt.txt").read_text(encoding="utf-8").rstrip()
    art_s = str(art)
    agent_dir = art / ".pi" / "agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "scribe.md").write_text(
        "---\n"
        "name: scribe\n"
        "description: Writes one file or asks one question\n"
        "tools: write, ask\n"
        "systemPromptMode: replace\n"
        "inheritProjectContext: false\n"
        "defaultContext: fresh\n"
        "---\n"
        "Do only the task. Do not explore. If the task says to write a file, write it and stop. "
        "If the task says to call ask, call ask and stop.\n",
        encoding="utf-8",
    )
    model = worker_model()
    worker_a = {
        "key": "a",
        "agent": "scribe",
        "model": model,
        "tools": ["write"],
        "writer": False,
        "cwd": art_s,
        "task": (
            f"{prompt}\n\nYou are worker A. Do only the Worker A part. "
            f"Write {art / 'hello-a.txt'} and no other file. Then stop."
        ),
    }
    worker_b = {
        "key": "b",
        "agent": "scribe",
        "model": model,
        "tools": ["write"],
        "writer": False,
        "cwd": art_s,
        "task": (
            f"{prompt}\n\nYou are worker B. Do only the Worker B part. "
            f"Write {art / 'hello-b.txt'} and no other file. Then stop."
        ),
    }
    gate = {
        "agent": "scribe",
        "model": model,
        "tools": ["ask"],
        "writer": False,
        "cwd": art_s,
        "task": "Call the ask tool now with exactly this question and then stop: Workers finished. Resume to review?",
    }
    source = (
        f"await runs.all([{json.dumps(worker_a)}, {json.dumps(worker_b)}]);\n"
        f"await runs.run(\"gate\", {json.dumps(gate)});\n"
    )
    spec = {"name": "line-pair", "cwd": art_s, "source": source}
    path = run / "spec.json"
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    return path


def _launch_and_dispatch(project: str, node: str, run_id: str, root: Path) -> None:
    cfg = config_root()
    spec = _spec_for(project, node, run_id, root, cfg)
    pane = launch_pi(project, node, run_id, root=root)
    session_id = str(pane["pi_session_id"])
    art = node_dir(project, node, root) / "runs" / run_id / "artifacts"
    request_id = f"{run_id}-{uuid.uuid4().hex[:6]}"
    proc = dsa_cmd(
        "run", "--request", request_id, "--spec", str(spec), "--cwd", str(art),
        "--session", session_id, "--json",
        wait_ms=20000,
    )
    if proc.returncode not in {0, 75}:
        raise JournalError(proc.stderr.strip() or proc.stdout.strip() or "durable run was refused")
    payload = _dsa_json(proc)
    wid = str(payload.get("wid") or "")
    if not wid:
        described = dsa_cmd("describe", "--key", request_id, "--json")
        if described.returncode == 0:
            wid = str(_dsa_json(described).get("wid") or "")
    if not wid:
        raise JournalError("pi-durable-subagents did not return a wid")
    journal(
        project, node, "dispatch",
        request_id=request_id,
        wid=wid,
        artifacts=[str(definition_dir(project, node, cfg) / "BRIEF.md")],
        root=root,
    )


def _questions(described: dict) -> list[dict]:
    raw = described.get("questions") or described.get("asking") or []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _advance_from_describe(project: str, node: str, root: Path) -> None:
    status = read_status(project, node, root)
    request_id = status.get("request_id") or ""
    if not request_id or current_state(project, node, root) not in {"running", "paused"}:
        return
    proc = dsa_cmd("describe", "--key", request_id, "--json")
    if proc.returncode != 0:
        return
    described = _dsa_json(proc)
    state = str(described.get("state") or "")
    if state == "asking":
        if any(pkt.get("kind") == "ambiguity" and pkt.get("open") for pkt in open_packets(project, node, root)):
            return
        questions = _questions(described)
        if not questions:
            return
        question = questions[0]
        qid = str(question.get("qid") or "")
        rev = question.get("rev", 0)
        text = str(question.get("question") or question.get("text") or "Workers finished. Resume to review?")
        _ambiguity_from_question(project, node, root, qid, rev, text, str(question.get("to") or ""))
        return
    if state == "sealed":
        calls = described.get("calls") or []
        failed = [c for c in calls if isinstance(c, dict) and c.get("ok") is False]
        if failed:
            note = "; ".join(f"{c.get('key')}: {c.get('error') or c.get('status')}" for c in failed)
            journal(project, node, "blocked", note=note or "workflow sealed failed", root=root)
            return
        _concat_and_review(project, node, root)


def _ambiguity_from_question(project: str, node: str, root: Path, qid: str, rev: object, text: str, target: str) -> None:
    ensure_pause(project, node, "subagent question", root=root)
    status = read_status(project, node, root)
    packet_id = _next_packet_id(node_dir(project, node, root))
    suggested = json.dumps({"reply": "resume", "packet_id": packet_id, "option_id": "resume"})
    packet = {
        "packet_id": packet_id,
        "project": project,
        "node": node,
        "run_id": status.get("run_id") or "",
        "kind": "ambiguity",
        "done": ["Workers are waiting on a question"],
        "question": text,
        "options": [{"id": "resume", "label": "Resume", "consequence": "Answer the subagent and continue"}],
        "evidence": text,
        "artifacts": [],
        "resume_handle": {
            "wid": status.get("wid") or "",
            "qid": qid,
            "rev": rev,
            "to": target,
        },
        "open": True,
    }
    rendered = _render_packet_md(packet, suggested)
    folder = node_dir(project, node, root) / "packets"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{packet_id}.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    (folder / f"{packet_id}.md").write_text(rendered, encoding="utf-8")
    journal(project, node, "packet", note=f"{packet_id} ambiguity", artifacts=[str(folder / f"{packet_id}.md")], root=root)


def _concat_and_review(project: str, node: str, root: Path) -> None:
    status = read_status(project, node, root)
    art = node_dir(project, node, root) / "runs" / str(status.get("run_id") or "") / "artifacts"
    if not (art / "hello-a.txt").is_file() or not (art / "hello-b.txt").is_file():
        return
    if not (art / "hello.txt").is_file():
        lines: list[str] = []
        for name in ("hello-a.txt", "hello-b.txt"):
            lines.extend(ln for ln in (art / name).read_text(encoding="utf-8").splitlines() if ln.strip())
        (art / "hello.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if current_state(project, node, root) == "running":
        review_node(project, node, root=root)


def run_node(project: str, node: str, *, decider: str = "none", timeout: float = 5400.0, root: Path | None = None) -> int:
    root = root or runtime_root()
    if not _deps_satisfied(project, node):
        if current_state(project, node, root) != "blocked":
            journal(project, node, "blocked", note="missing dependency gate", root=root)
        print(f"{node} is blocked on a dependency gate", file=sys.stderr)
        return 2
    state = current_state(project, node, root)
    if state == "accepted":
        show_node(project, node, root=root)
        return 0
    if state in {"pending", "blocked"} or not (node_dir(project, node, root) / "journal.jsonl").is_file():
        lines = _read_lines(node_dir(project, node, root))
        if lines and lines[-1].get("type") == "decision" and lines[-1].get("state") == "pending":
            run_id = str(lines[-1]["run_id"])
        else:
            run_id = _alloc_run_id(node, lines)
            run_dir = node_dir(project, node, root) / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
        try:
            _launch_and_dispatch(project, node, run_id, root)
        except JournalError as exc:
            if current_state(project, node, root) != "blocked":
                try:
                    journal(project, node, "blocked", note=str(exc), root=root)
                except JournalError:
                    pass
            print(exc, file=sys.stderr)
            return 2
    elif state == "awaiting-decision" and decider == "none":
        inbox(project, node, root=root)
        return 0
    final = follow(project, node, decider=decider, timeout=timeout, root=root)
    return 0 if final == "accepted" else 2 if final == "blocked" else 0


def _deps_satisfied(project: str, node: str) -> bool:
    path = config_root() / "graphs" / project / "nodes" / f"{node}.yaml"
    if not path.is_file():
        return True
    try:
        import yaml
    except ImportError:
        return True
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    deps = doc.get("depends_on") or []
    if not deps:
        return True
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from runtime.gate_tokens import gate_satisfied
    return gate_satisfied(_gate_repo(), list(deps))


def show_node(project: str, node: str, root: Path | None = None, cfg: Path | None = None) -> None:
    root = root or runtime_root()
    cfg = cfg or config_root()
    brief = definition_dir(project, node, cfg) / "BRIEF.md"
    directory = node_dir(project, node, root)
    print(f"# {project}/{node}")
    print("## BRIEF")
    print(brief.read_text(encoding="utf-8") if brief.is_file() else "(missing BRIEF.md)")
    print("## status")
    status_path = directory / "status"
    print(status_path.read_text(encoding="utf-8") if status_path.is_file() else "(no status)\n")
    print("## pane")
    print(live_pane_id(project, node, root))
    print("## journal")
    journal_path = directory / "journal.jsonl"
    if not journal_path.is_file():
        print("(no journal)")
    else:
        for raw in journal_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            print(raw)
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if line.get("type") in {"packet", "decision"}:
                note = str(line.get("note") or "")
                packet_id = note.split(" ", 1)[0]
                md = directory / "packets" / f"{packet_id}.md"
                js = directory / "packets" / f"{packet_id}.json"
                if line["type"] == "packet" and md.is_file():
                    print(f"--- packet {packet_id} ---")
                    print(md.read_text(encoding="utf-8"))
                if line["type"] == "decision" and js.is_file():
                    print(f"--- decision {packet_id} ---")
                    print(js.read_text(encoding="utf-8"))
    print("## artifacts")
    runs = directory / "runs"
    if runs.is_dir():
        for path in sorted(runs.rglob("*")):
            if path.is_file():
                print(path)
        for done in sorted(runs.glob("*/artifacts/workers.done")):
            print(f"workers.done {done.parent.parent.name}: {done.read_text(encoding='utf-8').strip()}")
        for hello in sorted(runs.glob("*/artifacts/hello.txt")):
            count = len(_artifact_lines(hello))
            print(f"hello.txt {hello.parent.parent.name}: {count} non-empty lines")
    token = _gate_repo() / ".gddp" / "gates" / f"{node}.token"
    print("## gate")
    print(token.read_text(encoding="utf-8") if token.is_file() else "(no gate)")
    request_id = ""
    status_path = directory / "status"
    if status_path.is_file():
        request_id = read_status(project, node, root).get("request_id") or ""
    if request_id:
        described = dsa_cmd("describe", "--key", request_id, "--json")
        print("## describe")
        print(described.stdout.strip() or described.stderr.strip() or "(no describe)")


def inbox(project: str | None = None, node: str | None = None, *, as_json: bool = False, root: Path | None = None) -> int:
    rows = open_packets(project, node, root)
    if as_json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("inbox: no open packets")
        return 0
    for row in rows:
        print(f"{row['packet_id']}  {row['project']}/{row['node']}  {row['kind']}  {row['question']}")
    return 0


def watch_node(project: str, node: str, root: Path | None = None) -> int:
    path = node_dir(project, node, root) / "journal.jsonl"
    if not path.is_file():
        print(f"no journal at {path}", file=sys.stderr)
        return 2
    cursor = "0:0"
    with path.open("r", encoding="utf-8") as handle:
        print(handle.read(), end="")
        while True:
            line = handle.readline()
            if line:
                print(line, end="")
                sys.stdout.flush()
            events = dsa_cmd("events", "--all", "--since", cursor, "--limit", "50", "--wait-ms", "1000")
            for raw in (events.stdout or "").splitlines():
                raw = raw.strip()
                if not raw.startswith("{"):
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if rec.get("cursor"):
                    cursor = str(rec["cursor"])
                if rec.get("type"):
                    print(f"event {rec.get('type')} {rec.get('wid', '')} {rec.get('question', rec.get('status', ''))}")
            if not line:
                time.sleep(0.2)


def pause_node(project: str, node: str, root: Path | None = None) -> int:
    root = root or runtime_root()
    state = current_state(project, node, root)
    if state == "running":
        ensure_pause(project, node, "operator pause", root=root)
        pane = _load_pane(project, node, root)
        if pane.get("pane_id"):
            subprocess.run(
                ["herdr", "agent", "prompt", pane["pane_id"],
                 "Pause the active workflow with the trajectory pause action (lifecycle.pause). Do not start new work."],
                check=False,
            )
    show_node(project, node, root=root)
    return 0


def steer_node(project: str, node: str, text: str, root: Path | None = None) -> int:
    root = root or runtime_root()
    journal(project, node, "steer", note=text, root=root)
    status = read_status(project, node, root)
    wid = status.get("wid") or ""
    if wid:
        dsa_cmd(
            "send", "--request", f"steer-{uuid.uuid4().hex[:8]}", "--to", wid,
            "--kind", "steer", "--message", text, "--json",
            wait_ms=15000,
        )
    return 0


def _cmd_journal(args: argparse.Namespace) -> int:
    reply = json.loads(args.reply_json) if args.reply_json else None
    try:
        line = journal(
            args.project, args.node, args.type,
            note=args.note, artifacts=args.artifact, who=args.who,
            request_id=args.request_id, wid=args.wid,
            reply=reply, verdict=args.verdict, repo=args.repo, verdict_path=args.verdict_path,
        )
    except JournalError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(json.dumps(line))
    return 0


def _cmd_decide(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.reply_json == "-" else Path(args.reply_json).read_text(encoding="utf-8")
    try:
        reply = json.loads(raw)
        decide(args.packet_id, reply, who=args.who)
    except (JournalError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gdad_run")
    sub = parser.add_subparsers(dest="cmd", required=True)

    journal_p = sub.add_parser("journal")
    journal_p.add_argument("project")
    journal_p.add_argument("node")
    journal_p.add_argument("type")
    journal_p.add_argument("--note")
    journal_p.add_argument("--artifact", action="append")
    journal_p.add_argument("--who")
    journal_p.add_argument("--request-id")
    journal_p.add_argument("--wid")
    journal_p.add_argument("--reply-json")
    journal_p.add_argument("--verdict", choices=["accept", "reject"])
    journal_p.add_argument("--repo")
    journal_p.add_argument("--verdict-path")
    journal_p.set_defaults(func=_cmd_journal)

    pause_p = sub.add_parser("pause-packet")
    pause_p.add_argument("project")
    pause_p.add_argument("node")
    pause_p.set_defaults(func=lambda args: _call(lambda: ambiguity_packet(args.project, args.node) or None))

    resumed_p = sub.add_parser("mark-resumed")
    resumed_p.add_argument("project")
    resumed_p.add_argument("node")
    resumed_p.set_defaults(func=lambda args: _call(lambda: mark_resumed(args.project, args.node)))

    wait_p = sub.add_parser("wait-running")
    wait_p.add_argument("project")
    wait_p.add_argument("node")
    wait_p.set_defaults(func=lambda args: _call(lambda: wait_running(args.project, args.node)))

    review_p = sub.add_parser("review")
    review_p.add_argument("project")
    review_p.add_argument("node")
    review_p.set_defaults(func=lambda args: _call(lambda: review_node(args.project, args.node)))

    run_p = sub.add_parser("run")
    run_p.add_argument("project")
    run_p.add_argument("node")
    run_p.add_argument("--decider", choices=["fable", "none"], default="none")
    run_p.set_defaults(func=lambda args: run_node(args.project, args.node, decider=args.decider))

    show_p = sub.add_parser("show")
    show_p.add_argument("project")
    show_p.add_argument("node")
    show_p.set_defaults(func=lambda args: show_node(args.project, args.node) or 0)

    inbox_p = sub.add_parser("inbox")
    inbox_p.add_argument("--project")
    inbox_p.add_argument("--node")
    inbox_p.add_argument("--json", action="store_true")
    inbox_p.set_defaults(func=lambda args: inbox(args.project, args.node, as_json=args.json))

    decide_p = sub.add_parser("decide")
    decide_p.add_argument("packet_id")
    decide_p.add_argument("reply_json")
    decide_p.add_argument("--who", default="sab")
    decide_p.set_defaults(func=_cmd_decide)

    watch_p = sub.add_parser("watch")
    watch_p.add_argument("project")
    watch_p.add_argument("node")
    watch_p.set_defaults(func=lambda args: watch_node(args.project, args.node))

    pause_cmd = sub.add_parser("pause")
    pause_cmd.add_argument("project")
    pause_cmd.add_argument("node")
    pause_cmd.set_defaults(func=lambda args: pause_node(args.project, args.node))

    steer_p = sub.add_parser("steer")
    steer_p.add_argument("project")
    steer_p.add_argument("node")
    steer_p.add_argument("text")
    steer_p.set_defaults(func=lambda args: steer_node(args.project, args.node, args.text))
    return parser


def _call(fn) -> int:
    try:
        fn()
    except JournalError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())
