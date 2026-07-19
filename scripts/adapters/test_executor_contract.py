from __future__ import annotations

import json
import os
import signal
import sqlite3
import sys
import time
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import heartbeat as legacy_heartbeat
from adapters.executor_protocol import (
    DispatchResult,
    ExecutorAdapter,
    NodePacket,
    SessionRef,
)
from adapters.jules_action_adapter import JulesActionAdapter
from adapters.jules_cli_adapter import JulesCliAdapter
from adapters.local_subprocess_adapter import LocalSubprocessAdapter
from adapters import local_subprocess_adapter
from runtime.heartbeat import dispatcher


def _persisted_job(*, executor: str = "jules_cli", attempt: int = 2) -> dict:
    return {
        "job_id": "job-123",
        "node_id": "node-456",
        "title": "Repair transport",
        "goal": "Preserve semantic intent",
        "why": "Executors must receive equivalent work",
        "constraints": json.dumps([
            "No shell",
            {"platform": ["darwin", "linux"]},
        ]),
        "acceptance_criteria": json.dumps([
            "Packet is immutable",
            {"tests": ["success", "failure"]},
        ]),
        "_required_artifacts": json.dumps(["decision.md", "patch.diff"]),
        "attempt": attempt,
        "_previous_findings": json.dumps({
            "verdict": "changes_requested",
            "integrity_verdict": "pass",
            "reasoning": "One semantic field was dropped",
            "findings": [
                {"severity": "high", "summary": "Preserve attempt identity"},
            ],
            "criteria_findings": [
                {
                    "criterion_id": "docs-usage-file",
                    "judgment": "judged_fail",
                    "evidence": ["docs/usage.md is absent"],
                    "reasoning": "The required usage guide was not created",
                },
            ],
        }),
        "executor": executor,
    }


def _packet(attempt: int = 2) -> NodePacket:
    return dispatcher._build_node_packet(_persisted_job(attempt=attempt))


def _wait_for_terminal(adapter: LocalSubprocessAdapter, result: DispatchResult):
    assert result.session_ref is not None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = adapter.status(result.session_ref)
        if status.state in {"completed", "failed"}:
            return status
        time.sleep(0.02)
    pytest.fail("local subprocess did not reach a terminal state")


def test_dispatcher_decodes_a_deeply_immutable_packet_without_mutating_job():
    job = _persisted_job()
    original = dict(job)

    packet = dispatcher._build_node_packet(job)

    assert packet.job_id == "job-123"
    assert packet.node_id == "node-456"
    assert packet.attempt_index == 2
    assert packet.execution_attempt_id == "job-123:attempt:2"
    assert packet.constraints[1]["platform"] == ("darwin", "linux")
    assert packet.acceptance_criteria[1]["tests"] == ("success", "failure")
    assert packet.required_artifacts == ("decision.md", "patch.diff")
    assert packet.previous_findings is not None
    assert packet.previous_findings["findings"][0]["severity"] == "high"
    assert job == original

    with pytest.raises(FrozenInstanceError):
        packet.goal = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        packet.constraints[1]["platform"] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        packet.previous_findings["verdict"] = "pass"  # type: ignore[index]


def test_jules_renderers_preserve_the_same_packet_semantics():
    packet = _packet()

    action_body = JulesActionAdapter("owner/repo").build_issue_body(packet)
    cli_body = JulesCliAdapter("owner/repo")._build_session_instructions(packet)

    for rendered in (action_body, cli_body):
        assert "Preserve semantic intent" in rendered
        assert "Executors must receive equivalent work" in rendered
        assert "No shell" in rendered
        assert "platform: ('darwin', 'linux')" in rendered
        assert "Packet is immutable" in rendered
        assert "tests: ('success', 'failure')" in rendered
        assert "decision.md" in rendered
        assert "patch.diff" in rendered
        assert "attempt: 2" in rendered
        assert "execution_attempt_id: job-123:attempt:2" in rendered
        assert "One semantic field was dropped" in rendered
        assert "[high] Preserve attempt identity" in rendered
        assert "node: node-456" in rendered
        assert "job: job-123" in rendered
        assert "docs-usage-file" in rendered
        assert "judged_fail" in rendered
        assert "docs/usage.md is absent" in rendered
        assert "The required usage guide was not created" in rendered


def test_direct_registry_contains_only_runtime_lifecycle_conformers(tmp_path):
    cli = JulesCliAdapter("owner/repo")
    local = LocalSubprocessAdapter(
        repo="owner/repo",
        argv=(sys.executable, "-c", "pass"),
        spool_root=tmp_path,
    )
    action = JulesActionAdapter("owner/repo")

    assert isinstance(cli, ExecutorAdapter)
    assert isinstance(local, ExecutorAdapter)
    assert not isinstance(action, ExecutorAdapter)
    assert dispatcher.ADAPTERS == {
        "jules_cli": JulesCliAdapter,
        "local_subprocess": LocalSubprocessAdapter,
    }
    assert dispatcher.MEDIATED_ADAPTERS == {"jules": JulesActionAdapter}

