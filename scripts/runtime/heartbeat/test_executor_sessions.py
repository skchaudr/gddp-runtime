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

import sqlite3
import subprocess
import sys
from pathlib import Path
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
from adapters.jules_action_adapter import DispatchResult as ActionDispatchResult
from adapters.jules_action_adapter import JulesActionAdapter
from adapters.jules_cli_adapter import JulesCliAdapter
from scripts.runtime.heartbeat import reconciler, runner
from scripts.runtime.heartbeat.dispatcher import dispatch
from scripts.runtime.heartbeat.state_recorder import (
    get_active_executor_sessions,
    get_executor_session_by_id,
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
    artifacts_dir       TEXT
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
):
    """Insert a minimal job + queue record (no event needed; FKs off in tests)."""
    con.execute(
        "INSERT INTO jobs (job_id, created_at, project_id, repo, node_id, "
        "job_type, executor, queue_state, title, goal, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job_id, "2026-07-17T00:00:00+00:00", project_id, repo, node_id,
            "implementation", executor, status, "Test", "Test goal", status,
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
    patch_text=_PATCH_ADD_RESULT,
    collect_success=True,
):
    """Build a configurable fake adapter class.

    The reconciler instantiates ``adapter_cls(repo=...)`` and calls
    ``.status()`` / ``.collect()``, so we track call counts at the class level.
    """

    class FakeAdapter:
        status_calls = 0
        collect_calls = 0

        def __init__(self, repo=""):
            self.repo = repo

        def status(self, session_ref):
            FakeAdapter.status_calls += 1
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
            return False

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


def test_reconcile_failed_session_marks_job_failed(con, tmp_path, monkeypatch):
    repo, _ = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_fail", executor="jules_cli", status="running")
    ses_id = insert_executor_session(con, "job_fail", "jules_cli", "sess-fail")
    FakeAdapter = _make_fake_adapter(status_state="failed", status_error="boom")
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    reconciler.reconcile_sessions(con, repo)

    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] == "failed"
    assert "boom" in (row["error"] or "")
    assert FakeAdapter.collect_calls == 0

    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = ?", ("job_fail",)
    ).fetchone()
    assert job["status"] == "failed"
    assert job["queue_state"] == "failed"


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

    def fake_reconcile(c, repo_path):
        called["reconcile"] = True

    monkeypatch.setattr(runner, "reconcile_sessions", fake_reconcile)

    # Empty events table — previously this would skip reconcile entirely.
    runner.run_heartbeat(
        project_id="proj-1",
        repo="owner/repo",
        config_path=str(tmp_path / "no-config"),
    )

    assert called["reconcile"] is True


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
        return_value=ActionDispatchResult(
            success=True,
            issue_url="https://github.com/owner/repo/issues/1",
            issue_number=1,
            error=None,
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
        return_value=ActionDispatchResult(
            success=True,
            issue_url="https://github.com/owner/repo/issues/2",
            issue_number=2,
            error=None,
        )
    )
    monkeypatch.setattr(JulesActionAdapter, "dispatch", action_dispatch)
    cli_dispatch = MagicMock()
    monkeypatch.setattr(JulesCliAdapter, "dispatch", cli_dispatch)

    result = dispatch(job, "owner/repo")

    action_dispatch.assert_called_once()
    cli_dispatch.assert_not_called()
    assert result.success is True
