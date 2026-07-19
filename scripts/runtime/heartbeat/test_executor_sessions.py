"""test_executor_sessions.py — Executor session lifecycle tests.

Covers the executor-neutral session lifecycle added across three commits:
  1. state_recorder CRUD (insert/update/get_active/get_by_id)
  2. reconciler: completed / failed / running / needs_operator handling
  3. idempotent collection (no double-apply on already-evaluated sessions)
  4. heartbeat reconcile-when-no-events (the Phase-0 early-exit fix)
  5. adapter selection (jules action vs jules_cli)

Uses in-memory SQLite for recorder/reconciler tests, a real throwaway git repo
in a temp dir for worktree/patch-application tests, and mocked subprocess-free
adapters (the Jules CLI is never actually invoked).
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from adapters.executor_protocol import (
    DispatchResult as ProtocolDispatchResult,
    PatchResult,
    SessionRef,
    SessionStatus,
)
from adapters.jules_action_adapter import JulesActionAdapter
from adapters.jules_cli_adapter import JulesCliAdapter
from scripts.runtime.heartbeat import reconciler, runner
from scripts.runtime.heartbeat.dispatcher import dispatch
from scripts.runtime.heartbeat.state_recorder import (
    allocate_retry_attempt,
    get_active_executor_sessions,
    get_executor_session_by_id,
    insert_job,
    insert_executor_session,
    update_executor_session_state,
)


# --------------------------------------------------------------------------- #
# Schema + fixtures
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE events (
    event_id   TEXT PRIMARY KEY,
    received_at TEXT,
    source     TEXT,
    event_type TEXT,
    repo       TEXT,
    project_id TEXT,
    status     TEXT DEFAULT 'received',
    claimed_at TEXT
);

CREATE TABLE jobs (
    job_id              TEXT PRIMARY KEY,
    event_id            TEXT,
    created_at          TEXT NOT NULL,
    project_id          TEXT,
    repo                TEXT,
    node_id             TEXT NOT NULL,
    job_type            TEXT NOT NULL,
    executor            TEXT NOT NULL,
    queue_state         TEXT DEFAULT 'ready',
    title               TEXT NOT NULL,
    goal                TEXT NOT NULL,
    why                 TEXT,
    constraints         TEXT,
    acceptance_criteria TEXT,
    priority            TEXT DEFAULT 'medium',
    status              TEXT DEFAULT 'ready',
    attempt             INTEGER DEFAULT 0,
    max_attempts        INTEGER DEFAULT 3,
    artifacts_dir       TEXT,
    required_artifacts  TEXT NOT NULL DEFAULT '[]',
    previous_findings   TEXT
);

CREATE TABLE queue_records (
    queue_item_id TEXT PRIMARY KEY,
    job_id        TEXT NOT NULL,
    queue         TEXT NOT NULL,
    available_at  TEXT NOT NULL
);

CREATE TABLE executor_sessions (
    session_db_id            TEXT PRIMARY KEY,
    job_id                   TEXT NOT NULL,
    executor                 TEXT NOT NULL,
    session_id               TEXT NOT NULL,
    execution_attempt_id     TEXT NOT NULL,
    attempt_index            INTEGER NOT NULL,
    state                    TEXT DEFAULT 'dispatched',
    expected_base_commit_sha TEXT,
    result_commit_sha        TEXT,
    patch_path               TEXT,
    error                    TEXT,
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL
);
"""


def _apply_schema(con):
    con.executescript(_SCHEMA)
    con.commit()


