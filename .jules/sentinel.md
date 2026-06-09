## 2025-02-23 - Prevent Stack Trace Leakage on Malformed Inputs
**Vulnerability:** Stack trace leakage / Denial of Service risk via uncaught `json.JSONDecodeError` and `sqlite3.Error` in the `/webhook` endpoint.
**Learning:** The server failed securely for signature verification but lacked try-except blocks for subsequent parsing (JSON) and DB operations, which could expose internal schemas or crash the request context unexpectedly.
**Prevention:** Always wrap external input parsing (like JSON) and database operations in try-except blocks, failing securely with generic HTTP error codes (e.g., 400 Bad Request, 500 Internal Server Error) to hide internal implementation details.
