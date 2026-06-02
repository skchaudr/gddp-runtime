import time
import os
import sqlite3
import tempfile
from scripts.runtime.results_store import init_db, write_result, DB_PATH
import scripts.runtime.results_store as rs

def benchmark():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test.db")
        rs.DB_PATH = db_file
        init_db()

        start = time.time()
        for i in range(100):
            write_result(
                result_id=f"res_{i}",
                job_id=f"job_{i}",
                executor="jules",
                outcome="success",
                status="needs_review",
            )
        duration = time.time() - start
        print(f"Time for 100 insertions (single mode): {duration:.4f}s")

        con = sqlite3.connect(db_file)
        start = time.time()
        for i in range(100, 200):
            write_result(
                result_id=f"res_{i}",
                job_id=f"job_{i}",
                executor="jules",
                outcome="success",
                status="needs_review",
                con=con
            )
        duration2 = time.time() - start
        con.close()
        print(f"Time for 100 insertions (connection reuse): {duration2:.4f}s")

if __name__ == "__main__":
    benchmark()
