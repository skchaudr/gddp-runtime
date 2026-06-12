## 2024-06-12 - Missing Error Handling Exposing Stack Traces

**Vulnerability:** The intake server `/webhook` route failed to securely catch and handle `json.JSONDecodeError` during payload parsing and `sqlite3.Error` during database insertion, allowing raw exceptions to surface.
**Learning:** This missing error handling could lead to stack trace leakage and expose internal application paths or configurations when encountering malformed payloads.
**Prevention:** Always implement `try/except` blocks to catch expected exceptions (like JSON or DB errors) at integration points and return generic, fail-secure responses (e.g., HTTP 400 or 500) rather than allowing internal errors to propagate to the client.
