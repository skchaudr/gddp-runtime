## 2025-02-20 - [Fix Auth Bypass in Webhook Intaking]
**Vulnerability:** The `verify_signature` in `intake_server.py` returned `True` (bypassing validation) if the `GITHUB_WEBHOOK_SECRET` was empty/missing, allowing attackers to spoof webhooks unauthenticated.
**Learning:** Security controls should never fail open. If a required authentication configuration is missing, the application must reject requests instead of assuming safety.
**Prevention:** Hardcode default deny behavior. Check that missing configuration flags implicitly fail validation checks (e.g., returning `False` instead of `True`).

## 2025-02-20 - [Fix Unhandled Exceptions Leaking Internals]
**Vulnerability:** The `/webhook` endpoint directly decoded JSON and executed SQLite DB statements without exception handling, risking application crashes and stack trace exposure on bad input or missing tables.
**Learning:** External inputs are untrusted and external state (like a local SQLite DB) can fail or be uninitialized.
**Prevention:** Wrap operations like JSON deserialization and DB connections in `try/except` blocks to catch specific exceptions (e.g., `json.JSONDecodeError`, `sqlite3.Error`) and return sanitized API errors (e.g., `{"error": "invalid json"}`) rather than leaking stack traces.