@pytest.fixture
def con():
    """In-memory SQLite with the full heartbeat schema."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    _apply_schema(c)
    yield c
    c.close()


def _insert_job(
    con,
    job_id="job_1",
    executor="jules_cli",
    repo="owner/repo",
    status="running",
    project_id="proj-1",
    node_id="node-1",
    attempt=0,
    max_attempts=3,
    required_artifacts=None,
    previous_findings=None,
):
    """Insert a minimal job + queue record (no event needed; FKs off in tests)."""
    con.execute(
        "INSERT INTO jobs (job_id, created_at, project_id, repo, node_id, "
        "job_type, executor, queue_state, title, goal, status, attempt, "
        "max_attempts, required_artifacts, previous_findings) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job_id, "2026-07-17T00:00:00+00:00", project_id, repo, node_id,
            "implementation", executor, status, "Test", "Test goal", status,
            attempt, max_attempts,
            json.dumps(required_artifacts or []),
            json.dumps(previous_findings) if previous_findings is not None else None,
        ),
    )
    con.execute(
        "INSERT INTO queue_records (queue_item_id, job_id, queue, available_at) "
        "VALUES (?, ?, ?, ?)",
        (f"qi_{job_id}", job_id, status, "2026-07-17T00:00:00+00:00"),
    )
    con.commit()
    return job_id


# --------------------------------------------------------------------------- #
# Fake adapter factory for reconciler tests
# --------------------------------------------------------------------------- #

# A unified diff that adds a single new file. Valid input for `git apply`.
_PATCH_ADD_RESULT = (
    "diff --git a/result.txt b/result.txt\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/result.txt\n"
    "@@ -0,0 +1 @@\n"
    "+executor result\n"
)


def _make_fake_adapter(
    *,
    status_state="completed",
    status_error=None,
    status_exception=None,
    patch_text=_PATCH_ADD_RESULT,
    collect_success=True,
    cancel_result=False,
):
    """Build a configurable fake adapter class.

    The reconciler instantiates ``adapter_cls(repo=...)`` and calls lifecycle
    methods, so call counts live at the class level.
    """

    class FakeAdapter:
        status_calls = 0
        collect_calls = 0
        cancel_calls = 0

        def __init__(self, repo=""):
            self.repo = repo

        def status(self, session_ref):
            FakeAdapter.status_calls += 1
            if status_exception is not None:
                raise status_exception
            return SessionStatus(state=status_state, error=status_error)

        def collect(self, session_ref, dest_path):
            FakeAdapter.collect_calls += 1
            if not collect_success:
                return PatchResult(success=False, error="collect failed (mock)")
            dest_path = Path(dest_path)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(patch_text)
            return PatchResult(
                success=True,
                patch_text=patch_text,
                patch_path=str(dest_path),
            )

        def cancel(self, session_ref):
            FakeAdapter.cancel_calls += 1
            return cancel_result

    return FakeAdapter


def _make_git_repo(parent):
    """Create a real throwaway git repo with one empty commit.

    Returns (repo_path, base_commit_sha). Configures user.name/email so commits
    inside reconciler-created worktrees succeed.
    """
    repo = parent / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo), check=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "initial", "-q"],
        cwd=str(repo), check=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()
    return repo, base


# =========================================================================== #
# 1. State recorder tests
# =========================================================================== #

def test_insert_executor_session_creates_row(con):
    _insert_job(con, job_id="job_a")
    ses_id = insert_executor_session(
        con, "job_a", "jules_cli", "sess-1",
        expected_base_commit_sha="abc123",
    )
    row = get_executor_session_by_id(con, ses_id)
    assert row is not None
    assert row["state"] == "dispatched"
    assert row["executor"] == "jules_cli"
    assert row["session_id"] == "sess-1"
    assert row["job_id"] == "job_a"
    assert row["expected_base_commit_sha"] == "abc123"
    assert row["result_commit_sha"] is None
    assert row["error"] is None
    assert row["attempt_index"] == 0
    assert row["execution_attempt_id"] == "job_a:attempt:0"


def test_update_executor_session_state(con):
    _insert_job(con, job_id="job_b")
    ses_id = insert_executor_session(con, "job_b", "jules_cli", "sess-2")

    update_executor_session_state(
        con, ses_id, state="completed",
        result_commit_sha="def456",
        patch_path="/tmp/x.diff",
        error=None,
    )

    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] == "completed"
    assert row["result_commit_sha"] == "def456"
    assert row["patch_path"] == "/tmp/x.diff"


def test_get_active_executor_sessions(con):
    _insert_job(con, job_id="job_c")
    # dispatched (default on insert)
    s_dispatched = insert_executor_session(con, "job_c", "jules_cli", "sess-d")
    # completed (terminal — must NOT appear)
    s_completed = insert_executor_session(con, "job_c", "jules_cli", "sess-c")
    update_executor_session_state(
        con, s_completed, state="completed", result_commit_sha="sha-c"
    )
    # running (active)
    s_running = insert_executor_session(con, "job_c", "jules_cli", "sess-r")
    update_executor_session_state(con, s_running, state="running")

    active = get_active_executor_sessions(con)
    active_ids = {row["session_db_id"] for row in active}

    assert s_dispatched in active_ids
    assert s_running in active_ids
    assert s_completed not in active_ids
    assert len(active) == 2


def test_get_active_executor_sessions_filters_by_repo(con):
    """Issue #7: cross-repo guard — repo filter isolates sessions by job repo."""
    # Two jobs in different repos.
    _insert_job(con, job_id="job_repo_a", repo="owner/repo-a")
    _insert_job(con, job_id="job_repo_b", repo="owner/repo-b")

    s_a = insert_executor_session(con, "job_repo_a", "jules_cli", "sess-a")
    s_b = insert_executor_session(con, "job_repo_b", "jules_cli", "sess-b")

    # No filter (backward-compatible): both active sessions returned.
    all_active = get_active_executor_sessions(con)
    all_ids = {row["session_db_id"] for row in all_active}
    assert s_a in all_ids
    assert s_b in all_ids

    # Filter by repo-a: only the repo-a session is returned.
    repo_a_active = get_active_executor_sessions(con, repo="owner/repo-a")
    repo_a_ids = {row["session_db_id"] for row in repo_a_active}
    assert s_a in repo_a_ids
    assert s_b not in repo_a_ids
    assert len(repo_a_active) == 1