def test_local_subprocess_rejects_parent_directory_session_refs(tmp_path):
    spool_root = tmp_path / "spool"
    spool_root.mkdir()
    adapter = LocalSubprocessAdapter(
        repo="owner/repo",
        argv=(sys.executable, "-c", "pass"),
        spool_root=spool_root,
    )
    parent_ref = SessionRef(executor="local_subprocess", session_id="..")

    assert adapter.status(parent_ref).state == "failed"
    assert adapter.cancel(parent_ref) is False
    assert not (tmp_path / "cancel.requested").exists()


@pytest.mark.parametrize(
    ("executor", "adapter_cls", "issue_url"),
    (
        ("jules", JulesActionAdapter, "https://github.com/owner/repo/issues/42"),
        ("jules_cli", JulesCliAdapter, None),
        ("local_subprocess", LocalSubprocessAdapter, None),
    ),
)
def test_dispatch_returns_common_receipt_and_passes_same_node_packet(
    monkeypatch, tmp_path, executor, adapter_cls, issue_url
):
    job = _persisted_job(executor=executor)
    receipt = DispatchResult(success=True, issue_url=issue_url)
    adapter_dispatch = MagicMock(return_value=receipt)
    monkeypatch.setattr(adapter_cls, "dispatch", adapter_dispatch)
    monkeypatch.setenv(
        "GDDP_LOCAL_SUBPROCESS_ARGV",
        json.dumps([sys.executable, "-c", "pass"]),
    )
    monkeypatch.setenv("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR", str(tmp_path))

    result = dispatcher.dispatch(job, "owner/repo")

    assert result is receipt
    dispatched_packet = adapter_dispatch.call_args.args[0]
    assert isinstance(dispatched_packet, NodePacket)
    assert dispatched_packet.to_json_value() == _packet().to_json_value()


