import hashlib
import hmac
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

def test_verify_signature_no_secret():
    """Test when WEBHOOK_SECRET is not set (empty string)."""
    original_secret = intake_server.WEBHOOK_SECRET
    intake_server.WEBHOOK_SECRET = ""
    try:
        payload = b'{"action": "opened"}'
        # When no secret is configured, it should always return False to prevent fail-open bypass
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
