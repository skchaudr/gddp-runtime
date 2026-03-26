import json
import hmac
import hashlib
from unittest.mock import patch, MagicMock
import pytest
from scripts.intake_server import app, verify_signature, normalize_event

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health(client):
    """Test the health endpoint."""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json == {"status": "ok"}

def test_verify_signature_no_secret():
    """Test verify_signature when WEBHOOK_SECRET is not set."""
    with patch('scripts.intake_server.WEBHOOK_SECRET', ''):
        assert verify_signature(b'payload', 'any_sig') is True

def test_verify_signature_valid():
    """Test verify_signature with a valid signature."""
    secret = 'test_secret'
    payload = b'{"action": "opened"}'
    expected_sig = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()

    with patch('scripts.intake_server.WEBHOOK_SECRET', secret):
        assert verify_signature(payload, expected_sig) is True

def test_verify_signature_invalid():
    """Test verify_signature with an invalid signature."""
    secret = 'test_secret'
    payload = b'{"action": "opened"}'

    with patch('scripts.intake_server.WEBHOOK_SECRET', secret):
        assert verify_signature(payload, "sha256=invalid") is False

def test_normalize_event_pull_request():
    """Test normalize_event with a pull_request event."""
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 123,
            "head": {"ref": "feature-branch", "sha": "abc1234"},
            "base": {"ref": "main"},
            "html_url": "https://github.com/owner/repo/pull/123"
        },
        "sender": {"login": "jules"}
    }
    event = normalize_event("pull_request", payload)
    assert event is not None
    assert event["event_type"] == "pull_request.opened"
    assert event["actor"] == "jules"
    assert event["pr_number"] == 123
    assert event["branch"] == "feature-branch"
    assert event["commit_sha"] == "abc1234"

def test_normalize_event_ignored():
    """Test normalize_event with an unhandled event."""
    payload = {"action": "labeled"}
    event = normalize_event("pull_request", payload)
    assert event is None

def test_normalize_event_issue():
    """Test normalize_event with an issues event."""
    payload = {
        "action": "opened",
        "issue": {
            "number": 456,
            "html_url": "https://github.com/owner/repo/issues/456"
        },
        "sender": {"login": "jules"}
    }
    event = normalize_event("issues", payload)
    assert event is not None
    assert event["event_type"] == "issue.opened"
    assert event["issue_number"] == 456

def test_normalize_event_push():
    """Test normalize_event with a push event."""
    payload = {
        "ref": "refs/heads/main",
        "after": "def456",
        "sender": {"login": "jules"}
    }
    event = normalize_event("push", payload)
    assert event is not None
    assert event["event_type"] == "push.branch_updated"
    assert event["branch"] == "main"
    assert event["commit_sha"] == "def456"

@patch('scripts.intake_server.sqlite3.connect')
@patch('scripts.intake_server.Path.write_text')
@patch('scripts.intake_server.Path.mkdir')
def test_webhook_success(mock_mkdir, mock_write_text, mock_connect, client):
    """Test successful webhook processing."""
    payload = {
        "action": "opened",
        "pull_request": {"number": 1},
        "sender": {"login": "user"}
    }
    payload_bytes = json.dumps(payload).encode()

    # Mock database connection and cursor
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    # Mock WEBHOOK_SECRET to be empty for simplicity
    with patch('scripts.intake_server.WEBHOOK_SECRET', ''):
        response = client.post(
            '/webhook',
            data=payload_bytes,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"}
        )

    assert response.status_code == 200
    assert response.json["status"] == "accepted"
    assert "event_id" in response.json

    # Verify file was "saved"
    assert mock_write_text.called
    # Verify database was "updated"
    assert mock_conn.execute.called
    assert mock_conn.commit.called

@patch('scripts.intake_server.WEBHOOK_SECRET', 'secret')
def test_webhook_invalid_signature(client):
    """Test webhook with invalid signature."""
    response = client.post(
        '/webhook',
        data=b'{}',
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=wrong"
        }
    )
    assert response.status_code == 401
    assert response.json == {"error": "invalid signature"}

def test_webhook_ignored_event(client):
    """Test webhook with an ignored event type."""
    with patch('scripts.intake_server.Path.write_text'):
        with patch('scripts.intake_server.Path.mkdir'):
            response = client.post(
                '/webhook',
                data=json.dumps({"action": "labeled"}).encode(),
                headers={"X-GitHub-Event": "pull_request"}
            )
    assert response.status_code == 200
    assert response.json == {"status": "ignored"}
