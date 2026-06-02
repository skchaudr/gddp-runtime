## 2024-06-02 - SQLite UPSERT speedup in results_store
**Learning:** Found an opportunity to optimize database updates in `write_result` by replacing read-then-write logic (using `SELECT 1` followed by `INSERT` or `UPDATE`) with SQLite's native `ON CONFLICT DO UPDATE`. This eliminates a query round trip per result processed.
**Action:** Always favor native database upsert capabilities when updating single rows by primary key to save on connection overhead and query parsing time.
