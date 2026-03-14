"""
results_store.py — Persistence for return router results.

Records every attempt to advance the graph from a merged PR.
Uses a dedicated table in queue.db or a separate DB for isolation.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Path to the database
DB_PATH = Path(__file__).parent.parent.parent / "db" / "queue.db"

def _now():
    return datetime.now(timezone.utc).isoformat()

def init_db():
    """Ensure the results table exists."""
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS return_results (
                id          TEXT PRIMARY KEY,
                repo_name   TEXT NOT NULL,
                node_id     TEXT,
                pr_number   INTEGER,
                merged_at   TEXT,
                status      TEXT NOT NULL, -- pending | completed | failed | rejected
                reason      TEXT,
                commit_sha  TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        con.commit()
    finally:
        con.close()

def write_result(
    result_id: str,
    repo_name: str,
    status: str,
    node_id: str = None,
    pr_number: int = None,
    merged_at: str = None,
    reason: str = None,
    commit_sha: str = None,
    created_at: str = None
):
    """Inserts or updates a result row."""
    init_db()
    con = sqlite3.connect(DB_PATH)
    try:
        # Check if record exists
        cur = con.cursor()
        cur.execute("SELECT 1 FROM return_results WHERE id = ?", (result_id,))
        exists = cur.fetchone()

        if not exists:
            con.execute("""
                INSERT INTO return_results (
                    id, repo_name, node_id, pr_number, merged_at,
                    status, reason, commit_sha, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result_id, repo_name, node_id, pr_number, merged_at,
                status, reason, commit_sha, created_at or _now()
            ))
        else:
            # Update existing record
            # Build update query dynamically for non-None values
            updates = []
            params = []
            if node_id is not None:
                updates.append("node_id = ?")
                params.append(node_id)
            if pr_number is not None:
                updates.append("pr_number = ?")
                params.append(pr_number)
            if merged_at is not None:
                updates.append("merged_at = ?")
                params.append(merged_at)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if reason is not None:
                updates.append("reason = ?")
                params.append(reason)
            if commit_sha is not None:
                updates.append("commit_sha = ?")
                params.append(commit_sha)

            if updates:
                sql = f"UPDATE return_results SET {', '.join(updates)} WHERE id = ?"
                params.append(result_id)
                con.execute(sql, params)
        con.commit()
    finally:
        con.close()
