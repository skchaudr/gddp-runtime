"""Contract tests for config's dynamically loaded status-history module."""

from scripts import node_status_history


def test_append_load_and_latest_reason(tmp_path):
    path = node_status_history.append_status_change(
        project_id="project-a",
        node_id="node-a",
        from_status="pending",
        to_status="ready",
        reason="operator approved the frontier",
        runtime_root=tmp_path,
        ts="2026-08-09T12:00:00+00:00",
    )

    assert path == (
        tmp_path / "node_status_history" / "project-a" / "node-a.jsonl"
    )
    assert node_status_history.load_history(
        "project-a", "node-a", runtime_root=tmp_path
    ) == [
        {
            "ts": "2026-08-09T12:00:00+00:00",
            "project_id": "project-a",
            "node_id": "node-a",
            "from_status": "pending",
            "to_status": "ready",
            "reason": "operator approved the frontier",
            "kind": "graph",
            "source": "gddp",
        }
    ]
    assert node_status_history.latest_reason(
        "project-a",
        "node-a",
        runtime_root=tmp_path,
        matching_to_status="ready",
    )["reason"] == "operator approved the frontier"
    assert node_status_history.latest_reason(
        "project-a",
        "node-a",
        runtime_root=tmp_path,
        matching_to_status="complete",
    ) is None
