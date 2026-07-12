"""Roundtrip tests for intake_server /webhook with signature verification."""

import hashlib
import hmac
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.test_intake_server import reload_intake_server


def _sign_payload(secret: str, payload_bytes: bytes) -> str:
    digest = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _sample_pull_request_opened_payload() -> dict:
    return {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "head": {"ref": "feature-branch", "sha": "abc123def456"},
            "base": {"ref": "main"},
            "html_url": "https://github.com/org/repo/pull/42",
        },
        "repository": {"full_name": "org/repo"},
        "sender": {"login": "test-user"},
    }


def test_signed_webhook_post_creates_event_row_and_raw_payload(monkeypatch, tmp_path):
    secret = "roundtrip-secret"
    mod, runtime_root = reload_intake_server(monkeypatch, tmp_path, webhook_secret=secret)
    client = mod.app.test_client()

    payload = _sample_pull_request_opened_payload()
    payload_bytes = json.dumps(payload).encode()
    signature = _sign_payload(secret, payload_bytes)

    resp = client.post(
        "/webhook",
        data=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request",
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "accepted"
    event_id = body["event_id"]
    assert event_id

    raw_dir = runtime_root / "events" / "raw"
    raw_files = list(raw_dir.glob("pull_request_*.json"))
    assert len(raw_files) == 1
    raw_file = raw_files[0]
    assert json.loads(raw_file.read_text()) == payload

    con = sqlite3.connect(runtime_root / "db" / "queue.db")
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT event_id, event_type, status, raw_payload_path, repo, pr_number "
            "FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
    finally:
        con.close()

    assert row is not None
    assert row["event_id"] == event_id
    assert row["event_type"] == "pull_request.opened"
    assert row["status"] == "received"
    assert row["raw_payload_path"] == str(raw_file)
    assert row["repo"] == "org/repo"
    assert row["pr_number"] == 42