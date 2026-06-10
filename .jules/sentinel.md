## 2025-06-10 - Secure Error Handling in Webhooks
**Vulnerability:** The webhook intake server (`scripts/intake_server.py`) was not catching exceptions like `json.JSONDecodeError` and `sqlite3.Error`, potentially exposing internal application logic or database structure via stack traces to the caller.
**Learning:** External webhook endpoints should fail gracefully and securely by intercepting specific unhandled exceptions before they propagate to the framework layer.
**Prevention:** Always implement explicit exception handling for parsing inputs and interacting with backend services (like databases) on internet-facing routes, returning generic error codes (400, 500) without leaking stack details.
