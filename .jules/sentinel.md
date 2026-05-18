## 2026-05-18 - Missing Secure Exception Handling
**Vulnerability:** The `/webhook` endpoint leaked stack traces or broke unexpectedly on malformed JSON (`json.JSONDecodeError`) and database connectivity issues (`sqlite3.Error`).
**Learning:** `json.loads` and `con.execute` lack localized exception handling within Flask routes, which defaults to standard unhandled exception bubbling.
**Prevention:** Wrap payload parsing and database transactions in `try...except` blocks, explicitly catching library-specific errors to return controlled 400/500 JSON responses.
