## 2025-02-12 - [Optimize write_result to use SQLite Native Upsert]
**Learning:** Manual "read-then-write" upserts (`SELECT 1 FROM ...` followed by `INSERT` or `UPDATE`) create unnecessary round-trips to the SQLite database and introduce potential race conditions.
**Action:** Always prefer SQLite's native `INSERT ... ON CONFLICT(...) DO UPDATE SET ...` clause for upsert operations, which halves the execution time by removing the explicit existence check query and executing atomically.
