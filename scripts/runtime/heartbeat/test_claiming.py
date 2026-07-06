"""Tests for X2 hardening: event claiming and the awaiting_review dispatch guard."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from scripts.runtime.heartbeat.scope_checker import check_scope


class _Node:
    node_id = "node-a"
    depends_on = []


def _mem_con() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE jobs (job_id TEXT, node_id TEXT, status TEXT)")
    con.execute(
        "CREATE TABLE events (event_id TEXT PRIMARY KEY, project_id TEXT,"
        " status TEXT, claimed_at TEXT)"
    )
    return con


class TestAwaitingReviewGuard:
    @pytest.mark.parametrize("status", ["ready", "running", "awaiting_review"])
    def test_active_job_blocks_dispatch(self, status):
        con = _mem_con()
        con.execute("INSERT INTO jobs VALUES ('job_1', 'node-a', ?)", (status,))
        result = check_scope(_Node(), "proj", con, graph_reader=None)
        assert not result
        assert "job_1" in result.reason

    def test_terminal_job_does_not_block(self):
        con = _mem_con()
        con.execute("INSERT INTO jobs VALUES ('job_1', 'node-a', 'done')")
        result = check_scope(_Node(), "proj", con, graph_reader=None)
        assert result


class TestEventClaiming:
    """The claim UPDATE in runner._plan_dispatches: exercised at SQL level."""

    CLAIM_SQL = """
        UPDATE events
           SET status = 'claimed', claimed_at = ?
         WHERE event_id = ?
           AND (status = 'received'
                OR (status = 'claimed' AND claimed_at < ?))
    """

    def _claim(self, con, event_id, now=None, cutoff=None):
        now = now or datetime.now(timezone.utc).isoformat()
        cutoff = cutoff or (
            datetime.now(timezone.utc) - timedelta(minutes=30)
        ).isoformat()
        cur = con.execute(self.CLAIM_SQL, (now, event_id, cutoff))
        con.commit()
        return cur.rowcount

    def test_first_claim_wins_second_loses(self):
        con = _mem_con()
        con.execute("INSERT INTO events VALUES ('evt_1', 'proj', 'received', NULL)")
        assert self._claim(con, "evt_1") == 1
        assert self._claim(con, "evt_1") == 0  # concurrent runner loses

    def test_stale_claim_is_reclaimable(self):
        con = _mem_con()
        stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        con.execute(
            "INSERT INTO events VALUES ('evt_1', 'proj', 'claimed', ?)", (stale,)
        )
        assert self._claim(con, "evt_1") == 1

    def test_fresh_claim_is_not_reclaimable(self):
        con = _mem_con()
        fresh = datetime.now(timezone.utc).isoformat()
        con.execute(
            "INSERT INTO events VALUES ('evt_1', 'proj', 'claimed', ?)", (fresh,)
        )
        assert self._claim(con, "evt_1") == 0
