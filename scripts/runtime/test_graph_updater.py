"""
test_graph_updater.py — Tests for the graph updater logic.
"""

import base64
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

# Add the parent directory to sys.path to allow importing from the current package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.runtime.graph_updater import update_graph_node_complete

def test_update_graph_node_complete_missing_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = update_graph_node_complete("p1", "n1", "pr123", "2023-10-27")
    assert result == {"ok": False, "reason": "GITHUB_TOKEN_missing"}

@patch("requests.get")
def test_update_graph_node_complete_project_not_found(mock_get, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    mock_get.return_value.status_code = 404

    result = update_graph_node_complete("p1", "n1", "pr123", "2023-10-27")
    assert result == {"ok": False, "reason": "project_not_found"}

@patch("requests.get")
def test_update_graph_node_complete_yaml_parse_failed(mock_get, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "sha": "sha123",
        "content": base64.b64encode(b"invalid: yaml: :").decode("utf-8")
    }

    result = update_graph_node_complete("p1", "n1", "pr123", "2023-10-27")
    assert result == {"ok": False, "reason": "yaml_parse_failed"}

@patch("requests.get")
def test_update_graph_node_complete_node_not_found(mock_get, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    content = yaml.dump({"nodes": [{"id": "other-node"}]})
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "sha": "sha123",
        "content": base64.b64encode(content.encode()).decode("utf-8")
    }

    result = update_graph_node_complete("p1", "n1", "pr123", "2023-10-27")
    assert result == {"ok": False, "reason": "node_not_found"}

@patch("requests.get")
def test_update_graph_node_complete_already_complete(mock_get, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    content = yaml.dump({"nodes": [{"id": "n1", "status": "complete"}]})
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "sha": "sha123",
        "content": base64.b64encode(content.encode()).decode("utf-8")
    }

    result = update_graph_node_complete("p1", "n1", "pr123", "2023-10-27")
    assert result == {"ok": False, "reason": "already_complete"}

@patch("requests.put")
@patch("requests.get")
def test_update_graph_node_complete_github_commit_failed(mock_get, mock_put, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    content = yaml.dump({"nodes": [{"id": "n1", "status": "ready"}]})
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "sha": "sha123",
        "content": base64.b64encode(content.encode()).decode("utf-8")
    }

    mock_put.return_value.status_code = 500
    mock_put.return_value.text = "Internal Server Error"
    mock_put.return_value.json.side_effect = Exception("JSON decode error")

    result = update_graph_node_complete("p1", "n1", "pr123", "2023-10-27")
    assert result == {"ok": False, "reason": "github_commit_failed: Internal Server Error"}

@patch("requests.put")
@patch("requests.get")
def test_update_graph_node_complete_success(mock_get, mock_put, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    content = yaml.dump({"nodes": [{"id": "n1", "status": "ready"}]})
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "sha": "sha123",
        "content": base64.b64encode(content.encode()).decode("utf-8")
    }

    mock_put.return_value.status_code = 200
    mock_put.return_value.json.return_value = {"commit": {"sha": "newsha123"}}

    result = update_graph_node_complete("p1", "n1", "pr123", "2023-10-27")
    assert result == {"ok": True, "commit_sha": "newsha123"}

    # Verify PUT payload
    args, kwargs = mock_put.call_args
    payload = kwargs["json"]
    assert payload["sha"] == "sha123"
    updated_content = yaml.safe_load(base64.b64decode(payload["content"]).decode())
    target_node = updated_content["nodes"][0]
    assert target_node["status"] == "complete"
    assert target_node["completed_at"] == "2023-10-27"
    assert target_node["merged_pr"] == "pr123"
