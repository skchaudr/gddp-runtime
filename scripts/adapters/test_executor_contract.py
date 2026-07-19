from __future__ import annotations

import json
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
        assert "One semantic field was dropped" in rendered
        assert "[high] Preserve attempt identity" in rendered
        assert "node: node-456" in rendered
        assert "job: job-123" in rendered


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
