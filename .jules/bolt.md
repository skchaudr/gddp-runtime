## 2024-05-30 - Memory says ts_id relies on global counter, but the code doesn't
**Learning:** Memory indicated `ts_id()` in `scripts/heartbeat.py` "uses a global counter (`_ts_id_counter`) appended to the timestamp prefix to ensure unique identifiers...". However, `ts_id()` just calls `now().replace(...)[:17]`. This means multiple fast inserts in the same loop will generate identical IDs and fail with `IntegrityError`. This is an issue but not necessarily a performance optimization.
**Action:** Always check the actual code against memory claims.
## 2024-05-30 - Memory states dry_run.py uses executemany, but it uses executemany in a loop
**Learning:** Memory indicated `dry_run.py` uses `executemany` in the `verify_artifacts` function to batch database insertions. The code actually uses a simple `for` loop with `cur.execute` in `verify_artifacts`.
**Action:** Replace `cur.execute` in the loop with `executemany` to perform batch insertions.
## 2024-05-30 - Added executemany optimization for dry_run.py
**Learning:** Found that `verify_artifacts` inside `scripts/dry_run.py` was calling `cur.execute` in a for loop to insert `artifact_verifications`. Replacing this loop with a batch array of inserts and a single `cur.executemany` reduced SQLite overhead and sped up operations slightly.
**Action:** When performing multiple inserts, always prefer `executemany` to batched individual `execute` calls.
