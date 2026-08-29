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

from adapters.executor_protocol import (  # noqa: E402
    AttemptContext,
    FRESH,
    Continuity,
    NodePacket,
    SessionRef,
)
from adapters.pi_rpc_adapter import (  # noqa: E402
    PiRpcAdapter,
    _PACKET_PREAMBLE,
    _assemble_turn_prompt,
    build_executor_turn_prompt,
    build_project_zone,
    compute_turn_context_coverage,
    extract_read_paths,
    _pid_is_running,
    read_pi_rpc_status,
)
from adapters.session_prompt import split_packet_zones  # noqa: E402


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
# FAKE_PI_PROMPT_MARKER, if set, gets one line appended each time a "prompt"
# request is received — lets tests prove a batch of N packets was handled by
# exactly ONE prompt/turn rather than N.
# FAKE_PI_READ_PATHS, if set, is a comma-separated list of paths emitted as
# real read tool_execution_start/end pairs before agent_end — the verified
# event shape the coverage parser reads.
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
prompt_marker = os.environ.get("FAKE_PI_PROMPT_MARKER")
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
        if prompt_marker:
            with open(prompt_marker, "a") as fh:
                fh.write(f"{os.getpid()}\n")
        if mode == "die_mid":
            sys.exit(9)
        if mode == "slow_ok":
            time.sleep(0.3)
        # Simulate a subagent (or, under a batch turn, one subagent per
        # packet) following the orchestrator preamble: write into every
        # worktree_path line carried in the prompt, not into our own cwd
        # (our own cwd is the repo root under fork A and must stay
        # untouched). A batch prompt carries one worktree_path line per
        # packet; a single-packet prompt carries exactly one.
        msg = req.get("message") or ""
        targets = [
            ln[len("worktree_path: "):].strip()
            for ln in msg.splitlines()
            if ln.startswith("worktree_path: ")
        ]
        if not targets:
            targets = [os.getcwd()]
        for target in targets:
            try:
                open(os.path.join(target, "RESULT.txt"), "w").write("pi-rpc-ok\n")
            except OSError:
                pass
        for i, p in enumerate(os.environ.get("FAKE_PI_READ_PATHS", "").split(",")):
            p = p.strip()
            if not p:
                continue
            cid = f"call_fake_{i}"
            print(json.dumps({"type": "tool_execution_start", "toolCallId": cid,
                              "toolName": "read", "args": {"path": p}}), flush=True)
            print(json.dumps({"type": "tool_execution_end", "toolCallId": cid,
                              "toolName": "read",
                              "result": {"content": [{"type": "text", "text": "x"}]},
                              "isError": False}), flush=True)
        print(json.dumps({"type": "message_update", "assistant": "done"}), flush=True)
        print(json.dumps({"type": "agent_end", "reason": "stop"}), flush=True)
    elif rtype == "abort":
        print(json.dumps({"type": "response", "id": rid, "success": True}), flush=True)
        sys.exit(0)
    else:
        print(json.dumps({"type": "response", "id": rid, "success": True, "data": {}}), flush=True)
