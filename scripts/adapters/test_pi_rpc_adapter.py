"""Tests for the pi_rpc persistent-orchestrator adapter (fake pi, no network)."""

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
    _pid_is_running,
    read_pi_rpc_status,
)


# ---------------------------------------------------------------------------
# Fake pi binary: speaks JSONL RPC, emits agent_end after a prompt.
# Modes controlled by FAKE_PI_MODE env:
#   ok          — agent_end after prompt; writes RESULT.txt into the
#                 worktree_path parsed out of the prompt (falls back to cwd
#                 if the prompt carries none), mirroring what a real
#                 orchestrator subagent is instructed to do (fork A preamble).
#   die_mid     — exit 9 after reading the prompt (no agent_end)
#   slow_ok     — agent_end after a short delay
# FAKE_PI_BOOT_MARKER, if set, gets one line (this process's pid) appended on
# startup — lets tests prove how many times pi was actually spawned across
# multiple packets.
# ---------------------------------------------------------------------------

_FAKE_PI = r'''#!/usr/bin/env python3
import json, os, sys, time
mode = os.environ.get("FAKE_PI_MODE", "ok")
session_dir = None
args = sys.argv[1:]
if "--session-dir" in args:
    session_dir = args[args.index("--session-dir") + 1]
boot_marker = os.environ.get("FAKE_PI_BOOT_MARKER")
if boot_marker:
    with open(boot_marker, "a") as fh:
        fh.write(f"{os.getpid()}\n")
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
        # Simulate a subagent following the orchestrator preamble: write into
        # the worktree_path line carried in the prompt, not into our own cwd
        # (our own cwd is the repo root under fork A and must stay untouched).
        msg = req.get("message") or ""
        target = os.getcwd()
        for ln in msg.splitlines():
            if ln.startswith("worktree_path: "):
                target = ln[len("worktree_path: "):].strip()
                break
        try:
            open(os.path.join(target, "RESULT.txt"), "w").write("pi-rpc-ok\n")
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


def _packet(base_sha: str, attempt: int = 0, project_id: str = "") -> NodePacket:
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
        project_id=project_id,
    )


def _wait_terminal(adapter: PiRpcAdapter, session_ref: SessionRef, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    status = adapter.status(session_ref)
    while status.state in {"dispatched", "running"} and time.time() < deadline:
        time.sleep(0.1)
        status = adapter.status(session_ref)


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

    _wait_terminal(adapter, result.session_ref)
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
    assert '"type":"agent_end"' in events or '"type": "agent_end"' in events

    # The worktree_path line in the prompt was actually honored: RESULT.txt
    # landed as a real, non-empty commit (not the empty-tree fallback).
    show = subprocess.run(
        ["git", "show", f"{collected.result_commit_sha}:RESULT.txt"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert show.returncode == 0, show.stderr
    assert "pi-rpc-ok" in show.stdout


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
    _wait_terminal(adapter, result.session_ref, timeout=20)
    status = adapter.status(result.session_ref)
    assert status.state == "failed", (status.state, status.error)
    assert status.error is not None
    # Plumbing-class text for the reconciler classifier.
    assert "without durable exit state" in status.error


def test_resume_reuses_session_file_arg(fake_pi, git_repo, tmp_path):
    """Constructor resume_session_file is recorded into command.json for the orchestrator."""
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
    cfg = json.loads((attempt_dir / "command.json").read_text())
    assert cfg["resume_session_file"] == str(prior)

    # Let it finish so we don't leave orphans.
    _wait_terminal(adapter, result.session_ref, timeout=20)


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
    # Wait for the orchestrator to wind down.
    _wait_terminal(adapter, result.session_ref, timeout=20)


# ---------------------------------------------------------------------------
# Fork A: persistent per-project orchestrator behavior
# ---------------------------------------------------------------------------


def test_second_dispatch_same_project_reuses_live_session(fake_pi, git_repo, tmp_path):
    """Two packets for the same project_id, dispatched sequentially, are
    served by ONE pi process (no second spawn once the first is idle)."""
    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    os.environ["FAKE_PI_MODE"] = "ok"
    boot_marker = tmp_path / "boots.txt"
    os.environ["FAKE_PI_BOOT_MARKER"] = str(boot_marker)
    try:
        adapter = PiRpcAdapter(
            repo="owner/repo",
            spool_root=spool,
            cwd=repo,
            pi_binary=str(fake_pi),
            model="fake/model",
            turn_timeout_s=30,
        )
        r1 = adapter.dispatch(_packet(base, attempt=0, project_id="proj-x"))
        assert r1.success, r1.error
        _wait_terminal(adapter, r1.session_ref, timeout=30)
        assert adapter.status(r1.session_ref).state == "completed"

        r2 = adapter.dispatch(_packet(base, attempt=1, project_id="proj-x"))
        assert r2.success, r2.error
        _wait_terminal(adapter, r2.session_ref, timeout=30)
        assert adapter.status(r2.session_ref).state == "completed"

        d1 = spool / r1.session_ref.session_id
        d2 = spool / r2.session_ref.session_id
        sup1 = (d1 / "supervisor.pid").read_text().strip()
        sup2 = (d2 / "supervisor.pid").read_text().strip()
        assert sup1 == sup2, "expected both attempts to share one orchestrator pid"

        boots = [ln for ln in boot_marker.read_text().splitlines() if ln.strip()]
        assert len(boots) == 1, f"expected exactly one pi process boot, got {boots}"
    finally:
        os.environ.pop("FAKE_PI_BOOT_MARKER", None)


def test_second_dispatch_while_first_running_queues_not_spawns(fake_pi, git_repo, tmp_path):
    """A packet dispatched while the project's orchestrator is mid-turn is
    queued into that same orchestrator's inbox, never spawns a second pi."""
    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    os.environ["FAKE_PI_MODE"] = "slow_ok"
    boot_marker = tmp_path / "boots.txt"
    os.environ["FAKE_PI_BOOT_MARKER"] = str(boot_marker)
    try:
        adapter = PiRpcAdapter(
            repo="owner/repo",
            spool_root=spool,
            cwd=repo,
            pi_binary=str(fake_pi),
            model="fake/model",
            turn_timeout_s=30,
        )
        r1 = adapter.dispatch(_packet(base, attempt=0, project_id="proj-y"))
        assert r1.success, r1.error
        r2 = adapter.dispatch(_packet(base, attempt=1, project_id="proj-y"))
        assert r2.success, r2.error

        # supervisor.pid is written synchronously inside dispatch() itself
        # (not by the orchestrator asynchronously), so this is deterministic:
        # dispatch() for r2 must have taken the "live, enqueue" branch.
        d1 = spool / r1.session_ref.session_id
        d2 = spool / r2.session_ref.session_id
        sup1 = (d1 / "supervisor.pid").read_text().strip()
        sup2 = (d2 / "supervisor.pid").read_text().strip()
        assert sup1 == sup2, "second dispatch should have queued behind the live orchestrator"

        _wait_terminal(adapter, r1.session_ref, timeout=30)
        _wait_terminal(adapter, r2.session_ref, timeout=30)
        assert adapter.status(r1.session_ref).state == "completed"
        assert adapter.status(r2.session_ref).state == "completed"

        boots = [ln for ln in boot_marker.read_text().splitlines() if ln.strip()]
        assert len(boots) == 1, f"expected exactly one pi process boot, got {boots}"
    finally:
        os.environ.pop("FAKE_PI_BOOT_MARKER", None)


def test_different_projects_get_separate_orchestrators(fake_pi, git_repo, tmp_path):
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
    r1 = adapter.dispatch(_packet(base, attempt=0, project_id="proj-a"))
    r2 = adapter.dispatch(_packet(base, attempt=1, project_id="proj-b"))
    assert r1.success and r2.success

    d1 = spool / r1.session_ref.session_id
    d2 = spool / r2.session_ref.session_id
    sup1 = (d1 / "supervisor.pid").read_text().strip()
    sup2 = (d2 / "supervisor.pid").read_text().strip()
    assert sup1 != sup2, "different project_id must not share one orchestrator"

    _wait_terminal(adapter, r1.session_ref, timeout=30)
    _wait_terminal(adapter, r2.session_ref, timeout=30)
    assert adapter.status(r1.session_ref).state == "completed"
    assert adapter.status(r2.session_ref).state == "completed"


def test_cancel_of_queued_packet_does_not_kill_live_orchestrator(fake_pi, git_repo, tmp_path):
    """Cancelling a packet still sitting in the inbox must not touch the
    shared per-project pi process running someone else's turn."""
    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    os.environ["FAKE_PI_MODE"] = "slow_ok"
    adapter = PiRpcAdapter(
        repo="owner/repo",
        spool_root=spool,
        cwd=repo,
        pi_binary=str(fake_pi),
        model="fake/model",
        turn_timeout_s=30,
    )
    r1 = adapter.dispatch(_packet(base, attempt=0, project_id="proj-z"))
    r2 = adapter.dispatch(_packet(base, attempt=1, project_id="proj-z"))
    assert r1.success and r2.success

    ok = adapter.cancel(r2.session_ref)  # r2 is queued, its turn never started
    assert ok is True
    d2 = spool / r2.session_ref.session_id
    assert (d2 / "cancel.requested").exists()

    _wait_terminal(adapter, r1.session_ref, timeout=30)
    status1 = adapter.status(r1.session_ref)
    assert status1.state == "completed", status1.error  # orchestrator survived, r1 unaffected

    _wait_terminal(adapter, r2.session_ref, timeout=30)
    status2 = adapter.status(r2.session_ref)
    assert status2.state == "failed"
    assert "cancel" in (status2.error or "").lower()


def test_idle_timeout_exits_session_then_new_dispatch_spawns_fresh(fake_pi, git_repo, tmp_path):
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
        idle_timeout_s=0.5,
    )
    r1 = adapter.dispatch(_packet(base, attempt=0, project_id="proj-idle"))
    assert r1.success
    _wait_terminal(adapter, r1.session_ref, timeout=30)
    assert adapter.status(r1.session_ref).state == "completed"

    sup1 = int((spool / r1.session_ref.session_id / "supervisor.pid").read_text().strip())
    deadline = time.time() + 10
    while _pid_is_running(sup1) and time.time() < deadline:
        time.sleep(0.1)
    assert not _pid_is_running(sup1), "orchestrator did not exit after its idle timeout"

    r2 = adapter.dispatch(_packet(base, attempt=1, project_id="proj-idle"))
    assert r2.success
    sup2 = int((spool / r2.session_ref.session_id / "supervisor.pid").read_text().strip())
    assert sup2 != sup1, "expected a fresh orchestrator after the prior one idled out"
    _wait_terminal(adapter, r2.session_ref, timeout=30)
    assert adapter.status(r2.session_ref).state == "completed"


# ---------------------------------------------------------------------------
# _observability_env
# ---------------------------------------------------------------------------


def test_observability_env_tags_attempt(tmp_path):
    from adapters.pi_rpc_adapter import _observability_env

    env_file = tmp_path / "env"
    env_file.write_text(
        "# comment\n"
        "export OBS_SERVER_URL='http://100.93.242.91:43190'\n"
        "export OBS_TOKEN=\"sekret\"\n"
        "export OBS_POOL='fleet'\n"
    )
    obs = _observability_env(
        {
            "node_id": "node-01b-contract-review",
            "job_id": "job_123",
            "attempt_index": 0,
            "project_id": "myapi-part2",
        },
        env_file=env_file,
    )
    assert obs["OBS_SERVER_URL"] == "http://100.93.242.91:43190"
    assert obs["OBS_TOKEN"] == "sekret"  # env only, never argv
    assert obs["OBS_POOL"] == "gddp"  # overridden from fleet
    assert obs["OBS_NAME"] == "gddp-node-01b-contract-review"
    tags = obs["OBS_TAG"].split(",")
    assert "gddp" in tags
    assert "project:myapi-part2" in tags
    assert "node:node-01b-contract-review" in tags
    assert "job:job_123" in tags
    assert "attempt:0" in tags
    assert any(t.startswith("host:") for t in tags)


def test_observability_env_off_when_unconfigured(tmp_path):
    from adapters.pi_rpc_adapter import _observability_env

    assert _observability_env({"node_id": "n"}, env_file=tmp_path / "missing") == {}
    env_file = tmp_path / "env"
    env_file.write_text("export OBS_POOL='fleet'\n")  # no server URL
    assert _observability_env({"node_id": "n"}, env_file=env_file) == {}


def test_observability_env_project_tag_from_production_packet(tmp_path):
    """Build the packet through the real dispatcher builder (job-row shape,
    no synthetic project_id shortcut) and assert the tag survives."""
    from adapters.pi_rpc_adapter import _observability_env
    from runtime.heartbeat.dispatcher import _build_node_packet

    job = {
        "job_id": "job_prod",
        "node_id": "node-02-chat-path-scorer",
        "project_id": "myapi-part2",
        "title": "t",
        "goal": "g",
        "why": "w",
        "constraints": "[]",
        "acceptance_criteria": "[]",
        "required_artifacts": "[]",
        "attempt": 0,
        "project_id": "myapi-part2",
    }
    packet = _build_node_packet(job)
    assert packet.project_id == "myapi-part2"
    # packet.json round trip: the orchestrator sees the serialized dict
    packet_dict = json.loads(packet.to_json())
    env_file = tmp_path / "env"
    env_file.write_text("export OBS_SERVER_URL='http://hub:43190'\n")
    obs = _observability_env(packet_dict, env_file=env_file)
    assert "project:myapi-part2" in obs["OBS_TAG"].split(",")