def test_get_executor_session_by_id(con):
    _insert_job(con, job_id="job_d")
    ses_id = insert_executor_session(
        con, "job_d", "jules_cli", "sess-z",
        expected_base_commit_sha="sha-base",
    )

    row = get_executor_session_by_id(con, ses_id)
    assert row["session_db_id"] == ses_id
    assert row["job_id"] == "job_d"
    assert row["executor"] == "jules_cli"
    assert row["session_id"] == "sess-z"
    assert row["expected_base_commit_sha"] == "sha-base"
    assert row["state"] == "dispatched"


def test_retry_allocation_persists_findings_for_db_replay(con):
    findings = {
        "verdict": "changes_requested",
        "findings": [{"severity": "medium", "summary": "src/a.py:8"}],
    }
    _insert_job(
        con,
        job_id="job_replay",
        required_artifacts=["decision.md", "result-summary.md"],
    )
    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", ("job_replay",)
    ).fetchone()

    allocated = allocate_retry_attempt(
        con,
        job,
        executor="jules_cli",
        previous_findings=findings,
    )
    con.commit()

    assert allocated is not None
    replayed_job = dict(
        con.execute(
            "SELECT * FROM jobs WHERE job_id = ?", ("job_replay",)
        ).fetchone()
    )
    from scripts.runtime.heartbeat.dispatcher import _build_node_packet

    packet = _build_node_packet(replayed_job)
    assert packet.attempt_index == 1
    assert packet.execution_attempt_id == "job_replay:attempt:1"
    assert packet.required_artifacts == ("decision.md", "result-summary.md")
    assert packet.previous_findings["findings"][0]["severity"] == "medium"


