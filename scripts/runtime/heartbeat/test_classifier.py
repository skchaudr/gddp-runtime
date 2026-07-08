"""Tests for classifier node-tag matching (item 1.5 hardening)."""

from scripts.runtime.heartbeat.classifier import classify


class FakeEvent:
    """Dict-like stand-in for a sqlite3.Row used by the classifier."""

    def __init__(self, **kwargs):
        self._data = kwargs

    def __getitem__(self, key):
        return self._data.get(key)

    def keys(self):
        return self._data.keys()


class FakeNode:
    """Minimal stand-in for graph_reader.NodeData."""

    def __init__(self, node_id, priority="normal", allowed_execution_modes=None):
        self.node_id = node_id
        self.priority = priority
        self.allowed_execution_modes = allowed_execution_modes or ["jules"]


def _issue_event(url=None, branch=None):
    return FakeEvent(
        event_type="issue.opened",
        url=url,
        branch=branch,
    )


class TestNodeTagMatching:
    def test_node_tag_in_url_matches_specific_node(self):
        nodes = [
            FakeNode("auth-bug", priority="low"),
            FakeNode("high-prio-thing", priority="high"),
        ]
        event = _issue_event(url="https://example.com/issues/1  node: auth-bug")
        result = classify(event, nodes)
        assert result["matched_node_id"] == "auth-bug"

    def test_node_tag_for_unready_node_returns_none(self):
        nodes = [
            FakeNode("auth-bug", priority="low"),
            FakeNode("high-prio-thing", priority="high"),
        ]
        event = _issue_event(url="https://example.com/issues/1  node: not-ready-node")
        assert classify(event, nodes) is None

    def test_no_node_tag_returns_none(self):
        # No fallback: untagged issues must never dispatch (public repos).
        nodes = [
            FakeNode("auth-bug", priority="low"),
            FakeNode("high-prio-thing", priority="high"),
        ]
        event = _issue_event(url="https://example.com/issues/1")
        assert classify(event, nodes) is None

    def test_node_tag_in_issue_body_matches(self, tmp_path):
        raw = tmp_path / "issues_raw.json"
        raw.write_text(
            '{"issue": {"title": "Fix the auth boundary", '
            '"body": "Please implement this.\\n\\nnode: auth-bug"}}'
        )
        nodes = [
            FakeNode("auth-bug", priority="low"),
            FakeNode("high-prio-thing", priority="high"),
        ]
        event = FakeEvent(
            event_type="issue.opened",
            url="https://example.com/issues/1",
            branch=None,
            raw_payload_path=str(raw),
        )
        result = classify(event, nodes)
        assert result["matched_node_id"] == "auth-bug"

    def test_non_issue_opened_returns_none(self):
        nodes = [FakeNode("auth-bug")]
        event = FakeEvent(event_type="pull_request.opened", url=None, branch=None)
        assert classify(event, nodes) is None

    def test_empty_ready_nodes_returns_none(self):
        event = _issue_event(url="https://example.com/issues/1  node: auth-bug")
        assert classify(event, []) is None

    def test_node_tag_in_branch_matches(self):
        nodes = [
            FakeNode("auth-bug", priority="low"),
            FakeNode("high-prio-thing", priority="high"),
        ]
        event = _issue_event(
            url="https://example.com/issues/1",
            branch="feature/node:auth-bug",
        )
        result = classify(event, nodes)
        assert result["matched_node_id"] == "auth-bug"
