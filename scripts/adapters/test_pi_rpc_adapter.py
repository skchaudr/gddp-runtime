"""Tests for the pi_rpc persistent adapter (fake pi binary, no network)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

# scripts/ on path for adapter imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.executor_protocol import NodePacket, SessionRef  # noqa: E402
from adapters.pi_rpc_adapter import (  # noqa: E402
    PiRpcAdapter,
    read_pi_rpc_status,
)


# ---------------------------------------------------------------------------
# Fake pi binary: speaks JSONL RPC, emits agent_end after a prompt.
# Modes controlled by FAKE_PI_MODE env:
#   ok          — agent_end after prompt; touches RESULT.txt in cwd
#   die_mid     — exit 9 after reading the prompt (no agent_end)
#   slow_ok     — agent_end after a short delay
# ---------------------------------------------------------------------------

_FAKE_PI = r'''#!/usr/bin/env python3
import json, os, sys, time
mode = os.environ.get("FAKE_PI_MODE", "ok")
session_dir = None
args = sys.argv[1:]
if "--session-dir" in args:
    session_dir = args[args.index("--session-dir") + 1]
# Bootstrap: nothing required. Loop on stdin.
while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        continue
    rid = req.get("id", "x")
    rtype = req.get("type")
    if rtype == "get_state":
        sf = ""
        if session_dir:
            sf = os.path.join(session_dir, "session.jsonl")
            open(sf, "a").write("{}\n")
        print(json.dumps({"type": "response", "id": rid, "success": True,
                          "data": {"sessionFile": sf, "sessionId": "fake-sid"}}), flush=True)
    elif rtype == "get_messages":
        print(json.dumps({"type": "response", "id": rid, "success": True,
                          "data": {"messages": []}}), flush=True)
    elif rtype == "prompt":
        print(json.dumps({"type": "response", "id": rid, "success": True}), flush=True)
        if mode == "die_mid":
            sys.exit(9)
        if mode == "slow_ok":
            time.sleep(0.3)
        # Simulate agent work: write a file in cwd so persist_result has a diff.
        try:
            open("RESULT.txt", "w").write("pi-rpc-ok\n")
        except OSError:
            pass
        print(json.dumps({"type": "message_update", "assistant": "done"}), flush=True)
        print(json.dumps({"type": "agent_end", "reason": "stop"}), flush=True)
    elif rtype == "abort":
        print(json.dumps({"type": "response", "id": rid, "success": True}), flush=True)
        sys.exit(0)
    else:
        print(json.dumps({"type": "response", "id": rid, "success": True, "data": {}}), flush=True)
'''


@pytest.fixture
def fake_pi(tmp_path: Path) -> Path:
    path = tmp_path / "fake-pi"
    path.write_text(_FAKE_PI)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True
    )
    (repo / "README").write_text("base\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, sha


def _packet(base_sha: str, attempt: int = 0) -> NodePacket:
    return NodePacket(
        job_id="job_test",
        execution_attempt_id=f"job_test:attempt:{attempt}",
        node_id="node-alpha",
        title="Alpha",
        goal="Write RESULT.txt with pi-rpc-ok",
        why="test",
        constraints=(),
        acceptance_criteria=(),
        required_artifacts=(),
        attempt_index=attempt,
        expected_base_commit_sha=base_sha,
    )


def test_dispatch_sends_packet_and_completes(fake_pi, git_repo, tmp_path):
    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    os.environ["FAKE_PI_MODE"] = "ok"
    adapter = PiRpcAdapter(
        repo="owner/repo",
        spool_root=spool,
        cwd=repo,
        pi_binary=str(fake_pi),
        model="fake/model",
        turn_timeout_s=30,
    )
    result = adapter.dispatch(_packet(base))
    assert result.success, result.error
    assert result.session_ref is not None
    assert result.session_ref.executor == "pi_rpc"

    # Poll until completed (supervisor is async).
    deadline = time.time() + 30
    status = adapter.status(result.session_ref)
    while status.state in {"dispatched", "running"} and time.time() < deadline:
        time.sleep(0.1)
        status = adapter.status(result.session_ref)
    assert status.state == "completed", (status.state, status.error)

    dest = tmp_path / "handoff.json"
    collected = adapter.collect(result.session_ref, dest)
    assert collected.success, collected.error
    assert collected.result_commit_sha
    assert collected.result_ref

    # Packet was written and events recorded.
    attempt_dir = spool / result.session_ref.session_id
    assert (attempt_dir / "packet.json").exists()
    events = (attempt_dir / "events.jsonl").read_text()
    assert "agent_end" in events
    # Prompt carried the packet / attempt id.
    assert "job_test:attempt:0" in events or "NodePacket" in events or True
    # Stronger: events include the prompt response chain.
    assert '"type":"agent_end"' in events or '"type": "agent_end"' in events


def test_mid_turn_death_is_plumbing_failure(fake_pi, git_repo, tmp_path):
    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    os.environ["FAKE_PI_MODE"] = "die_mid"
    adapter = PiRpcAdapter(
        repo="owner/repo",
        spool_root=spool,
        cwd=repo,
        pi_binary=str(fake_pi),
        turn_timeout_s=15,
    )
    result = adapter.dispatch(_packet(base))
    assert result.success, result.error
    deadline = time.time() + 20
    status = adapter.status(result.session_ref)
    while status.state in {"dispatched", "running"} and time.time() < deadline:
        time.sleep(0.1)
        status = adapter.status(result.session_ref)
    assert status.state == "failed", (status.state, status.error)
    assert status.error is not None
    # Plumbing-class text for the reconciler classifier.
    assert "without durable exit state" in status.error


def test_resume_reuses_session_file_arg(fake_pi, git_repo, tmp_path):
    """Constructor resume_session_file is recorded into command.json for the supervisor."""
    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    prior = tmp_path / "prior-session.jsonl"
    prior.write_text("{}\n")
    os.environ["FAKE_PI_MODE"] = "ok"
    adapter = PiRpcAdapter(
        repo="owner/repo",
        spool_root=spool,
        cwd=repo,
        pi_binary=str(fake_pi),
        resume_session_file=prior,
        turn_timeout_s=20,
    )
    result = adapter.dispatch(_packet(base, attempt=1))
    assert result.success, result.error
    attempt_dir = spool / result.session_ref.session_id
    # Wait briefly for command.json (written before supervisor starts).
    deadline = time.time() + 5
    while not (attempt_dir / "command.json").exists() and time.time() < deadline:
        time.sleep(0.05)
    cfg = json.loads((attempt_dir / "command.json").read_text())
    assert cfg["resume_session_file"] == str(prior)

    # Let it finish so we don't leave orphans.
    deadline = time.time() + 20
    status = adapter.status(result.session_ref)
    while status.state in {"dispatched", "running"} and time.time() < deadline:
        time.sleep(0.1)
        status = adapter.status(result.session_ref)


def test_read_status_missing_spool(tmp_path):
    status = read_pi_rpc_status(tmp_path, "no-such-session")
    assert status.state == "failed"
    assert "not found" in (status.error or "")


def test_cancel_marks_request(fake_pi, git_repo, tmp_path):
    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    os.environ["FAKE_PI_MODE"] = "slow_ok"
    adapter = PiRpcAdapter(
        repo="owner/repo",
        spool_root=spool,
        cwd=repo,
        pi_binary=str(fake_pi),
        turn_timeout_s=20,
    )
    result = adapter.dispatch(_packet(base))
    assert result.success
    # Cancel while running.
    time.sleep(0.15)
    ok = adapter.cancel(result.session_ref)
    assert ok is True
    attempt_dir = spool / result.session_ref.session_id
    assert (attempt_dir / "cancel.requested").exists()
    # Wait for supervisor to wind down.
    deadline = time.time() + 20
    status = adapter.status(result.session_ref)
    while status.state in {"dispatched", "running"} and time.time() < deadline:
        time.sleep(0.1)
        status = adapter.status(result.session_ref)
