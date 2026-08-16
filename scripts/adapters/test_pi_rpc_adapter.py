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
# FAKE_PI_PROMPT_MARKER, if set, gets one line appended each time a "prompt"
# request is received — lets tests prove a batch of N packets was handled by
# exactly ONE prompt/turn rather than N.
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
# Fork A batch turns: N packets claimed together run as ONE shared turn.
# These call run_orchestrator() directly against a hand-built inbox so the
# batch is deterministic (no race against a spawned supervisor's own claim
# timing — see the dispatch()-based tests above for that path instead).
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
) -> Path:
    """Build one attempt_dir's packet.json + command.json without going
    through dispatch(), so several can be enqueued together before
    run_orchestrator() ever takes its first claim. `attempt` must be unique
    across packets sharing a git_repo fixture so each gets its own
    attempt-ref name (persist_result refuses to overwrite an existing ref
    pointed at unrelated evidence)."""
    attempt_dir = spool / name
    attempt_dir.mkdir(parents=True)
    packet = _packet(base_sha, attempt=attempt, project_id="batch-proj")
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


def test_batch_claims_run_as_one_turn_not_n(fake_pi, git_repo, tmp_path):
    """N packets queued together before the orchestrator's first claim are
    served by exactly ONE prompt/turn, and each gets its own persisted
    result — proving fan-out inside a shared turn, not N serial turns."""
    from adapters.pi_rpc_adapter import _enqueue_attempt, _orchestrator_lock, run_orchestrator

    repo, base = git_repo
    spool = tmp_path / "spool"
    spool.mkdir()
    orchestrator_dir = spool / "_orchestrators" / "batch-proj"
    os.environ["FAKE_PI_MODE"] = "ok"
    prompt_marker = tmp_path / "prompts.txt"
    os.environ["FAKE_PI_PROMPT_MARKER"] = str(prompt_marker)
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

        prompts = [ln for ln in prompt_marker.read_text().splitlines() if ln.strip()]
        assert len(prompts) == 1, f"expected exactly one turn/prompt, got {prompts}"

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
    finally:
        os.environ.pop("FAKE_PI_PROMPT_MARKER", None)


def test_batch_partial_failure_does_not_stop_other_packets_or_session(
    fake_pi, git_repo, tmp_path
):
    """One packet with an unreachable base commit fails in isolation; the
    other packets in the SAME batch still persist real results, and the
    session (and the shared pi process) runs to completion normally."""
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
        attempt_dirs = [good_dirs[0], bad_dir, good_dirs[1]]
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
    """A cancel.requested marker on ONE attempt in a batch cancels only that
    node's result; the other N-1 packets in the same turn still complete
    and the shared session survives."""
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