'''


@pytest.fixture(autouse=True)
def _isolate_fake_pi_env(monkeypatch):
    """Keep FAKE_PI_* off the process after each test. Tests still set them
    with os.environ; teardown restores the pre-test values."""
    monkeypatch.delenv("FAKE_PI_MODE", raising=False)
    monkeypatch.delenv("FAKE_PI_BOOT_MARKER", raising=False)
    monkeypatch.delenv("FAKE_PI_PROMPT_MARKER", raising=False)
    monkeypatch.delenv("FAKE_PI_READ_PATHS", raising=False)


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


def _packet(
    base_sha: str,
    attempt: int = 0,
    project_id: str = "",
    pointers: dict | None = None,
) -> NodePacket:
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
        context_pointers=pointers,
    )


def _dispatch(adapter: PiRpcAdapter, packet: NodePacket, *, continuity=FRESH):
    attempt_id = f"test-{packet.execution_attempt_id.replace(':', '-')}-{time.time_ns()}"
    attempt_dir = adapter.attempt_root() / attempt_id
    attempt_dir.mkdir(parents=True)
    (attempt_dir / "packet.json").write_text(packet.to_json())
    return adapter.dispatch(
        packet,
        attempt=AttemptContext(attempt_id=attempt_id, attempt_dir=attempt_dir),
        continuity=continuity,
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
    result = _dispatch(adapter, _packet(base))
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
        model="fake/model",
        turn_timeout_s=15,
    )
    result = _dispatch(adapter, _packet(base))
    assert result.success, result.error
    _wait_terminal(adapter, result.session_ref, timeout=20)
    status = adapter.status(result.session_ref)
    assert status.state == "failed", (status.state, status.error)
    assert status.error is not None
    # Plumbing-class text for the reconciler classifier.
    assert "without durable exit state" in status.error


def test_resume_continuity_sets_session_file_arg(fake_pi, git_repo, tmp_path):
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
        model="fake/model",
        turn_timeout_s=20,
    )
    result = _dispatch(
        adapter,
        _packet(base, attempt=1),
        continuity=Continuity(mode="resume", token=str(prior)),
    )
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
        model="fake/model",
        turn_timeout_s=20,
    )
    result = _dispatch(adapter, _packet(base))
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
        r1 = _dispatch(adapter, _packet(base, attempt=0, project_id="proj-x"))
        assert r1.success, r1.error
        _wait_terminal(adapter, r1.session_ref, timeout=30)
        assert adapter.status(r1.session_ref).state == "completed"

        r2 = _dispatch(adapter, _packet(base, attempt=1, project_id="proj-x"))
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
        r1 = _dispatch(adapter, _packet(base, attempt=0, project_id="proj-y"))
        assert r1.success, r1.error
        r2 = _dispatch(adapter, _packet(base, attempt=1, project_id="proj-y"))
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
    r1 = _dispatch(adapter, _packet(base, attempt=0, project_id="proj-a"))
    r2 = _dispatch(adapter, _packet(base, attempt=1, project_id="proj-b"))
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
    r1 = _dispatch(adapter, _packet(base, attempt=0, project_id="proj-z"))
    r2 = _dispatch(adapter, _packet(base, attempt=1, project_id="proj-z"))
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
    r1 = _dispatch(adapter, _packet(base, attempt=0, project_id="proj-idle"))
    assert r1.success
    _wait_terminal(adapter, r1.session_ref, timeout=30)
    assert adapter.status(r1.session_ref).state == "completed"

    sup1 = int((spool / r1.session_ref.session_id / "supervisor.pid").read_text().strip())
    deadline = time.time() + 10
    while _pid_is_running(sup1) and time.time() < deadline:
        time.sleep(0.1)
    assert not _pid_is_running(sup1), "orchestrator did not exit after its idle timeout"

    r2 = _dispatch(adapter, _packet(base, attempt=1, project_id="proj-idle"))
    assert r2.success
    sup2 = int((spool / r2.session_ref.session_id / "supervisor.pid").read_text().strip())
    assert sup2 != sup1, "expected a fresh orchestrator after the prior one idled out"
    _wait_terminal(adapter, r2.session_ref, timeout=30)
    assert adapter.status(r2.session_ref).state == "completed"


# ---------------------------------------------------------------------------
# _observability_env
# ---------------------------------------------------------------------------


def test_observability_env_tags_project_not_attempt(tmp_path):
    """Fork A + batch turns: OBS_NAME/OBS_TAG identify the project-level
    orchestrator session only. node:/job:/attempt: are dropped rather than
    mutated mid-session, because a single long-lived process (and a single
    batch turn) can now cover many nodes/jobs/attempts at once — a fixed
    per-node tag set at spawn time would just be stale for all of them."""
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
    assert obs["OBS_NAME"] == "gddp-myapi-part2"
    tags = obs["OBS_TAG"].split(",")
    assert "gddp" in tags
    assert "project:myapi-part2" in tags
    assert any(t.startswith("host:") for t in tags)
    assert not any(t.startswith("node:") for t in tags)
    assert not any(t.startswith("job:") for t in tags)
    assert not any(t.startswith("attempt:") for t in tags)


def test_observability_env_off_when_unconfigured(tmp_path):
    from adapters.pi_rpc_adapter import _observability_env

    assert _observability_env({"node_id": "n"}, env_file=tmp_path / "missing") == {}
    env_file = tmp_path / "env"
    env_file.write_text("export OBS_POOL='fleet'\n")  # no server URL
    assert _observability_env({"node_id": "n"}, env_file=env_file) == {}


# ---------------------------------------------------------------------------
# Session worktree: N queued packets share ONE worktree for the session.
# These call run_orchestrator() directly against a hand-built inbox so the
# claim set is deterministic (no race against a spawned supervisor's own
# claim timing — see the dispatch()-based tests above for that path).
# ---------------------------------------------------------------------------


def _seed_attempt(
    spool: Path,
    orchestrator_dir: Path,
    repo: Path,
    fake_pi: Path,
    base_sha: str,
    *,
    name: str,
    attempt: int = 0,
    idle_timeout_s: float = 0.5,
    turn_timeout_s: float = 20.0,
    pointers: dict | None = None,
) -> Path:
    """Build one attempt_dir's packet.json + command.json without going
    through dispatch(), so several can be enqueued together before
    run_orchestrator() ever takes its first claim. `attempt` must be unique
    across packets sharing a git_repo fixture so each gets its own
    attempt-ref name (persist_result refuses to overwrite an existing ref
    pointed at unrelated evidence)."""
    attempt_dir = spool / name
    attempt_dir.mkdir(parents=True)
    packet = _packet(
        base_sha, attempt=attempt, project_id="batch-proj", pointers=pointers
    )
    (attempt_dir / "packet.json").write_text(packet.to_json())
    config = {
        "pi_binary": str(fake_pi),
        "model": "fake/model",
        "tools": "read,bash,edit,write,grep,find,ls,subagent",
        "turn_timeout_s": turn_timeout_s,
        "idle_timeout_s": idle_timeout_s,
        "repo_cwd": str(repo),
        "orchestrator_dir": str(orchestrator_dir),
        "resume_session_file": None,
    }
    (attempt_dir / "command.json").write_text(json.dumps(config))
    return attempt_dir


def test_queued_packets_reuse_one_session_worktree(fake_pi, git_repo, tmp_path):
    """N packets queued before the first claim share ONE session worktree,
    each persist their own result, and the worktree is removed when the
    session exits."""
    from adapters.pi_rpc_adapter import _enqueue_attempt, _orchestrator_lock, run_orchestrator

    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    orchestrator_dir = spool / "_orchestrators" / "batch-proj"
    os.environ["FAKE_PI_MODE"] = "ok"
    boot_marker = tmp_path / "boots.txt"
    os.environ["FAKE_PI_BOOT_MARKER"] = str(boot_marker)
    try:
        attempt_dirs = [
            _seed_attempt(spool, orchestrator_dir, repo, fake_pi, base, name=f"a{i}", attempt=i)
            for i in range(3)
        ]
        with _orchestrator_lock(orchestrator_dir):
            for attempt_dir in attempt_dirs:
                _enqueue_attempt(orchestrator_dir, attempt_dir)

        rc = run_orchestrator(orchestrator_dir)
        assert rc == 0

        paths = [(d / "worktree_path").read_text().strip() for d in attempt_dirs]
        assert len(set(paths)) == 1, paths
        session_wt = Path(paths[0])
        assert not session_wt.exists(), "session worktree must be removed on exit"

        for attempt_dir in attempt_dirs:
            exit_state = json.loads((attempt_dir / "exit.json").read_text())
            assert exit_state == {
                "returncode": 0,
                "cancelled": False,
                "plumbing": False,
                "error": None,
            }, exit_state
            result = json.loads((attempt_dir / "result.json").read_text())
            assert result.get("result_commit_sha"), result

        boots = [ln for ln in boot_marker.read_text().splitlines() if ln.strip()]
        assert len(boots) == 1, f"expected one pi process, got {boots}"
    finally:
        os.environ.pop("FAKE_PI_BOOT_MARKER", None)


def test_batch_partial_failure_does_not_stop_other_packets_or_session(
    fake_pi, git_repo, tmp_path
):
    """A packet whose base commit cannot be checked out fails in isolation
    at session-worktree setup; later packets still open the session and
    persist, and the shared pi process survives."""
    from adapters.pi_rpc_adapter import _enqueue_attempt, _orchestrator_lock, run_orchestrator

    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    orchestrator_dir = spool / "_orchestrators" / "batch-proj"
    os.environ["FAKE_PI_MODE"] = "ok"
    boot_marker = tmp_path / "boots.txt"
    os.environ["FAKE_PI_BOOT_MARKER"] = str(boot_marker)
    try:
        good_dirs = [
            _seed_attempt(
                spool, orchestrator_dir, repo, fake_pi, base, name=f"good{i}", attempt=i
            )
            for i in range(2)
        ]
        bad_dir = _seed_attempt(
            spool, orchestrator_dir, repo, fake_pi, "deadbeef00deadbeef00deadbeef00deadbeef",
            name="bad0", attempt=2,
        )
        attempt_dirs = [bad_dir, good_dirs[0], good_dirs[1]]
        with _orchestrator_lock(orchestrator_dir):
            for attempt_dir in attempt_dirs:
                _enqueue_attempt(orchestrator_dir, attempt_dir)

        rc = run_orchestrator(orchestrator_dir)
        assert rc == 0, "session must not terminate on a single packet's setup failure"

        bad_exit = json.loads((bad_dir / "exit.json").read_text())
        assert bad_exit["returncode"] != 0
        assert bad_exit["plumbing"] is True
        assert bad_exit["cancelled"] is False
        assert "worktree" in (bad_exit["error"] or "").lower()
        assert not (bad_dir / "result.json").exists()

        for good_dir in good_dirs:
            exit_state = json.loads((good_dir / "exit.json").read_text())
            assert exit_state["returncode"] == 0, exit_state
            result = json.loads((good_dir / "result.json").read_text())
            assert result.get("result_commit_sha"), result

        boots = [ln for ln in boot_marker.read_text().splitlines() if ln.strip()]
        assert len(boots) == 1, f"expected the one shared pi process to survive, got {boots}"
    finally:
        os.environ.pop("FAKE_PI_BOOT_MARKER", None)


def test_batch_cancel_of_one_packet_does_not_terminate_session(fake_pi, git_repo, tmp_path):
    """A cancel.requested marker on ONE attempt cancels only that node's
    result; the other packets still complete and the session survives."""
    from adapters.pi_rpc_adapter import _enqueue_attempt, _orchestrator_lock, run_orchestrator

    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    orchestrator_dir = spool / "_orchestrators" / "batch-proj"
    os.environ["FAKE_PI_MODE"] = "ok"
    boot_marker = tmp_path / "boots.txt"
    os.environ["FAKE_PI_BOOT_MARKER"] = str(boot_marker)
    try:
        keep_dirs = [
            _seed_attempt(
                spool, orchestrator_dir, repo, fake_pi, base, name=f"keep{i}", attempt=i
            )
            for i in range(2)
        ]
        cancel_dir = _seed_attempt(
            spool, orchestrator_dir, repo, fake_pi, base, name="cancelled0", attempt=2
        )
        (cancel_dir / "cancel.requested").write_text("")

        attempt_dirs = [keep_dirs[0], cancel_dir, keep_dirs[1]]
        with _orchestrator_lock(orchestrator_dir):
            for attempt_dir in attempt_dirs:
                _enqueue_attempt(orchestrator_dir, attempt_dir)

        rc = run_orchestrator(orchestrator_dir)
        assert rc == 0, "session must not terminate on a single packet's cancel"

        cancel_exit = json.loads((cancel_dir / "exit.json").read_text())
        assert cancel_exit["cancelled"] is True
        assert cancel_exit["returncode"] == 130
        assert not (cancel_dir / "result.json").exists()

        for keep_dir in keep_dirs:
            exit_state = json.loads((keep_dir / "exit.json").read_text())
            assert exit_state == {
                "returncode": 0,
                "cancelled": False,
                "plumbing": False,
                "error": None,
            }, exit_state
            result = json.loads((keep_dir / "result.json").read_text())
            assert result.get("result_commit_sha"), result

        boots = [ln for ln in boot_marker.read_text().splitlines() if ln.strip()]
        assert len(boots) == 1, f"expected the one shared pi process to survive, got {boots}"
    finally:
        os.environ.pop("FAKE_PI_BOOT_MARKER", None)


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


def _zone_packet(*, attempt: int, pointers: dict | None = None) -> dict:
    packet = {
        "node_id": "node-01",
        "title": "T",
        "goal": "G",
        "why": "W",
        "constraints": [],
        "acceptance_criteria": [],
        "required_artifacts": [],
        "job_id": "job-a",
        "execution_attempt_id": f"job-a:attempt:{attempt}",
        "attempt_index": attempt,
        "expected_base_commit_sha": "abc",
        "previous_findings": None,
    }
    if pointers is not None:
        packet["context_pointers"] = pointers
    return packet


_POINTERS = {
    "readme": "/repo/README.md",
    "project_brief": "UNAVAILABLE: /repo/PROJECT-BRIEF.md does not exist",
    "foundational_node": "/cfg/graphs/p/nodes/node-00.yaml",
    "neighbor:node-02": "/cfg/graphs/p/nodes/node-02.yaml",
}


def test_split_packet_zones_stable_across_retries():
    stable0, vol0 = split_packet_zones(_zone_packet(attempt=0))
    stable1, vol1 = split_packet_zones(_zone_packet(attempt=1))
    assert stable0 == stable1
    assert "execution_attempt_id" not in stable0
    assert vol0 != vol1
    assert stable0.startswith('{"node_id":')
    assert '"job_id":' in vol0


def test_turn_prompt_puts_node_json_before_attempt_envelope():
    packet = _zone_packet(attempt=0)
    stable, _volatile = split_packet_zones(packet)
    prompt = _assemble_turn_prompt(worktree=Path("/tmp/wt"), packets=[packet])
    assert prompt.startswith(_PACKET_PREAMBLE)
    assert prompt.index(stable) < prompt.index("### ATTEMPT ENVELOPE")
    assert prompt.index(stable) < prompt.index("execution_attempt_id")
    assert prompt.index(stable) < prompt.index("worktree_path:")
    assert "worktree_path: /tmp/wt" in prompt


def test_executor_turn_prompt_retry_preserves_protocol_and_node_prefix():
    """Two attempts of the same node share protocol (preamble) + node zones
    byte-for-byte; only the attempt tail (ids + worktree) varies."""
    from scripts.prompt_topology import common_prefix_tokens, token_estimate

    p0 = _zone_packet(attempt=0)
    p1 = _zone_packet(attempt=1)
    a = _assemble_turn_prompt(worktree=Path("/tmp/wt-a"), packets=[p0])
    b = _assemble_turn_prompt(worktree=Path("/tmp/wt-b"), packets=[p1])
    # Preamble (protocol) is the shared prefix.
    assert a.startswith(_PACKET_PREAMBLE)
    assert b.startswith(_PACKET_PREAMBLE)
    stable, _ = split_packet_zones(p0)
    expected = token_estimate(_PACKET_PREAMBLE) + token_estimate(stable)
    assert common_prefix_tokens(a, b) >= expected


def test_executor_turn_prompt_worktree_stays_in_attempt_zone():
    """worktree_path must not precede the node zone (it busts the cached prefix)."""
    from scripts.prompt_topology import TurnPrompt  # noqa: F401

    tp = build_executor_turn_prompt(
        worktree=Path("/repo/.worktrees/n7"), packets=[_zone_packet(attempt=0)]
    )
    bounds = tp.zone_offsets()
    text = tp.assemble()
    node_end = bounds["node"][1]
    assert text.index("worktree_path:") >= node_end
    assert text.index("execution_attempt_id") >= node_end


def test_executor_turn_prompt_cache_report_potential_reuse():
    """The structural cache report shows protocol+node as reusable prefix and
    attempt as volatile; potential_reuse_ratio > 0 for a real packet."""
    from scripts.prompt_topology import prompt_cache_report

    tp = build_executor_turn_prompt(
        worktree=Path("/tmp/wt"), packets=[_zone_packet(attempt=0)]
    )
    report = prompt_cache_report(tp)
    assert report.protocol_tokens > 0
    assert report.node_tokens > 0
    assert report.attempt_tokens > 0
    assert report.potential_reuse_tokens == report.protocol_tokens + report.node_tokens
    assert 0.0 < report.potential_reuse_ratio < 1.0
    # No provider feed yet -> actual is unmeasured (None), not 0. No bust-loss
    # field exists (provider reality vs GDDP structural potential span
    # different surfaces and are not compared).
    assert report.actual_cached_tokens is None
    assert not hasattr(report, "cache_bust_loss_tokens")


def test_project_zone_renders_pointer_paths_not_contents():
    """The project zone lists canonical file PATHS, sorted by key, with
    UNAVAILABLE markers preserved verbatim — a read is evidence, an embedded
    blob is not."""
    tp = build_executor_turn_prompt(
        worktree=Path("/tmp/wt"),
        packets=[_zone_packet(attempt=0, pointers=_POINTERS)],
    )
    zone = tp.project
    assert zone != ""
    lines = zone.splitlines()
    assert lines[0].startswith("Project context pointers")
    assert lines[1:] == [
        "foundational_node: /cfg/graphs/p/nodes/node-00.yaml",
        "neighbor:node-02: /cfg/graphs/p/nodes/node-02.yaml",
        "project_brief: UNAVAILABLE: /repo/PROJECT-BRIEF.md does not exist",
        "readme: /repo/README.md",
    ]
    # Pointers live only in the project zone — never duplicated into the
    # volatile tail, where a graph-stable list would ride along for free.
    text = tp.assemble()
    assert text.count("/repo/README.md") == 1
    assert "context_pointers" not in text


def test_project_zone_is_empty_without_pointers():
    """Old packets (no context_pointers) fall back to the previous empty
    project zone rather than failing the turn."""
    tp = build_executor_turn_prompt(
        worktree=Path("/tmp/wt"), packets=[_zone_packet(attempt=0)]
    )
    assert tp.project == ""
    assert tp.assemble().startswith(_PACKET_PREAMBLE)


def test_project_zone_sits_between_protocol_and_node():
    tp = build_executor_turn_prompt(
        worktree=Path("/tmp/wt"),
        packets=[_zone_packet(attempt=0, pointers=_POINTERS)],
    )
    bounds = tp.zone_offsets()
    assert bounds["protocol"][1] <= bounds["project"][0]
    assert bounds["project"][1] <= bounds["node"][0]
    assert bounds["node"][1] <= bounds["attempt"][0]
    text = tp.assemble()
    assert text.index("worktree_path:") >= bounds["node"][1]


def test_retry_shares_protocol_project_and_node_prefix():
    """Two attempts of the same node share protocol+project+node byte-for-byte:
    pointers are built once per packet, so the pointer block cannot drift
    between retries."""
    from scripts.prompt_topology import common_prefix_tokens, token_estimate

    p0 = _zone_packet(attempt=0, pointers=_POINTERS)
    p1 = _zone_packet(attempt=1, pointers=_POINTERS)
    a = _assemble_turn_prompt(worktree=Path("/tmp/wt-a"), packets=[p0])
    b = _assemble_turn_prompt(worktree=Path("/tmp/wt-b"), packets=[p1])
    stable, _ = split_packet_zones(p0)
    project_zone = build_executor_turn_prompt(
        worktree=Path("/tmp/wt-a"), packets=[p0]
    ).project
    expected = (
        token_estimate(_PACKET_PREAMBLE)
        + token_estimate(project_zone)
        + token_estimate(stable)
    )
    assert common_prefix_tokens(a, b) >= expected


def test_batch_turn_merges_pointers_deterministically():
    """A batch turn carrying two nodes renders one merged, sorted pointer
    block — same bytes regardless of which packet contributed a key."""
    p1 = _zone_packet(attempt=0, pointers={"readme": "/repo/README.md"})
    p2 = _zone_packet(
        attempt=0, pointers={"neighbor:node-03": "/cfg/node-03.yaml"}
    )
    forward = build_project_zone([p1, p2])
    assert forward == build_project_zone([p2, p1])
    assert "readme: /repo/README.md" in forward
    assert "neighbor:node-03: /cfg/node-03.yaml" in forward


def test_model_must_be_explicit(monkeypatch, tmp_path):
    """No silent default: an unset model is a configuration error, an explicit
    constructor arg wins over the env."""
    monkeypatch.delenv("GDDP_PI_RPC_MODEL", raising=False)
    with pytest.raises(ValueError, match="GDDP_PI_RPC_MODEL"):
        PiRpcAdapter(repo="owner/repo", spool_root=tmp_path)

    monkeypatch.setenv("GDDP_PI_RPC_MODEL", "env/model")
    assert PiRpcAdapter(repo="owner/repo", spool_root=tmp_path).model == "env/model"
    assert (
        PiRpcAdapter(
            repo="owner/repo", spool_root=tmp_path, model="explicit/model"
        ).model
        == "explicit/model"
    )


def test_dispatcher_passes_the_model_at_the_call_site(monkeypatch):
    """dispatcher._build_adapter names the model when building PiRpcAdapter so
    the operator's choice is visible where the adapter is constructed."""
    from runtime.heartbeat.dispatcher import _build_adapter

    monkeypatch.setenv("GDDP_PI_RPC_MODEL", "chosen/model")
    seen: dict[str, object] = {}

    class FakePi:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    _build_adapter(FakePi, "pi_rpc", "owner/repo", "/tmp/checkout")
    assert seen["model"] == "chosen/model"
    assert seen["cwd"] == "/tmp/checkout"


# ---------------------------------------------------------------------------
# Context coverage (fix 5): offered pointers vs paths the turn actually read.
#
# Event shapes below are copied from real orchestrator streams in the pi_rpc
# spool (jobs/local-subprocess-spool/*/events.jsonl): tool_execution_start
# carries toolName + args.path, the matching tool_execution_end carries the
# outcome as a top-level isError.
# ---------------------------------------------------------------------------


def _read_start(call_id: str, path: str, tool: str = "read") -> dict:
    return {
        "type": "tool_execution_start",
        "toolCallId": call_id,
        "toolName": tool,
        "args": {"path": path},
    }


def _read_end(call_id: str, tool: str = "read", is_error: bool = False) -> dict:
    return {
        "type": "tool_execution_end",
        "toolCallId": call_id,
        "toolName": tool,
        "result": {"content": [{"type": "text", "text": "..."}], "details": {}},
        "isError": is_error,
    }


def _reads(*paths: str, tool: str = "read") -> list[dict]:
    events: list[dict] = []
    for i, path in enumerate(paths):
        call_id = f"call_{tool}_{i}"
        events.append(_read_start(call_id, path, tool=tool))
        events.append(_read_end(call_id, tool=tool))
    return events


_COVERAGE_POINTERS = {
    "readme": "/repo/README.md",
    "project_brief": "/repo/PROJECT-BRIEF.md",
    "foundational_node": "/cfg/nodes/node-00.yaml",
    "neighbor:node-02": "/cfg/nodes/node-02.yaml",
}


def test_read_paths_come_from_verified_tool_execution_shape():
    """read and grep starts carry args.path; the end event carries the outcome."""
    events = [
        *_reads("/repo/README.md"),
        *_reads("/cfg/nodes/node-02.yaml", tool="grep"),
    ]
    assert extract_read_paths(events) == {
        "/repo/README.md",
        "/cfg/nodes/node-02.yaml",
    }


def test_ls_and_find_are_not_content_access():
    """Awareness that a path exists is not evidence the pointer was consumed."""
    events = [
        *_reads("/repo/README.md", tool="ls"),
        *_reads("/cfg/nodes/node-02.yaml", tool="find"),
    ]
    assert extract_read_paths(events) == set()


def test_failed_and_unfinished_reads_are_not_coverage():
    """An ENOENT read, and a read whose turn died before its end event, are
    both excluded — same strictness as the evaluator's lane extraction."""
    events = [
        _read_start("enoent", "/repo/README.md"),
        _read_end("enoent", is_error=True),
        _read_start("orphan", "/repo/PROJECT-BRIEF.md"),
    ]
    assert extract_read_paths(events) == set()


def test_relative_read_paths_resolve_against_base(tmp_path):
    """About a third of observed read/grep calls use a relative path; pi runs
    with cwd=repo, so they must still match the absolute offered pointers."""
    (tmp_path / "README.md").write_text("# r")
    pointers = {"readme": str(tmp_path / "README.md")}
    coverage = compute_turn_context_coverage(
        pointers=pointers, events=_reads("README.md"), base=tmp_path
    )
    assert coverage["rating"] == "high"
    assert coverage["outside_pointers"] == []


def test_coverage_high_when_every_offered_pointer_is_read():
    coverage = compute_turn_context_coverage(
        pointers=_COVERAGE_POINTERS,
        events=_reads(
            "/repo/README.md",
            "/repo/PROJECT-BRIEF.md",
            "/cfg/nodes/node-00.yaml",
            "/cfg/nodes/node-02.yaml",
        ),
    )
    assert coverage["rating"] == "high"
    assert coverage["offered"] == 4
    assert coverage["content_accessed"] == 4
    assert coverage["not_observed"] == 0
    assert coverage["not_observed_paths"] == []
    assert coverage["groups"]["docs"]["content_accessed"] == 2
    assert coverage["groups"]["neighbors"]["content_accessed"] == 2


def test_coverage_none_when_no_offered_pointer_is_read():
    coverage = compute_turn_context_coverage(
        pointers=_COVERAGE_POINTERS, events=_reads("/repo/scripts/whatever.py")
    )
    assert coverage["rating"] == "none"
    assert coverage["content_accessed"] == 0
    assert coverage["not_observed"] == 4
    assert "/repo/README.md" in coverage["not_observed_paths"]


def test_coverage_low_when_only_a_neighbor_is_read():
    coverage = compute_turn_context_coverage(
        pointers=_COVERAGE_POINTERS, events=_reads("/cfg/nodes/node-02.yaml")
    )
    assert coverage["rating"] == "low"


def test_coverage_medium_when_docs_read_but_offered_neighbors_are_not():
    coverage = compute_turn_context_coverage(
        pointers=_COVERAGE_POINTERS, events=_reads("/repo/README.md")
    )
    assert coverage["rating"] == "medium"


def test_coverage_high_without_neighbors_offered():
    """No neighbors offered + a doc read reaches 'high' — the no-neighbor rule."""
    coverage = compute_turn_context_coverage(
        pointers={"readme": "/repo/README.md"}, events=_reads("/repo/README.md")
    )
    assert coverage["rating"] == "high"


def test_coverage_skips_unavailable_pointers():
    """An UNAVAILABLE marker is offered as context but is not a ratable path,
    so it cannot be held against the turn as unread."""
    coverage = compute_turn_context_coverage(
        pointers={
            "readme": "/repo/README.md",
            "project_brief": "UNAVAILABLE: /repo/PROJECT-BRIEF.md does not exist",
        },
        events=_reads("/repo/README.md"),
    )
    assert coverage["offered"] == 1
    assert coverage["offered_paths"] == ["/repo/README.md"]
    assert coverage["rating"] == "high"
    assert coverage["unavailable_pointer_keys"] == ["project_brief"]


def test_coverage_is_none_when_nothing_ratable_was_offered():
    """No artifact beats a misleading 'none' for a packet carrying no pointers
    (or only UNAVAILABLE ones)."""
    assert compute_turn_context_coverage(pointers={}, events=_reads("/x")) is None
    assert (
        compute_turn_context_coverage(
            pointers={"readme": "UNAVAILABLE: /repo/README.md does not exist"},
            events=_reads("/x"),
        )
        is None
    )
    # "invariants" is offered but deliberately unrated (optional per project).
    assert (
        compute_turn_context_coverage(
            pointers={"invariants": "/repo/INVARIANTS.md"}, events=[]
        )
        is None
    )


def test_coverage_records_reads_outside_the_offered_pointers():
    """The research-drift signal: an orchestrator rediscovering the project
    shows a long outside_pointers list whatever its rating is."""
    coverage = compute_turn_context_coverage(
        pointers=_COVERAGE_POINTERS,
        events=_reads(
            "/repo/README.md",
            "/cfg/nodes/node-00.yaml",
            "/repo/context.md",
            "/repo/vocabulary.md",
            "/repo/LOOP.md",
        ),
    )
    assert coverage["rating"] == "high"
    assert coverage["outside_pointers"] == [
        "/repo/LOOP.md",
        "/repo/context.md",
        "/repo/vocabulary.md",
    ]
    assert len(coverage["read_paths"]) == 5


def test_coverage_record_is_json_serializable():
    coverage = compute_turn_context_coverage(
        pointers=_COVERAGE_POINTERS, events=_reads("/repo/README.md")
    )
    assert json.loads(json.dumps(coverage, sort_keys=True)) == coverage


def test_turn_writes_context_coverage_artifact(fake_pi, git_repo, tmp_path):
    """run_orchestrator writes context_coverage.json beside
    prompt_cache_report.json, measured against the pointers the packet
    offered and the reads the turn actually made."""
    from adapters.pi_rpc_adapter import _enqueue_attempt, _orchestrator_lock, run_orchestrator

    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    orchestrator_dir = spool / "_orchestrators" / "batch-proj"
    readme = repo / "README.md"
    readme.write_text("# offered\n")
    neighbor = tmp_path / "cfg" / "node-02.yaml"
    neighbor.parent.mkdir(parents=True)
    neighbor.write_text("node_id: node-02\n")

    os.environ["FAKE_PI_MODE"] = "ok"
    # Read one offered doc (relative, as a model naturally would) plus one
    # path that was never offered.
    os.environ["FAKE_PI_READ_PATHS"] = f"README.md,{repo / 'context.md'}"
    attempt_dir = _seed_attempt(
        spool,
        orchestrator_dir,
        repo,
        fake_pi,
        base,
        name="coverage0",
        attempt=0,
        pointers={
            "readme": str(readme),
            "project_brief": "UNAVAILABLE: missing",
            "neighbor:node-02": str(neighbor),
        },
    )
    with _orchestrator_lock(orchestrator_dir):
        _enqueue_attempt(orchestrator_dir, attempt_dir)

    assert run_orchestrator(orchestrator_dir) == 0
    coverage = json.loads((attempt_dir / "context_coverage.json").read_text())
    assert coverage["offered"] == 2
    assert coverage["accessed_paths"] == [str(readme.resolve())]
    assert coverage["not_observed_paths"] == [str(neighbor.resolve())]
    # Doc read, neighbor offered and unread.
    assert coverage["rating"] == "medium"
    assert coverage["outside_pointers"] == [str((repo / "context.md").resolve())]
    assert coverage["unavailable_pointer_keys"] == ["project_brief"]


def test_coverage_absence_never_fails_a_turn(fake_pi, git_repo, tmp_path):
    """A packet with no pointers still persists its node result; coverage is
    measurement, not a gate."""
    from adapters.pi_rpc_adapter import _enqueue_attempt, _orchestrator_lock, run_orchestrator

    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    orchestrator_dir = spool / "_orchestrators" / "batch-proj"
    os.environ["FAKE_PI_MODE"] = "ok"
    attempt_dir = _seed_attempt(
        spool, orchestrator_dir, repo, fake_pi, base, name="nocoverage0", attempt=1
    )
    with _orchestrator_lock(orchestrator_dir):
        _enqueue_attempt(orchestrator_dir, attempt_dir)

    assert run_orchestrator(orchestrator_dir) == 0
    assert not (attempt_dir / "context_coverage.json").exists()
    assert json.loads((attempt_dir / "result.json").read_text())["result_commit_sha"]