def test_init_db_safely_migrates_existing_attempt_rows(tmp_path, monkeypatch):
    from scripts import init_db as init_db_module

    db_path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            attempt INTEGER DEFAULT 0
        );
        CREATE TABLE executor_sessions (
            session_db_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            executor TEXT NOT NULL,
            session_id TEXT NOT NULL,
            state TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO jobs (job_id, attempt) VALUES ('job_old', 1);
        INSERT INTO executor_sessions VALUES
            ('ses_old_0', 'job_old', 'jules_cli', 'remote-0', 'failed',
             '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'),
            ('ses_old_1', 'job_old', 'jules_cli', 'remote-1', 'running',
             '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z');
        """
    )
    legacy.commit()
    legacy.close()
    monkeypatch.setattr(init_db_module, "DB_PATH", db_path)

    init_db_module.init_db()
    init_db_module.init_db()

    migrated = sqlite3.connect(db_path)
    migrated.row_factory = sqlite3.Row
    job_columns = {
        row["name"] for row in migrated.execute("PRAGMA table_info(jobs)")
    }
    session_columns = {
        row["name"]
        for row in migrated.execute("PRAGMA table_info(executor_sessions)")
    }
    assert {"required_artifacts", "previous_findings"} <= job_columns
    assert {"execution_attempt_id", "attempt_index"} <= session_columns
    rows = migrated.execute(
        "SELECT attempt_index, execution_attempt_id "
        "FROM executor_sessions ORDER BY created_at"
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        (0, "job_old:attempt:0"),
        (1, "job_old:attempt:1"),
    ]
    migrated.close()


# =========================================================================== #
# 2. Reconciler tests
# =========================================================================== #

def test_reconcile_no_active_sessions(con, tmp_path, monkeypatch):
    repo, _ = _make_git_repo(tmp_path)
    FakeAdapter = _make_fake_adapter(status_state="completed")
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    # Empty DB — no active sessions.
    result = reconciler.reconcile_sessions(con, repo)

    assert result is None
    assert FakeAdapter.status_calls == 0
    assert FakeAdapter.collect_calls == 0


def test_reconcile_completed_session_collects_and_commits(con, tmp_path, monkeypatch):
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_done", executor="jules_cli",
                repo="owner/repo", status="running")
    ses_id = insert_executor_session(
        con, "job_done", "jules_cli", "sess-done",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(status_state="completed")
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    # The evaluator bridge is mocked: real verification needs config/repo
    # checkouts that the test fixture does not provide.
    monkeypatch.setattr(
        reconciler, "verify_job_return",
        lambda **kw: {"verification_status": "ok", "verdict": "pass"},
    )
    # write_result opens its own connection to the real DB_PATH; the test
    # uses an in-memory DB, so mock it to avoid writing to disk.
    monkeypatch.setattr(
        reconciler, "write_result", lambda **kw: None
    )

    reconciler.reconcile_sessions(con, repo)

    row = get_executor_session_by_id(con, ses_id)
    # collected -> evaluated; result commit pinned.
    assert row["state"] == "evaluated"
    assert row["result_commit_sha"] is not None
    assert len(row["result_commit_sha"]) == 40  # full git SHA
    # patch was applied exactly once.
    assert FakeAdapter.collect_calls == 1

    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = ?", ("job_done",)
    ).fetchone()
    assert job["status"] == "awaiting_review"
    assert job["queue_state"] == "awaiting_review"

    qr = con.execute(
        "SELECT queue FROM queue_records WHERE job_id = ?", ("job_done",)
    ).fetchone()
    assert qr["queue"] == "awaiting_review"


def test_reconcile_failed_session_allocates_one_retry_and_preserves_original(
    con, tmp_path, monkeypatch
):
    repo, base_sha = _make_git_repo(tmp_path)
    findings = {
        "verdict": "changes_requested",
        "findings": [{"severity": "high", "summary": "src/a.py:4 is wrong"}],
    }
    _insert_job(
        con,
        job_id="job_fail",
        executor="jules_cli",
        status="running",
        required_artifacts=["decision.md", "patch.diff"],
        previous_findings=findings,
    )
    original_id = insert_executor_session(
        con,
        "job_fail",
        "jules_cli",
        "sess-fail",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(status_state="failed", status_error="boom")
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})
    dispatched_jobs = []

    def retry_dispatch(job, repo_name):
        dispatched_jobs.append(dict(job))
        return ProtocolDispatchResult(
            success=True,
            session_ref=SessionRef("jules_cli", "sess-retry"),
        )

    monkeypatch.setattr(reconciler, "dispatch", retry_dispatch)

    reconciler.reconcile_sessions(con, repo)

    original = get_executor_session_by_id(con, original_id)
    assert original["state"] == "failed"
    assert original["session_id"] == "sess-fail"
    assert original["attempt_index"] == 0
    assert original["execution_attempt_id"] == "job_fail:attempt:0"
    assert original["error"] == "boom"

    rows = con.execute(
        "SELECT * FROM executor_sessions WHERE job_id = ? ORDER BY attempt_index",
        ("job_fail",),
    ).fetchall()
    assert len(rows) == 2
    replacement = rows[1]
    assert replacement["state"] == "dispatched"
    assert replacement["session_id"] == "sess-retry"
    assert replacement["attempt_index"] == 1
    assert replacement["execution_attempt_id"] == "job_fail:attempt:1"

    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", ("job_fail",)
    ).fetchone()
    assert job["attempt"] == 1
    assert job["status"] == "running"
    assert job["queue_state"] == "running"
    assert len(dispatched_jobs) == 1

    from scripts.runtime.heartbeat.dispatcher import _build_node_packet

    packet = _build_node_packet(dispatched_jobs[0])
    assert packet.execution_attempt_id == "job_fail:attempt:1"
    assert packet.required_artifacts == ("decision.md", "patch.diff")
    assert packet.previous_findings["findings"][0]["severity"] == "high"


def test_retry_dispatch_failure_is_visible_and_idempotent(
    con, tmp_path, monkeypatch
):
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_dispatch_fail", status="running")
    original_id = insert_executor_session(
        con,
        "job_dispatch_fail",
        "jules_cli",
        "sess-original",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(status_state="failed", status_error="remote failed")
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})
    dispatch_calls = []

    def failed_dispatch(job, repo_name):
        dispatch_calls.append(job["attempt"])
        return ProtocolDispatchResult(success=False, error="retry transport failed")

    monkeypatch.setattr(reconciler, "dispatch", failed_dispatch)

    reconciler.reconcile_sessions(con, repo)
    reconciler.reconcile_sessions(con, repo)

    rows = con.execute(
        "SELECT * FROM executor_sessions WHERE job_id = ? ORDER BY attempt_index",
        ("job_dispatch_fail",),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["session_db_id"] == original_id
    assert rows[0]["state"] == "failed"
    assert rows[1]["state"] == "dispatch_failed"
    assert rows[1]["error"] == "retry transport failed"
    assert rows[1]["execution_attempt_id"] == "job_dispatch_fail:attempt:1"
    assert dispatch_calls == [1]

    job = con.execute(
        "SELECT attempt, status, queue_state FROM jobs WHERE job_id = ?",
        ("job_dispatch_fail",),
    ).fetchone()
    assert tuple(job) == (1, "failed", "failed")


def test_reconcile_failed_session_at_attempt_cap_does_not_dispatch(
    con, tmp_path, monkeypatch
):
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(
        con,
        job_id="job_exhausted",
        status="running",
        attempt=3,
        max_attempts=3,
    )
    session_id = insert_executor_session(
        con,
        "job_exhausted",
        "jules_cli",
        "sess-last",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(status_state="failed", status_error="last failure")
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})
    retry_dispatch = MagicMock()
    monkeypatch.setattr(reconciler, "dispatch", retry_dispatch)

    reconciler.reconcile_sessions(con, repo)

    row = get_executor_session_by_id(con, session_id)
    assert row["state"] == "failed"
    assert row["attempt_index"] == 3
    retry_dispatch.assert_not_called()
    assert con.execute(
        "SELECT COUNT(*) FROM executor_sessions WHERE job_id = ?",
        ("job_exhausted",),
    ).fetchone()[0] == 1
    job = con.execute(
        "SELECT attempt, status, queue_state FROM jobs WHERE job_id = ?",
        ("job_exhausted",),
    ).fetchone()
    assert tuple(job) == (3, "failed", "failed")


def test_reconcile_poll_exception_does_not_allocate_replacement(
    con, tmp_path, monkeypatch
):
    repo, _ = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_poll", status="running")
    session_id = insert_executor_session(
        con, "job_poll", "jules_cli", "sess-poll"
    )
    FakeAdapter = _make_fake_adapter(
        status_exception=RuntimeError("temporary network failure")
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})
    retry_dispatch = MagicMock()
    monkeypatch.setattr(reconciler, "dispatch", retry_dispatch)

    reconciler.reconcile_sessions(con, repo)

    assert get_executor_session_by_id(con, session_id)["state"] == "dispatched"
    assert con.execute(
        "SELECT COUNT(*) FROM executor_sessions WHERE job_id = ?", ("job_poll",)
    ).fetchone()[0] == 1
    assert con.execute(
        "SELECT attempt FROM jobs WHERE job_id = ?", ("job_poll",)
    ).fetchone()[0] == 0
    retry_dispatch.assert_not_called()


def test_reconcile_running_session_stays_active(con, tmp_path, monkeypatch):
    repo, _ = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_run", executor="jules_cli", status="running")
    ses_id = insert_executor_session(con, "job_run", "jules_cli", "sess-run")
    FakeAdapter = _make_fake_adapter(status_state="running")
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    reconciler.reconcile_sessions(con, repo)

    row = get_executor_session_by_id(con, ses_id)
    # dispatched -> running; no patch collection yet.
    assert row["state"] == "running"
    assert row["result_commit_sha"] is None
    assert FakeAdapter.collect_calls == 0

    job = con.execute(
        "SELECT status FROM jobs WHERE job_id = ?", ("job_run",)
    ).fetchone()
    assert job["status"] == "running"

    # Still in the active set.
    active = get_active_executor_sessions(con)
    assert any(r["session_db_id"] == ses_id for r in active)


def test_reconcile_needs_operator_persists_state(con, tmp_path, monkeypatch):
    repo, _ = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_op", executor="jules_cli", status="running")
    ses_id = insert_executor_session(con, "job_op", "jules_cli", "sess-op")
    FakeAdapter = _make_fake_adapter(
        status_state="needs_operator", status_error="needs human"
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    reconciler.reconcile_sessions(con, repo)

    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] == "needs_operator"
    assert "needs human" in (row["error"] or "")
    assert FakeAdapter.collect_calls == 0

    # needs_operator is still active (awaiting human), and the job is untouched.
    job = con.execute(
        "SELECT status FROM jobs WHERE job_id = ?", ("job_op",)
    ).fetchone()
    assert job["status"] == "running"
    active = get_active_executor_sessions(con)
    assert any(r["session_db_id"] == ses_id for r in active)
    assert con.execute(
        "SELECT COUNT(*) FROM executor_sessions WHERE job_id = ?", ("job_op",)
    ).fetchone()[0] == 1
    assert con.execute(
        "SELECT attempt FROM jobs WHERE job_id = ?", ("job_op",)
    ).fetchone()[0] == 0


def test_persisted_local_cancellation_is_terminal_across_reconciler_restart(
    con, tmp_path, monkeypatch
):
    repo, _ = _make_git_repo(tmp_path)
    _insert_job(
        con,
        job_id="job_cancel_local",
        executor="local_subprocess",
        status="running",
    )
    session_id = insert_executor_session(
        con,
        "job_cancel_local",
        "local_subprocess",
        "local-session",
    )
    FakeLocal = _make_fake_adapter(status_state="running", cancel_result=True)
    monkeypatch.setattr(reconciler, "ADAPTERS", {"local_subprocess": FakeLocal})

    result = reconciler.cancel_executor_session(con, session_id)

    assert result == "cancelled"
    row = get_executor_session_by_id(con, session_id)
    assert row["state"] == "cancelled"
    assert FakeLocal.cancel_calls == 1
    assert get_active_executor_sessions(con) == []
    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = ?",
        ("job_cancel_local",),
    ).fetchone()
    assert tuple(job) == ("cancelled", "cancelled")

    reconciler.reconcile_sessions(con, repo)
    assert FakeLocal.status_calls == 0
    assert FakeLocal.collect_calls == 0


def test_jules_cancellation_persists_unsupported_without_claiming_remote_success(
    con, monkeypatch
):
    _insert_job(con, job_id="job_cancel_jules", status="running")
    session_id = insert_executor_session(
        con,
        "job_cancel_jules",
        "jules_cli",
        "jules-session",
    )
    FakeJules = _make_fake_adapter(status_state="running", cancel_result=False)
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeJules})

    result = reconciler.cancel_executor_session(con, session_id)

    assert result == "cancel_unsupported"
    row = get_executor_session_by_id(con, session_id)
    assert row["state"] == "cancel_unsupported"
    assert "unsupported" in row["error"].lower()
    assert "cancelled" not in row["error"].lower()
    assert get_active_executor_sessions(con) == []
    assert con.execute(
        "SELECT status FROM jobs WHERE job_id = ?", ("job_cancel_jules",)
    ).fetchone()[0] == "cancelled"


# =========================================================================== #
# 3. Idempotency — a session already collected must not be re-applied
# =========================================================================== #

def test_reconcile_idempotent_no_double_apply(con, tmp_path, monkeypatch):
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(
        con, job_id="job_idem", executor="jules_cli", status="awaiting_review"
    )
    ses_id = insert_executor_session(
        con, "job_idem", "jules_cli", "sess-idem",
        expected_base_commit_sha=base_sha,
    )
    # Simulate a session that already went through collect+evaluate.
    update_executor_session_state(
        con, ses_id, state="evaluated", result_commit_sha="existing_sha_123",
    )
    FakeAdapter = _make_fake_adapter(status_state="completed")
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    reconciler.reconcile_sessions(con, repo)

    # 'evaluated' is terminal for the active-session query, so the adapter is
    # never consulted and no new commit can be created.
    assert FakeAdapter.status_calls == 0
    assert FakeAdapter.collect_calls == 0
    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] == "evaluated"
    assert row["result_commit_sha"] == "existing_sha_123"


# =========================================================================== #
# 4. Heartbeat must run reconcile even when there are no new intake events
#    (the Phase-0 early-exit fix)
# =========================================================================== #

def test_heartbeat_reconciles_even_without_new_events(tmp_path, monkeypatch):
    # File DB: runner.connect() enables WAL, which requires a real file.
    db_path = tmp_path / "queue.db"
    init_con = sqlite3.connect(str(db_path))
    _apply_schema(init_con)
    init_con.close()

    monkeypatch.setattr(runner, "DB_PATH", db_path)

    # No real graph/config needed: ready nodes are empty so planning is a no-op.
    mock_reader = MagicMock()
    mock_reader.get_ready_nodes.return_value = []
    monkeypatch.setattr(runner, "GraphReader", lambda **kw: mock_reader)

    called = {"reconcile": False}

    def fake_reconcile(c, repo_path, repo=None):
        called["reconcile"] = True

    monkeypatch.setattr(runner, "reconcile_sessions", fake_reconcile)

    # Empty events table — previously this would skip reconcile entirely.
    runner.run_heartbeat(
        project_id="proj-1",
        repo="owner/repo",
        config_path=str(tmp_path / "no-config"),
    )

    assert called["reconcile"] is True


def test_runner_persists_initial_attempt_before_dispatch(con, monkeypatch):
    con.execute(
        """INSERT INTO events
           (event_id, received_at, source, event_type, repo, project_id, status)
           VALUES ('evt_initial', '2026-01-01T00:00:00Z', 'manual',
                   'issue.opened', 'owner/repo', 'proj-1', 'received')"""
    )
    con.commit()
    node = SimpleNamespace(node_id="node-1")
    monkeypatch.setattr(
        runner,
        "classify",
        lambda event, nodes: {
            "matched_node_id": "node-1",
            "executor_recommendation": "jules_cli",
        },
    )
    monkeypatch.setattr(runner, "mark_event_classified", lambda *args: None)
    monkeypatch.setattr(runner, "check_scope", lambda *args: True)
    monkeypatch.setattr(
        runner,
        "build_job",
        lambda *args: {
            "job_id": "job_initial",
            "created_at": "2026-01-01T00:00:00Z",
            "event_id": "evt_initial",
            "project_id": "proj-1",
            "repo": "owner/repo",
            "node_id": "node-1",
            "job_type": "implementation",
            "executor": "jules_cli",
            "queue_state": "ready",
            "title": "Initial",
            "goal": "Dispatch once",
            "why": "",
            "constraints": "[]",
            "acceptance_criteria": "[]",
            "priority": "medium",
            "status": "ready",
            "attempt": 0,
            "max_attempts": 3,
            "artifacts_dir": "/tmp/job_initial/",
            "required_artifacts": '["decision.md"]',
            "previous_findings": None,
        },
    )

    planned = runner._plan_dispatches(
        con,
        "proj-1",
        "owner/repo",
        [node],
        SimpleNamespace(),
    )

    assert len(planned) == 1
    assert planned[0].session_db_id
    row = con.execute(
        "SELECT * FROM executor_sessions WHERE job_id = 'job_initial'"
    ).fetchone()
    assert row["state"] == "dispatching"
    assert row["attempt_index"] == 0
    assert row["execution_attempt_id"] == "job_initial:attempt:0"
    persisted_job = con.execute(
        "SELECT required_artifacts FROM jobs WHERE job_id = 'job_initial'"
    ).fetchone()
    assert json.loads(persisted_job["required_artifacts"]) == ["decision.md"]


# =========================================================================== #
# 5. Adapter selection — executor field routes to the correct adapter
# =========================================================================== #

def _sample_job(job_id="job_x", executor="jules_cli"):
    return {
        "job_id": job_id,
        "node_id": "node-1",
        "title": "Test task",
        "goal": "Do the thing",
        "why": "Because",
        "constraints": "[]",
        "acceptance_criteria": "[]",
        "executor": executor,
        "attempt": 0,
    }


def test_dispatcher_selects_jules_cli_adapter(monkeypatch):
    job = _sample_job(executor="jules_cli")

    cli_dispatch = MagicMock(
        return_value=ProtocolDispatchResult(
            success=True,
            session_ref=SessionRef(
                executor="jules_cli", session_id="1234567890123456"
            ),
        )
    )
    monkeypatch.setattr(JulesCliAdapter, "dispatch", cli_dispatch)
    # Guard: the action adapter must not be selected.
    action_dispatch = MagicMock()
    monkeypatch.setattr(JulesActionAdapter, "dispatch", action_dispatch)

    result = dispatch(job, "owner/repo")

    cli_dispatch.assert_called_once()
    action_dispatch.assert_not_called()
    assert result.success is True
    assert result.session_ref is not None
    assert result.session_ref.executor == "jules_cli"
    assert result.session_ref.session_id == "1234567890123456"


def test_dispatcher_selects_jules_action_adapter(monkeypatch):
    job = _sample_job(executor="jules")

    action_dispatch = MagicMock(
        return_value=ProtocolDispatchResult(
            success=True,
            issue_url="https://github.com/owner/repo/issues/1",
        )
    )
    monkeypatch.setattr(JulesActionAdapter, "dispatch", action_dispatch)
    # Guard: the CLI adapter must not be selected.
    cli_dispatch = MagicMock()
    monkeypatch.setattr(JulesCliAdapter, "dispatch", cli_dispatch)

    result = dispatch(job, "owner/repo")

    action_dispatch.assert_called_once()
    cli_dispatch.assert_not_called()
    assert result.success is True
    assert result.issue_url == "https://github.com/owner/repo/issues/1"
    # Action adapter path produces no durable session_ref.
    assert result.session_ref is None


# =========================================================================== #
# 6. Issue #4 — "Awaiting User Feedback" parses as needs_operator
# =========================================================================== #

def test_jules_cli_status_awaiting_maps_to_needs_operator(monkeypatch):
    """Live Jules output shows "Awaiting User F" (truncated). It must not fall
    through to running; it means the executor is blocked on a human."""
    import adapters.jules_cli_adapter as jca
    from types import SimpleNamespace

    session_id = "16944924106855934613"
    list_output = (
        f"{session_id}\tUpdate old...\tskchaudr/saboorkc.dev\t"
        "6 days ago\tAwaiting User F\n"
    )

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=list_output, stderr="")

    monkeypatch.setattr(jca.subprocess, "run", fake_run)

    adapter = JulesCliAdapter(repo="skchaudr/saboorkc.dev")
    status = adapter.status(
        SessionRef(executor="jules_cli", session_id=session_id)
    )
    assert status.state == "needs_operator"


def test_jules_cli_status_unknown_keyword_still_running(monkeypatch):
    """Regression guard: an unrecognized keyword that is not "awaiting" still
    falls through to running (the original fail-safe behaviour)."""
    import adapters.jules_cli_adapter as jca
    from types import SimpleNamespace

    session_id = "16944924106855934614"
    list_output = f"{session_id}\tsome task\towner/repo\t1 day ago\tIn Review\n"

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=list_output, stderr="")

    monkeypatch.setattr(jca.subprocess, "run", fake_run)

    adapter = JulesCliAdapter(repo="owner/repo")
    status = adapter.status(
        SessionRef(executor="jules_cli", session_id=session_id)
    )
    assert status.state == "running"


# =========================================================================== #
# 7. Issue #6 — GDDP_EXECUTOR_OVERRIDE reroutes dispatch without graph changes
# =========================================================================== #

def test_dispatcher_executor_override_env_var(monkeypatch):
    """A job carrying executor: jules is rerouted to jules_cli when
    GDDP_EXECUTOR_OVERRIDE is set, so the canary can test the CLI path
    without mutating the human-owned graph."""
    job = _sample_job(executor="jules")
    monkeypatch.setenv("GDDP_EXECUTOR_OVERRIDE", "jules_cli")

    cli_dispatch = MagicMock(
        return_value=ProtocolDispatchResult(
            success=True,
            session_ref=SessionRef(
                executor="jules_cli", session_id="1234567890123456"
            ),
        )
    )
    monkeypatch.setattr(JulesCliAdapter, "dispatch", cli_dispatch)
    # Guard: the action adapter must not be selected despite executor: jules.
    action_dispatch = MagicMock()
    monkeypatch.setattr(JulesActionAdapter, "dispatch", action_dispatch)

    result = dispatch(job, "owner/repo")

    cli_dispatch.assert_called_once()
    action_dispatch.assert_not_called()
    assert result.success is True
    assert result.session_ref is not None
    assert result.session_ref.executor == "jules_cli"


def test_dispatcher_executor_override_unset_uses_job_executor(monkeypatch):
    """Without the override env var, executor: jules still routes to the
    action adapter (the override is opt-in only)."""
    job = _sample_job(executor="jules")
    monkeypatch.delenv("GDDP_EXECUTOR_OVERRIDE", raising=False)

    action_dispatch = MagicMock(
        return_value=ProtocolDispatchResult(
            success=True,
            issue_url="https://github.com/owner/repo/issues/2",
        )
    )
    monkeypatch.setattr(JulesActionAdapter, "dispatch", action_dispatch)
    cli_dispatch = MagicMock()
    monkeypatch.setattr(JulesCliAdapter, "dispatch", cli_dispatch)

    result = dispatch(job, "owner/repo")

    action_dispatch.assert_called_once()
    cli_dispatch.assert_not_called()
    assert result.success is True
