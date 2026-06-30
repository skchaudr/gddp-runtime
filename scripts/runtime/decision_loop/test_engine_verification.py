from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from scripts.runtime.decision_loop import engine
from scripts.runtime.decision_loop.context_reader import DecisionContext, ProjectState, RecentActivity
from scripts.runtime.decision_loop.schema import NoOpResult
from scripts.runtime.heartbeat.graph_reader import NodeData


class FakeConnection:
    def close(self) -> None:
        pass


def _node(node_id: str, status: str) -> NodeData:
    return NodeData(
        node_id=node_id,
        title=node_id,
        status=status,
        type="capability",
        why="",
        depends_on=[],
        acceptance=[],
        constraints=[],
        allowed_execution_modes=["jules"],
        required_artifacts=[],
        priority="normal",
        unlocks=[],
    )


def _context() -> DecisionContext:
    complete = _node("done-node", "complete")
    pending = _node("next-node", "pending")
    return DecisionContext(
        project=ProjectState(
            project_id="project-a",
            repo="/tmp/project-a",
            nodes=[complete, pending],
            pending_nodes=[pending],
            in_progress_nodes=[],
            complete_nodes=[complete],
            blocked_nodes=[],
        ),
        activity=RecentActivity(
            active_jobs=[],
            recent_results=[],
            stale_jobs=[],
            stale_events=[],
        ),
        trigger={"event": "cron"},
    )


def test_complete_node_without_receipt_runs_verification_before_dispatch(monkeypatch, tmp_path: Path) -> None:
    result = NoOpResult(action="no_op", reason="verified_pass: done-node", ok=True)
    run_verification = MagicMock(return_value=result)
    dispatch = MagicMock()

    monkeypatch.setattr(engine, "_connect", lambda: FakeConnection())
    monkeypatch.setattr(engine, "_clean_stale_state", lambda con: 0)
    monkeypatch.setattr(engine, "read_context", lambda reader, con, project_id, trigger: _context())
    monkeypatch.setattr(engine, "_write_decision_result", lambda result, project_id: None)
    monkeypatch.setattr(engine, "receipt_exists", lambda project_id, node_id: False)
    monkeypatch.setattr(engine, "_run_verification", run_verification)
    monkeypatch.setattr(engine.dispatch_next, "run", dispatch)

    actual = engine.handle_event({"event": "cron"}, "project-a", config_path=str(tmp_path))

    assert actual == result
    run_verification.assert_called_once()
    assert run_verification.call_args.args[1].node_id == "done-node"
    dispatch.assert_not_called()


def test_complete_node_with_receipt_is_skipped(monkeypatch, tmp_path: Path) -> None:
    dispatch_result = NoOpResult(action="no_op", reason="dispatch placeholder", ok=True)
    run_verification = MagicMock()
    dispatch = MagicMock(return_value=dispatch_result)

    monkeypatch.setattr(engine, "_connect", lambda: FakeConnection())
    monkeypatch.setattr(engine, "_clean_stale_state", lambda con: 0)
    monkeypatch.setattr(engine, "read_context", lambda reader, con, project_id, trigger: _context())
    monkeypatch.setattr(engine, "_write_decision_result", lambda result, project_id: None)
    monkeypatch.setattr(engine, "receipt_exists", lambda project_id, node_id: True)
    monkeypatch.setattr(engine, "_run_verification", run_verification)
    monkeypatch.setattr(engine.dispatch_next, "run", dispatch)

    actual = engine.handle_event({"event": "cron"}, "project-a", config_path=str(tmp_path))

    assert actual == dispatch_result
    run_verification.assert_not_called()
    dispatch.assert_called_once()
