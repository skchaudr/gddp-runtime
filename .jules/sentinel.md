## 2024-05-19 - Mandatory Authentication & Stack Trace Prevention
**Vulnerability:** Webhook intake server lacked mandatory signature validation (allowing unauthenticated payloads when secret wasn't configured) and leaked stack traces on malformed JSON or database errors.
**Learning:** Security controls should fail closed. Optional security controls often lead to bypass in environments where configuration is omitted. Error handling must catch specific exceptions (like `JSONDecodeError` and `sqlite3.Error`) to return generic HTTP error codes without exposing internal application state.
**Prevention:** Always enforce authentication (fail closed when secrets are missing) and consistently wrap external input parsing and database operations in `try/except` blocks returning generic responses.
