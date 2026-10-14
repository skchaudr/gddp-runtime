import sqlite3
import threading
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import MagicMock, patch

import sys
import os
from pathlib import Path
from runtime.heartbeat import runner
from init_db import init_db

class MockNode:
    def __init__(self, **kwargs):
        self.node_id = kwargs.get("node_id")
        self.title = kwargs.get("title", "test")
        self.type = kwargs.get("type", "capability")
        self.why = kwargs.get("why", "test")
        self.acceptance_criteria = kwargs.get("acceptance_criteria", [])
        self.status = kwargs.get("status", "ready")
        self.constraints = kwargs.get("constraints", [])
        self.priority = kwargs.get("priority", "medium")
        self.required_artifacts = kwargs.get("required_artifacts", [])
        self.__dict__.update(kwargs)
    
    def get(self, key, default=None):
        return self.__dict__.get(key, default)

def test_no_double_processing_with_concurrent_runs(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    
    with patch('init_db.DB_PATH', db_path):
        init_db()

    con = sqlite3.connect(db_path)
    
    con.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, "
        "repo, project_id, status) VALUES "
        "('evt_atomic', '2026-07-29T09:00:00Z', 'manual', 'issue.opened', "
        "'owner/a', 'proj-a', 'received')"
    )
    con.commit()
    con.close()

    monkeypatch.setattr(runner, "DB_PATH", db_path)
    monkeypatch.setattr(runner, "RUNTIME_ROOT", tmp_path)
    
    node = MockNode(node_id="node-1")
    
    monkeypatch.setattr(runner, "classify", lambda event, nodes: {
        "matched_node_id": "node-1",
        "executor_recommendation": "local_subprocess"
    })
    monkeypatch.setattr(runner, "executor_preflight_error", lambda a, b, c=None: None)
    monkeypatch.setattr(runner, "check_scope", lambda a, b, c, d: MagicMock(reason=None))
    
    results = []
    
    def run_plan():
        con = runner.connect()
        try:
            res = runner._plan_dispatches(con, "proj-a", "owner/a", [node], MagicMock())
            results.extend(res)
        finally:
            con.close()
        
    t1 = threading.Thread(target=run_plan)
    t2 = threading.Thread(target=run_plan)
    t3 = threading.Thread(target=run_plan)
    
    t1.start()
    t2.start()
    t3.start()
    
    t1.join()
    t2.join()
    t3.join()
    
    assert len(results) == 1
    
def test_stale_claim_is_reclaimed_and_processed(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    with patch('init_db.DB_PATH', db_path):
        init_db()
    con = sqlite3.connect(db_path)
    
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    
    con.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, "
        "repo, project_id, status, claimed_at) VALUES "
        "('evt_stale', '2026-07-29T09:00:00Z', 'manual', 'issue.opened', "
        "'owner/a', 'proj-a', 'claimed', ?)",
        (stale_time,)
    )
    con.commit()
    con.close()

    monkeypatch.setattr(runner, "DB_PATH", db_path)
    monkeypatch.setattr(runner, "RUNTIME_ROOT", tmp_path)
    
    node = MockNode(node_id="node-1")
    monkeypatch.setattr(runner, "classify", lambda event, nodes: {
        "matched_node_id": "node-1",
        "executor_recommendation": "local_subprocess"
    })
    monkeypatch.setattr(runner, "executor_preflight_error", lambda a, b, c=None: None)
    monkeypatch.setattr(runner, "check_scope", lambda a, b, c, d: MagicMock(reason=None))

    con = runner.connect()
    res = runner._plan_dispatches(con, "proj-a", "owner/a", [node], MagicMock())
    
    assert len(res) == 1
    assert res[0].event_id == 'evt_stale'

