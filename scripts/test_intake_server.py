import hashlib
import hmac
import importlib
import sqlite3
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# We need to mock 'flask' because it's imported at the top of intake_server.py
# and we only want to test the verify_signature function which doesn't depend on Flask.
from unittest.mock import MagicMock
sys.modules["flask"] = MagicMock()

import scripts.intake_server as intake_server


def _init_events_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS events (
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
                repo                    TEXT,
                project_id              TEXT,
                project_node_candidates TEXT,
                scope_status            TEXT DEFAULT 'pending',
                priority                TEXT DEFAULT 'pending',
                risk_level              TEXT DEFAULT 'pending',
                raw_payload_path        TEXT,
                normalized_payload_path TEXT,
                classification          TEXT,
                routing                 TEXT,
                status                  TEXT DEFAULT 'received',
                claimed_at              TEXT
            );
            """
        )
        con.commit()
    finally:
        con.close()


def reload_intake_server(
    monkeypatch,
    tmp_path,
    *,
    webhook_secret: str | None = "test-secret",
    secret_unresolved: bool = False,
    insecure: bool = False,
):
    """Reload intake_server with a fresh tmp runtime root and secret config."""
    if isinstance(sys.modules.get("flask"), MagicMock):
        sys.modules.pop("flask", None)
    sys.modules.pop("scripts.intake_server", None)

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    _init_events_db(runtime_root / "db" / "queue.db")

    monkeypatch.setenv("GDDP_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.delenv("OPCLAW_ROOT", raising=False)
    if secret_unresolved:
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        monkeypatch.setenv("GDDP_WEBHOOK_SECRET_CMD", "/bin/false")
    elif webhook_secret is not None:
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", webhook_secret)
    else:
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        monkeypatch.delenv("GDDP_WEBHOOK_SECRET_CMD", raising=False)
    if insecure:
        monkeypatch.setenv("GDDP_INTAKE_INSECURE", "1")
    else:
        monkeypatch.delenv("GDDP_INTAKE_INSECURE", raising=False)

    mod = importlib.import_module("scripts.intake_server")
    return mod, runtime_root


def test_health_returns_ok_with_webhook_verification_when_secret_resolved(
    monkeypatch, tmp_path
):
    mod, _runtime_root = reload_intake_server(monkeypatch, tmp_path, webhook_secret="test-secret")
    client = mod.app.test_client()

    resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["webhook_verification"] is True


def test_health_returns_503_when_secret_unresolved(monkeypatch, tmp_path):
    mod, _runtime_root = reload_intake_server(
        monkeypatch, tmp_path, secret_unresolved=True
    )
    client = mod.app.test_client()

    resp = client.get("/health")

    assert resp.status_code == 503
    data = resp.get_json()
    assert data["status"] == "unhealthy"
    assert data["reason"] == "webhook_secret_unresolved"


def test_verify_signature_no_secret():
    """Test when WEBHOOK_SECRET is not set (empty string)."""
    original_secret = intake_server.WEBHOOK_SECRET
    intake_server.WEBHOOK_SECRET = ""
    try:
        payload = b'{"action": "opened"}'
        # When no secret is configured, it should return False
        assert intake_server.verify_signature(payload, "any_signature") is False
    finally:
        intake_server.WEBHOOK_SECRET = original_secret

def test_verify_signature_valid():
    """Test with a valid secret and matching signature."""
    original_secret = intake_server.WEBHOOK_SECRET
    secret = "test_secret"
    intake_server.WEBHOOK_SECRET = secret
    try:
        payload = b'{"test": "payload"}'
        expected_hash = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        signature = f"sha256={expected_hash}"

        assert intake_server.verify_signature(payload, signature) is True
    finally:
        intake_server.WEBHOOK_SECRET = original_secret

def test_verify_signature_invalid_hash():
    """Test with a valid secret but an incorrect signature hash."""
    original_secret = intake_server.WEBHOOK_SECRET
    secret = "test_secret"
    intake_server.WEBHOOK_SECRET = secret
    try:
        payload = b'{"test": "payload"}'
        signature = "sha256=wrong_hash"

        assert intake_server.verify_signature(payload, signature) is False
    finally:
        intake_server.WEBHOOK_SECRET = original_secret

def test_verify_signature_missing_prefix():
    """Test with a valid secret but missing 'sha256=' prefix in signature."""
    original_secret = intake_server.WEBHOOK_SECRET
    secret = "test_secret"
    intake_server.WEBHOOK_SECRET = secret
    try:
        payload = b'{"test": "payload"}'
        expected_hash = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        # Missing 'sha256=' prefix
        signature = expected_hash

        assert intake_server.verify_signature(payload, signature) is False
    finally:
        intake_server.WEBHOOK_SECRET = original_secret

def test_startup_webhook_secret_check_exits_when_unresolved():
    original = intake_server.WEBHOOK_SECRET
    original_insecure = intake_server._INTAKE_INSECURE
    intake_server.WEBHOOK_SECRET = ""
    intake_server._INTAKE_INSECURE = False
    try:
        try:
            intake_server._startup_webhook_secret_check()
            assert False, "expected SystemExit"
        except SystemExit as exc:
            assert exc.code == 1
    finally:
        intake_server.WEBHOOK_SECRET = original
        intake_server._INTAKE_INSECURE = original_insecure


def test_startup_webhook_secret_check_allows_insecure_dev():
    original = intake_server.WEBHOOK_SECRET
    original_insecure = intake_server._INTAKE_INSECURE
    intake_server.WEBHOOK_SECRET = ""
    intake_server._INTAKE_INSECURE = True
    try:
        intake_server._startup_webhook_secret_check()
    finally:
        intake_server.WEBHOOK_SECRET = original
        intake_server._INTAKE_INSECURE = original_insecure


def test_verify_signature_wrong_secret():
    """Test when the payload is signed with a different secret."""
    original_secret = intake_server.WEBHOOK_SECRET
    intake_server.WEBHOOK_SECRET = "correct_secret"
    try:
        payload = b'{"test": "payload"}'
        wrong_secret = "wrong_secret"
        wrong_hash = hmac.new(
            wrong_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        signature = f"sha256={wrong_hash}"

        assert intake_server.verify_signature(payload, signature) is False
    finally:
        intake_server.WEBHOOK_SECRET = original_secret

if __name__ == "__main__":
    print("Running tests for verify_signature...")
    try:
        test_verify_signature_no_secret()
        print("  → test_verify_signature_no_secret: OK")
        test_verify_signature_valid()
        print("  → test_verify_signature_valid: OK")
        test_verify_signature_invalid_hash()
        print("  → test_verify_signature_invalid_hash: OK")
        test_verify_signature_missing_prefix()
        print("  → test_verify_signature_missing_prefix: OK")
        test_verify_signature_wrong_secret()
        print("  → test_verify_signature_wrong_secret: OK")
        print("\nAll tests passed!")
    except AssertionError as e:
        print(f"\nTest failed!")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
