import hashlib
import hmac
import json
import sqlite3
import sys
from pathlib import Path
import pytest

# Add repo root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import intake_server

@pytest.fixture
def mock_env(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    opclaw_root = tmp_path / "opclaw"
    opclaw_root.mkdir()

    monkeypatch.setattr(intake_server, "DB_PATH", db_path)
    monkeypatch.setattr(intake_server, "OPCLAW_ROOT", opclaw_root)
    # Mock now to return a fixed timestamp
    monkeypatch.setattr(intake_server, "now", lambda: "2025-01-01T00:00:00+00:00")

    # Initialize DB with the schema from init_db.py
    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE events (
            event_id                TEXT PRIMARY KEY,
            schema_version          TEXT NOT NULL DEFAULT '1.0',
            received_at             TEXT NOT NULL,
            source                  TEXT NOT NULL,
            event_type              TEXT NOT NULL,
            actor                   TEXT,
            branch                  TEXT,
            base_branch             TEXT,
            pr_number               INTEGER,
            issue_number            INTEGER,
            commit_sha              TEXT,
            url                     TEXT,
            project_id              TEXT,
            project_node_candidates TEXT,
            scope_status            TEXT DEFAULT 'pending',
            priority                TEXT DEFAULT 'pending',
            risk_level              TEXT DEFAULT 'pending',
            raw_payload_path        TEXT,
            normalized_payload_path TEXT,
            classification          TEXT,
            routing                 TEXT,
            status                  TEXT DEFAULT 'received'
        )
    """)
    con.close()

    return {"db_path": db_path, "opclaw_root": opclaw_root}

@pytest.fixture
def client(mock_env):
    intake_server.app.config["TESTING"] = True
    with intake_server.app.test_client() as client:
        yield client

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}

def test_webhook_no_secret(client, monkeypatch):
    monkeypatch.setattr(intake_server, "WEBHOOK_SECRET", "")
    payload = {"action": "opened", "pull_request": {"number": 1}}
    response = client.post(
        "/webhook",
        data=json.dumps(payload),
        headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"}
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "accepted"

def test_webhook_invalid_signature(client, monkeypatch):
    monkeypatch.setattr(intake_server, "WEBHOOK_SECRET", "test_secret")
    payload = {"action": "opened"}
    response = client.post(
        "/webhook",
        data=json.dumps(payload),
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=wrong",
            "Content-Type": "application/json"
        }
    )
    assert response.status_code == 401
    assert response.get_json() == {"error": "invalid signature"}

def test_webhook_valid_signature(client, monkeypatch):
    secret = "test_secret"
    monkeypatch.setattr(intake_server, "WEBHOOK_SECRET", secret)
    payload = {"action": "opened", "pull_request": {"number": 123}}
    payload_bytes = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhook",
        data=payload_bytes,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json"
        }
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "accepted"

def test_webhook_ignored_event(client, monkeypatch):
    monkeypatch.setattr(intake_server, "WEBHOOK_SECRET", "")
    payload = {"action": "unknown"}
    response = client.post(
        "/webhook",
        data=json.dumps(payload),
        headers={"X-GitHub-Event": "ping", "Content-Type": "application/json"}
    )
    assert response.status_code == 200
    assert response.get_json() == {"status": "ignored"}

def test_webhook_accepted_event(client, mock_env, monkeypatch):
    monkeypatch.setattr(intake_server, "WEBHOOK_SECRET", "")
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "head": {"ref": "feature", "sha": "abcdef"},
            "base": {"ref": "main"},
            "html_url": "https://github.com/org/repo/pull/42"
        },
        "sender": {"login": "jules"}
    }

    response = client.post(
        "/webhook",
        data=json.dumps(payload),
        headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"}
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "accepted"
    event_id = data["event_id"]
    assert event_id.startswith("evt_20250101")

    # Check raw payload persistence
    raw_dir = mock_env["opclaw_root"] / "events" / "raw"
    files = list(raw_dir.glob("pull_request_*.json"))
    assert len(files) == 1
    with open(files[0]) as f:
        saved_payload = json.load(f)
    assert saved_payload == payload

    # Check database insertion
    con = sqlite3.connect(mock_env["db_path"])
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    con.close()

    assert row is not None
    assert row["event_type"] == "pull_request.opened"
    assert row["actor"] == "jules"
    assert row["pr_number"] == 42
    assert row["commit_sha"] == "abcdef"
    assert row["branch"] == "feature"
    assert row["url"] == "https://github.com/org/repo/pull/42"
    assert row["status"] == "received"
    assert row["raw_payload_path"] == str(files[0])