def test_legacy_heartbeat_dispatches_the_central_node_packet(monkeypatch, tmp_path):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            classification TEXT,
            scope_status TEXT
        );
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            event_id TEXT,
            project_id TEXT,
            repo TEXT,
            node_id TEXT NOT NULL,
            job_type TEXT NOT NULL,
            executor TEXT NOT NULL,
            queue_state TEXT,
            title TEXT NOT NULL,
            goal TEXT NOT NULL,
            why TEXT,
            constraints TEXT,
            acceptance_criteria TEXT,
            priority TEXT,
            status TEXT,
            attempt INTEGER,
            max_attempts INTEGER,
            artifacts_dir TEXT
        );
        CREATE TABLE queue_records (
            queue_item_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            queue TEXT NOT NULL,
            available_at TEXT NOT NULL
        );
        INSERT INTO events (event_id, event_type, status)
        VALUES ('event-1', 'issue.opened', 'received');
        """
    )
    dispatched = MagicMock(
        return_value=DispatchResult(
            success=True,
            issue_url="https://github.com/owner/repo/issues/42",
        )
    )
    identifiers = iter(("job-id", "queue-id"))
    monkeypatch.setattr(legacy_heartbeat, "connect", lambda: connection)
    monkeypatch.setattr(legacy_heartbeat, "job_dir", lambda job_id: tmp_path / job_id)
    monkeypatch.setattr(legacy_heartbeat, "ts_id", lambda: next(identifiers))
    monkeypatch.setattr(JulesActionAdapter, "dispatch", dispatched)
    monkeypatch.delenv("GDDP_EXECUTOR_OVERRIDE", raising=False)

    legacy_heartbeat.run_heartbeat("owner/repo")

    packet = dispatched.call_args.args[0]
    assert isinstance(packet, NodePacket)
    assert packet.job_id == "job_job-id"
    assert packet.node_id == legacy_heartbeat.PHASE3_NODE["node_id"]
    assert packet.attempt_index == 0
    assert packet.required_artifacts == tuple(
        legacy_heartbeat.PHASE3_NODE["required_artifacts"]
    )

def test_local_subprocess_persists_exact_packet_and_collects_after_reinstantiation(tmp_path):
    argv = (
        sys.executable,
        "-c",
        "import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data)",
    )
    adapter = LocalSubprocessAdapter(repo="owner/repo", argv=argv, spool_root=tmp_path)
    packet = _packet()

    first = adapter.dispatch(packet)
    second = adapter.dispatch(packet)

    assert first.success is True
    assert second.success is True
    assert first.session_ref is not None
    assert second.session_ref is not None
    assert first.session_ref.session_id != second.session_ref.session_id
    assert "attempt-2" in first.session_ref.session_id
    assert _wait_for_terminal(adapter, first).state == "completed"
    assert _wait_for_terminal(adapter, second).state == "completed"

    reinstantiated = LocalSubprocessAdapter(
        repo="owner/repo", argv=argv, spool_root=tmp_path
    )
    assert reinstantiated.status(first.session_ref).state == "completed"
    destination = tmp_path / "collected" / "result.patch"
    collected = reinstantiated.collect(first.session_ref, destination)

    assert collected.success is True
    assert collected.patch_path == str(destination)
    assert collected.patch_text == packet.to_json()
    assert destination.read_text() == packet.to_json()
    assert json.loads(collected.patch_text) == packet.to_json_value()
    assert json.loads(collected.patch_text)["execution_attempt_id"] == (
        "job-123:attempt:2"
    )


def test_local_subprocess_failure_is_durable_and_not_collectable(tmp_path):
    argv = (
        sys.executable,
        "-c",
        "import sys; sys.stdin.buffer.read(); sys.stderr.write('broken\\n'); raise SystemExit(7)",
    )
    adapter = LocalSubprocessAdapter(repo="", argv=argv, spool_root=tmp_path)


    result = adapter.dispatch(_packet())

    status = _wait_for_terminal(adapter, result)
    assert status.state == "failed"
    assert status.error is not None
    assert "code 7" in status.error
    assert "broken" in status.error

    reinstantiated = LocalSubprocessAdapter(repo="", argv=argv, spool_root=tmp_path)
    assert result.session_ref is not None
    assert reinstantiated.status(result.session_ref).state == "failed"
    collected = reinstantiated.collect(
        result.session_ref, tmp_path / "must-not-exist.patch"
    )
    assert collected.success is False
    assert "code 7" in (collected.error or "")


def test_local_subprocess_default_cwd_is_attempt_isolated(tmp_path):
    adapter = LocalSubprocessAdapter(
        repo="owner/repo",
        argv=(sys.executable, "-c", "from pathlib import Path; print(Path.cwd())"),
        spool_root=tmp_path,
    )

    result = adapter.dispatch(_packet())

    assert result.session_ref is not None
    attempt_dir = tmp_path / result.session_ref.session_id
    command = json.loads((attempt_dir / "command.json").read_text())
    assert Path(command["cwd"]) == attempt_dir / "workspace"
    assert Path(command["cwd"]).is_dir()
    assert _wait_for_terminal(adapter, result).state == "completed"
    assert (attempt_dir / "stdout").read_text().strip() == command["cwd"]


def test_local_subprocess_supervisor_metadata_failure_stops_unpublished_session(
    tmp_path, monkeypatch
):
    adapter = LocalSubprocessAdapter(
        repo="", argv=(sys.executable, "-c", "pass"), spool_root=tmp_path
    )
    supervisor = MagicMock(pid=43212)
    monkeypatch.setattr(
        local_subprocess_adapter.subprocess, "Popen", lambda *a, **k: supervisor
    )
    real_atomic_write = local_subprocess_adapter._atomic_write

    def fail_supervisor_pid(path, content):
        if path.name == "supervisor.pid":
            raise OSError("spool unavailable")
        real_atomic_write(path, content)

    killpg = MagicMock()
    monkeypatch.setattr(local_subprocess_adapter, "_atomic_write", fail_supervisor_pid)
    monkeypatch.setattr(local_subprocess_adapter.os, "killpg", killpg)

    result = adapter.dispatch(_packet())

    assert result.success is False
    assert result.session_ref is None
    killpg.assert_called_once_with(supervisor.pid, signal.SIGTERM)


def test_local_subprocess_closed_startup_handshake_never_launches_child(
    tmp_path, monkeypatch
):
    attempt_dir = tmp_path / "unpublished"
    attempt_dir.mkdir()
    (attempt_dir / "packet.json").write_text(_packet().to_json())
    (attempt_dir / "command.json").write_text(
        json.dumps({"argv": [sys.executable, "-c", "pass"], "cwd": str(tmp_path)})
    )
    start_read, start_write = os.pipe()
    os.close(start_write)
    popen = MagicMock()
    monkeypatch.setattr(local_subprocess_adapter.subprocess, "Popen", popen)

    try:
        assert local_subprocess_adapter._run_attempt(attempt_dir, start_read) == 0
    finally:
        os.close(start_read)

    popen.assert_not_called()
    assert json.loads((attempt_dir / "exit.json").read_text())["returncode"] == 127


def test_local_subprocess_cancel_best_effort_survives_reinstantiation(tmp_path):
    argv = (
        sys.executable,
        "-c",
        "import sys,time; sys.stdin.buffer.read(); time.sleep(30)",
    )
    adapter = LocalSubprocessAdapter(repo="", argv=argv, spool_root=tmp_path)
    result = adapter.dispatch(_packet())
    assert result.session_ref is not None

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if adapter.status(result.session_ref).state == "running":
            break
        time.sleep(0.02)
    else:
        pytest.fail("local subprocess never started")

    assert adapter.cancel(result.session_ref) is True
    assert _wait_for_terminal(adapter, result).state == "failed"

    reinstantiated = LocalSubprocessAdapter(repo="", argv=argv, spool_root=tmp_path)
    terminal = reinstantiated.status(result.session_ref)
    assert terminal.state == "failed"
    assert terminal.error is not None
    assert "cancel" in terminal.error.lower()


def test_local_subprocess_cancel_before_launch_persists_terminal_cancellation(
    tmp_path, monkeypatch
):
    adapter = LocalSubprocessAdapter(
        repo="", argv=(sys.executable, "-c", "raise SystemExit(99)"), spool_root=tmp_path
    )
    session_ref = SessionRef(executor="local_subprocess", session_id="pending")
    attempt_dir = tmp_path / session_ref.session_id
    attempt_dir.mkdir()
    (attempt_dir / "packet.json").write_text(_packet().to_json())
    (attempt_dir / "command.json").write_text(
        json.dumps({"argv": list(adapter.argv), "cwd": str(tmp_path)})
    )
    popen = MagicMock()
    monkeypatch.setattr(local_subprocess_adapter.subprocess, "Popen", popen)

    assert adapter.cancel(session_ref) is True
    assert local_subprocess_adapter._run_attempt(attempt_dir) == 0

    popen.assert_not_called()
    assert json.loads((attempt_dir / "exit.json").read_text()) == {
        "cancelled": True,
        "returncode": 143,
    }
    terminal = adapter.status(session_ref)
    assert terminal.state == "failed"
    assert "cancel" in (terminal.error or "").lower()
    assert adapter.collect(session_ref, tmp_path / "must-not-exist.patch").success is False


def test_local_subprocess_cancel_during_launch_terminates_after_pid_publication(
    tmp_path, monkeypatch
):
    adapter = LocalSubprocessAdapter(
        repo="", argv=(sys.executable, "-c", "pass"), spool_root=tmp_path
    )
    session_ref = SessionRef(executor="local_subprocess", session_id="racing")
    attempt_dir = tmp_path / session_ref.session_id
    attempt_dir.mkdir()
    (attempt_dir / "packet.json").write_text(_packet().to_json())
    (attempt_dir / "command.json").write_text(
        json.dumps({"argv": list(adapter.argv), "cwd": str(tmp_path)})
    )
    process = MagicMock(pid=43210)
    process.wait.return_value = -signal.SIGTERM

    def publish_cancel_before_pid(*args, **kwargs):
        assert not (attempt_dir / "pid").exists()
        assert adapter.cancel(session_ref) is True
        return process

    killpg = MagicMock()
    monkeypatch.setattr(
        local_subprocess_adapter.subprocess, "Popen", publish_cancel_before_pid
    )
    monkeypatch.setattr(local_subprocess_adapter.os, "killpg", killpg)

    assert local_subprocess_adapter._run_attempt(attempt_dir) == 0

    killpg.assert_called_once_with(process.pid, signal.SIGTERM)
    assert json.loads((attempt_dir / "exit.json").read_text())["cancelled"] is True
    assert adapter.collect(session_ref, tmp_path / "must-not-exist.patch").success is False


def test_local_subprocess_normal_exit_ignores_stale_cancel_marker(
    tmp_path, monkeypatch
):
    attempt_dir = tmp_path / "normal"
    attempt_dir.mkdir()
    (attempt_dir / "packet.json").write_text(_packet().to_json())
    (attempt_dir / "command.json").write_text(
        json.dumps({"argv": [sys.executable, "-c", "pass"], "cwd": str(tmp_path)})
    )
    process = MagicMock(pid=43211)
    process.wait.side_effect = lambda: (
        (attempt_dir / "cancel.requested").write_text(""),
        0,
    )[1]
    monkeypatch.setattr(local_subprocess_adapter.subprocess, "Popen", lambda *a, **k: process)

    assert local_subprocess_adapter._run_attempt(attempt_dir) == 0

    assert json.loads((attempt_dir / "exit.json").read_text()) == {
        "cancelled": False,
        "returncode": 0,
    }
