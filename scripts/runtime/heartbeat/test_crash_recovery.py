import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from unittest.mock import MagicMock
import sys

from scripts.runtime.heartbeat import runner
sys.path.insert(0, str(Path(".").resolve()))
from scripts.init_db import init_db

class FakeNode:
    node_id = "test-node"
    depends_on = []
    title = "Test Node"
    why = "Because tests"
    constraints = ["None"]
    acceptance_criteria = ["Works"]
    priority = "high"
    required_artifacts = ["patch.diff"]

class TestCrashRecovery:
    @pytest.fixture
    def test_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "queue.db"
        monkeypatch.setattr("scripts.init_db.DB_PATH", str(db_path))
        init_db()
        return db_path

    def test_stale_claim_recovery_processed_by_heartbeat(self, test_db, monkeypatch):
        con = sqlite3.connect(test_db)
        con.row_factory = sqlite3.Row
        
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
        
        con.execute(
            "INSERT INTO events (event_id, received_at, source, event_type, project_id, status, claimed_at, repo) "
            "VALUES (?, ?, 'github', 'issue.opened', 'test-project', 'claimed', ?, 'owner/repo')",
            ("evt_stale", "2024-03-20T09:00:00Z", stale_time)
        )
        con.commit()

        mock_classify = MagicMock(return_value={
            "category": "implementation_request",
            "intent": "implement_existing_node",
            "in_scope": True,
            "matched_node_id": "test-node",
            "executor_recommendation": "jules",
            "requires_code_execution": True,
            "requires_human_review": False,
        })
        monkeypatch.setattr(runner, "classify", mock_classify)
        
        class ScopeResult:
            def __bool__(self): return True
            @property
            def reason(self): return ""
            @property
            def _dict(self): return {}
        mock_check_scope = MagicMock(return_value=ScopeResult())
        monkeypatch.setattr(runner, "check_scope", mock_check_scope)

        planned = runner._plan_dispatches(con, "test-project", "owner/repo", [FakeNode()], None)

        assert len(planned) == 1
        
        row = con.execute("SELECT status, claimed_at FROM events WHERE event_id = 'evt_stale'").fetchone()
        assert row["status"] in ("mapped", "classified")
        assert row["claimed_at"] > stale_time
        con.close()

    def test_concurrent_heartbeats_no_double_processing(self, test_db, monkeypatch):
        con1 = sqlite3.connect(test_db, timeout=10)
        con1.execute(
            "INSERT INTO events (event_id, received_at, source, event_type, project_id, status, repo) "
            "VALUES (?, ?, 'github', 'issue.opened', 'test-project', 'received', 'owner/repo')",
            ("evt_concurrent", "2024-03-20T09:00:00Z")
        )
        con1.commit()
        con1.close()

        mock_classify = MagicMock(return_value={
            "category": "implementation_request",
            "intent": "implement_existing_node",
            "in_scope": True,
            "matched_node_id": "test-node",
            "executor_recommendation": "jules",
            "requires_code_execution": True,
            "requires_human_review": False,
        })
        monkeypatch.setattr(runner, "classify", mock_classify)
            
        class ScopeResult:
            def __bool__(self): return True
            @property
            def reason(self): return ""
            @property
            def _dict(self): return {}
        mock_check_scope = MagicMock(return_value=ScopeResult())
        monkeypatch.setattr(runner, "check_scope", mock_check_scope)

        barrier = threading.Barrier(2)
        results = []

        def run_plan():
            con = sqlite3.connect(test_db, timeout=10)
            con.row_factory = sqlite3.Row
            barrier.wait()
            try:
                # Need isolated cursor and transaction for concurrent execution to test atomic claim
                planned = runner._plan_dispatches(con, "test-project", "owner/repo", [FakeNode()], None)
                results.append(planned)
            except Exception as e:
                print(e)
                results.append([])
            finally:
                con.close()

        t1 = threading.Thread(target=run_plan)
        t2 = threading.Thread(target=run_plan)
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        total_planned = sum(len(p) for p in results)
        assert total_planned == 1
