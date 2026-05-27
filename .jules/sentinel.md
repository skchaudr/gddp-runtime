## 2024-05-27 - [Sentinel] Fix Webhook Authentication Bypass and Prevent Info Disclosure

**Vulnerability:**
1. Fail-open authentication bypass: `scripts/intake_server.py` returned `True` for `verify_signature` if `WEBHOOK_SECRET` was unconfigured, allowing unauthenticated attackers to spoof events if a deployment lacked the secret.
2. Information Disclosure/DoS: The `/webhook` route was missing error handling for `json.loads` and database inserts, exposing the application to crashes and potentially leaking stack traces on malformed payloads or database errors.

**Learning:**
Security defaults must be fail-closed, particularly for endpoints handling external events. Relying on an "optional" configuration for core authentication guarantees bypass if human misconfiguration occurs. Additionally, exposing raw application errors across external boundaries violates secure error handling practices.

**Prevention:**
Enforce mandatory existence of secrets for validation functions to return true. Wrap all deserialization and database insertion logic in `try-except` blocks, catching specific exceptions (`json.JSONDecodeError`, `sqlite3.Error`) and returning generic, safe HTTP error responses (e.g., 400 or 500 status codes with minimal detail).
