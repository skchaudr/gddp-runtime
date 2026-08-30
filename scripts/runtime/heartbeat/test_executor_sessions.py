"""test_executor_sessions.py — Executor session lifecycle tests.

Covers the executor-neutral session lifecycle added across three commits:
  1. state_recorder CRUD (insert/update/get_active/get_by_id)
  2. reconciler: completed / failed / running / needs_operator handling
  3. idempotent collection (no double-apply on already-evaluated sessions)
  4. heartbeat reconcile-when-no-events (the Phase-0 early-exit fix)
  5. adapter selection (jules action vs jules_api)

Uses in-memory SQLite for recorder/reconciler tests, a real throwaway git repo
in a temp dir for worktree/patch-application tests, and mocked subprocess-free
adapters (the Jules CLI is never actually invoked).
"""

import hashlib
import json
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
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
from adapters.jules_api_adapter import JulesApiAdapter
from scripts.runtime.heartbeat import dispatcher, reconciler, runner
from scripts.runtime.heartbeat.dispatcher import dispatch
from scripts.runtime.heartbeat.state_recorder import (
    allocate_retry_attempt,
    finalize_executor_session_dispatch,
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
    plumbing_attempt    INTEGER NOT NULL DEFAULT 0,
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
    result_commit_sha=None,
    result_ref=None,
    base_commit_sha=None,
):
    """Build a configurable fake adapter class.

    The reconciler instantiates ``adapter_cls(repo=...)`` and calls lifecycle
    methods, so call counts live at the class level.
    """

    class FakeAdapter:
        status_calls = 0
        collect_calls = 0
        cancel_calls = 0
        cancelled_session_ids = []

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
            if result_commit_sha:
                payload = json.dumps(
                    {
                        "schema": "gddp.local_result.v1",
                        "result_commit_sha": result_commit_sha,
                        "result_ref": result_ref,
                    }
                )
                dest_path.write_text(payload)
                return PatchResult(
                    success=True,
                    patch_path=str(dest_path),
                    result_commit_sha=result_commit_sha,
                    result_ref=result_ref,
                )
            dest_path.write_text(patch_text)
            return PatchResult(
                success=True,
                patch_text=patch_text,
                patch_path=str(dest_path),
                base_commit_sha=base_commit_sha,
            )

        def cancel(self, session_ref):
            FakeAdapter.cancelled_session_ids.append(session_ref.session_id)
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
        expected_base_commit_sha="abc123",
        previous_findings=findings,
    )
    con.commit()

    assert allocated is not None
    assert allocated[0]["expected_base_commit_sha"] == "abc123"
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


def _insert_collected_evaluation(con, index, *, session_id):
    job_id = f"job_eval_{index}"
    _insert_job(
        con,
        job_id=job_id,
        executor="local_subprocess",
        status="running",
        node_id=f"node-{index}",
    )
    session_db_id = insert_executor_session(
        con,
        job_id,
        "local_subprocess",
        session_id,
        expected_base_commit_sha="a" * 40,
    )
    update_executor_session_state(
        con,
        session_db_id,
        state="collected",
        result_commit_sha=f"{index + 1:040x}",
    )
    con.commit()
    return job_id, session_db_id


def test_evaluators_overlap_with_bounded_capacity_and_distinct_results(
    con, tmp_path, monkeypatch
):
    session_prefix = "same-session-id-"  # 16 characters: old IDs collided.
    sessions = [
        _insert_collected_evaluation(
            con,
            index,
            session_id=f"{session_prefix}{index}",
        )
        for index in range(3)
    ]
    monkeypatch.setattr(
        reconciler,
        "ADAPTERS",
        {"local_subprocess": object},
    )

    lock = threading.Lock()
    active = 0
    peak = 0

    def fake_verify(**kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.1)
        with lock:
            active -= 1
        return {"verification_status": "ok", "verdict": "pass"}

    writes = []
    coordinator_thread = threading.get_ident()
    monkeypatch.setattr(reconciler, "verify_job_return", fake_verify)
    monkeypatch.setattr(
        reconciler,
        "write_result",
        lambda **kwargs: writes.append(
            (kwargs, threading.get_ident())
        ),
    )

    reconciler.reconcile_sessions(
        con,
        tmp_path,
        max_concurrent_evaluations=2,
    )

    assert peak == 2
    assert len(writes) == 3
    assert len({item[0]["result_id"] for item in writes}) == 3
    assert {item[0]["job_id"] for item in writes} == {
        job_id for job_id, _ in sessions
    }
    assert {thread_id for _, thread_id in writes} == {coordinator_thread}
    for job_id, session_db_id in sessions:
        assert get_executor_session_by_id(con, session_db_id)["state"] == "evaluated"
        job = con.execute(
            "SELECT status FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        assert job["status"] == "awaiting_review"


def test_evaluator_failure_isolated_from_peer(con, tmp_path, monkeypatch):
    successful = _insert_collected_evaluation(
        con,
        10,
        session_id="success-session",
    )
    failing = _insert_collected_evaluation(
        con,
        11,
        session_id="failure-session",
    )
    monkeypatch.setattr(
        reconciler,
        "ADAPTERS",
        {"local_subprocess": object},
    )

    def fake_verify(**kwargs):
        if kwargs["job_id"] == failing[0]:
            raise RuntimeError("intentional evaluator failure")
        return {"verification_status": "ok", "verdict": "pass"}

    writes = []
    monkeypatch.setattr(reconciler, "verify_job_return", fake_verify)
    monkeypatch.setattr(
        reconciler,
        "write_result",
        lambda **kwargs: writes.append(kwargs),
    )

    reconciler.reconcile_sessions(
        con,
        tmp_path,
        max_concurrent_evaluations=2,
    )

    outcomes = {item["job_id"]: item["outcome"] for item in writes}
    assert outcomes == {
        successful[0]: "pass",
        failing[0]: "error",
    }
    for job_id, session_db_id in (successful, failing):
        assert get_executor_session_by_id(con, session_db_id)["state"] == "evaluated"
        status = con.execute(
            "SELECT status FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()["status"]
        assert status == "awaiting_review"


def test_evaluator_finalization_failure_leaves_only_that_session_collected(
    con, tmp_path, monkeypatch
):
    successful = _insert_collected_evaluation(
        con,
        12,
        session_id="finalize-success",
    )
    failing = _insert_collected_evaluation(
        con,
        13,
        session_id="finalize-failure",
    )
    monkeypatch.setattr(
        reconciler,
        "ADAPTERS",
        {"local_subprocess": object},
    )
    monkeypatch.setattr(
        reconciler,
        "verify_job_return",
        lambda **kwargs: {"verification_status": "ok", "verdict": "pass"},
    )
    monkeypatch.setattr(reconciler, "write_result", lambda **kwargs: None)
    real_finalize = reconciler._finalize_evaluation

    def fail_one_finalize(connection, pending, verification, **kwargs):
        if pending.job_id == failing[0]:
            raise sqlite3.OperationalError("intentional finalization failure")
        real_finalize(connection, pending, verification, **kwargs)

    monkeypatch.setattr(
        reconciler,
        "_finalize_evaluation",
        fail_one_finalize,
    )

    reconciler.reconcile_sessions(
        con,
        tmp_path,
        max_concurrent_evaluations=2,
    )

    assert get_executor_session_by_id(con, successful[1])["state"] == "evaluated"
    assert get_executor_session_by_id(con, failing[1])["state"] == "collected"
    statuses = dict(
        con.execute(
            "SELECT job_id, status FROM jobs WHERE job_id IN (?, ?)",
            (successful[0], failing[0]),
        ).fetchall()
    )
    assert statuses == {
        successful[0]: "awaiting_review",
        failing[0]: "running",
    }


def test_external_evaluation_batch_defers_finalization(
    con, tmp_path, monkeypatch
):
    job_id, session_db_id = _insert_collected_evaluation(
        con,
        20,
        session_id="deferred-session",
    )
    monkeypatch.setattr(
        reconciler,
        "ADAPTERS",
        {"local_subprocess": object},
    )
    release = threading.Event()
    started = threading.Event()

    def fake_verify(**kwargs):
        started.set()
        assert release.wait(timeout=2)
        return {"verification_status": "ok", "verdict": "pass"}

    monkeypatch.setattr(reconciler, "verify_job_return", fake_verify)
    monkeypatch.setattr(reconciler, "write_result", lambda **kwargs: None)

    batch = reconciler.EvaluationBatch(max_workers=1)
    reconciler.reconcile_sessions(
        con,
        tmp_path,
        evaluation_batch=batch,
    )

    assert started.wait(timeout=1)
    assert get_executor_session_by_id(con, session_db_id)["state"] == "collected"
    assert con.execute(
        "SELECT status FROM jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()["status"] == "running"

    release.set()
    batch.finalize(con)

    assert get_executor_session_by_id(con, session_db_id)["state"] == "evaluated"
    assert con.execute(
        "SELECT status FROM jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()["status"] == "awaiting_review"


def test_mission_session_provenance_reaches_evaluator(
    con, tmp_path, monkeypatch,
):
    for name in (
        "completion_id",
        "completion_digest_sha256",
        "completion_quarantine_reason",
        "evidence_manifest_path",
    ):
        con.execute(f"ALTER TABLE executor_sessions ADD COLUMN {name} TEXT")
    _insert_job(
        con,
        job_id="job_mission_eval",
        executor="factory_mission",
        status="running",
        node_id="mission-node",
    )
    session_db_id = insert_executor_session(
        con,
        "job_mission_eval",
        "factory_mission",
        "engagement-1",
        expected_base_commit_sha="a" * 40,
    )
    manifest = tmp_path / "mission-node.json"
    manifest.write_bytes(b'{"feature_id":"mission-node"}\n')
    expected_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    con.execute(
        """
        UPDATE executor_sessions
           SET state = 'collected',
               result_commit_sha = ?,
               completion_id = ?,
               evidence_manifest_path = ?
         WHERE session_db_id = ?
        """,
        (
            "b" * 40,
            "mis_1:mission-node:worker-1",
            str(manifest),
            session_db_id,
        ),
    )
    con.commit()
    monkeypatch.setattr(
        reconciler,
        "ADAPTERS",
        {"factory_mission": object},
    )
    calls = []
    monkeypatch.setattr(
        reconciler,
        "verify_job_return",
        lambda **kwargs: calls.append(kwargs)
        or {"verification_status": "ok", "verdict": "pass"},
    )
    monkeypatch.setattr(reconciler, "write_result", lambda **_kwargs: None)
    monkeypatch.setattr(
        reconciler,
        "maybe_mark_provisional",
        lambda **_kwargs: False,
    )

    reconciler.reconcile_sessions(con, tmp_path)

    assert len(calls) == 1
    assert calls[0]["execution_attempt_id"] == "job_mission_eval:attempt:0"
    assert calls[0]["evidence_manifest_sha256"] == expected_digest
    assert (
        calls[0]["mission_receipt_id"]
        == "mis_1:mission-node:worker-1"
    )


def test_reconcile_evaluates_remote_patch_built_on_another_base(
    con, tmp_path, monkeypatch
):
    """A base difference must never stop the evaluator from rendering a verdict.

    This previously asserted the opposite — that evaluation "must not run on
    base mismatch." That behavior discarded three nodes of real returned work
    unread on 2026-07-29, on a commit-hash comparison, before a single
    acceptance criterion was read. Refusing to evaluate returned work is
    evidence suppression. Base differences are an integration concern; only an
    unretrievable result may prevent evaluation.
    """
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(
        con,
        job_id="job_other_base",
        executor="jules_api",
        repo="owner/repo",
        status="running",
    )
    ses_id = insert_executor_session(
        con,
        "job_other_base",
        "jules_api",
        "session-other-base",
        expected_base_commit_sha="f" * 40,
    )
    FakeAdapter = _make_fake_adapter(
        status_state="completed",
        base_commit_sha=base_sha,
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_api": FakeAdapter})

    evaluated = []

    def fake_verify(**kwargs):
        evaluated.append(kwargs)
        return {"verification_status": "ok", "verdict": "pass"}

    monkeypatch.setattr(reconciler, "verify_job_return", fake_verify)
    monkeypatch.setattr(reconciler, "write_result", lambda **kw: None)

    reconciler.reconcile_sessions(con, repo)

    assert evaluated, "evaluator must run even when the base differs"
    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] != "failed"


def test_reconcile_local_commit_ref_skips_apply_worktree(con, tmp_path, monkeypatch):
    repo, base_sha = _make_git_repo(tmp_path)
    # Create a real descendant commit for the commit-ref path.
    (repo / "result.txt").write_text("from local agent\n")
    subprocess.run(["git", "add", "result.txt"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "agent result", "-q"], cwd=str(repo), check=True
    )
    result_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()
    # The executor's durable attempt ref: the reconciler resolves it and
    # requires it to agree with the reported SHA.
    subprocess.run(
        ["git", "branch", "gddp/attempt-job_local", result_sha],
        cwd=str(repo), check=True, capture_output=True,
    )

    _insert_job(
        con, job_id="job_local", executor="local_subprocess",
        repo="owner/repo", status="running",
    )
    ses_id = insert_executor_session(
        con, "job_local", "local_subprocess", "sess-local",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(
        status_state="completed",
        result_commit_sha=result_sha,
        result_ref=f"gddp/attempt-job_local",
    )
    monkeypatch.setattr(
        reconciler, "ADAPTERS", {"local_subprocess": FakeAdapter}
    )
    monkeypatch.setattr(
        reconciler, "verify_job_return",
        lambda **kw: {"verification_status": "ok", "verdict": "pass"},
    )
    monkeypatch.setattr(reconciler, "write_result", lambda **kw: None)

    create_calls = []
    apply_calls = []
    monkeypatch.setattr(
        reconciler,
        "_create_exec_worktree",
        lambda *a, **k: create_calls.append((a, k)) or (_ for _ in ()).throw(
            AssertionError("worktree must not be created on commit-ref path")
        ),
    )
    monkeypatch.setattr(
        reconciler,
        "_apply_and_commit",
        lambda *a, **k: apply_calls.append((a, k)) or (None, "should not run"),
    )

    reconciler.reconcile_sessions(con, repo)

    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] == "evaluated"
    assert row["result_commit_sha"] == result_sha
    assert FakeAdapter.collect_calls == 1
    assert create_calls == []
    assert apply_calls == []
    # Durable reconciler ref adopted.
    ref = subprocess.run(
        ["git", "rev-parse", "gddp/result-job_local-sess-local"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert ref == result_sha

    job = con.execute(
        "SELECT status FROM jobs WHERE job_id = ?", ("job_local",)
    ).fetchone()
    assert job["status"] == "awaiting_review"


def test_reconcile_rejects_ref_not_descending_from_base(con, tmp_path, monkeypatch):
    repo, base_sha = _make_git_repo(tmp_path)
    # Unrelated orphan commit (not descending from base).
    orphan_repo = tmp_path / "orphan"
    orphan_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(orphan_repo), check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(orphan_repo), check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(orphan_repo), check=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "orphan", "-q"],
        cwd=str(orphan_repo), check=True,
    )
    orphan_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(orphan_repo), capture_output=True, text=True, check=True,
    ).stdout.strip()
    # Fetch the orphan object into the main repo without linking ancestry.
    subprocess.run(
        ["git", "fetch", str(orphan_repo), "HEAD:refs/heads/orphan-tmp"],
        cwd=str(repo), capture_output=True, check=True,
    )

    _insert_job(
        con, job_id="job_bad", executor="local_subprocess",
        status="running",
    )
    ses_id = insert_executor_session(
        con, "job_bad", "local_subprocess", "sess-bad",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(
        status_state="completed",
        result_commit_sha=orphan_sha,
        # Ref resolves correctly; the ancestry check is what must reject it.
        result_ref="orphan-tmp",
    )
    monkeypatch.setattr(
        reconciler, "ADAPTERS", {"local_subprocess": FakeAdapter}
    )
    monkeypatch.setattr(
        reconciler, "verify_job_return",
        lambda **kw: {"verification_status": "ok", "verdict": "pass"},
    )
    monkeypatch.setattr(reconciler, "write_result", lambda **kw: None)

    reconciler.reconcile_sessions(con, repo)

    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] == "failed"
    assert "does not descend" in (row["error"] or "")
    job = con.execute(
        "SELECT status FROM jobs WHERE job_id = ?", ("job_bad",)
    ).fetchone()
    assert job["status"] == "failed"


def test_reconcile_rejects_ref_that_does_not_resolve_to_reported_sha(
    con, tmp_path, monkeypatch
):
    """The ref is the durability guarantee; a SHA it does not point at is not
    durable evidence, even when the SHA itself descends from the base."""
    repo, base_sha = _make_git_repo(tmp_path)
    # Two real descendant commits; the ref is left pointing at the first.
    (repo / "result.txt").write_text("first\n")
    subprocess.run(["git", "add", "result.txt"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "first result", "-q"], cwd=str(repo), check=True
    )
    stale_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "branch", "gddp/attempt-job_drift", stale_sha],
        cwd=str(repo), check=True, capture_output=True,
    )
    (repo / "result.txt").write_text("second\n")
    subprocess.run(["git", "add", "result.txt"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "second result", "-q"], cwd=str(repo), check=True
    )
    reported_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()

    _insert_job(
        con, job_id="job_drift", executor="local_subprocess",
        repo="owner/repo", status="running",
    )
    ses_id = insert_executor_session(
        con, "job_drift", "local_subprocess", "sess-drift",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(
        status_state="completed",
        result_commit_sha=reported_sha,
        result_ref="gddp/attempt-job_drift",
    )
    monkeypatch.setattr(
        reconciler, "ADAPTERS", {"local_subprocess": FakeAdapter}
    )
    monkeypatch.setattr(
        reconciler, "verify_job_return",
        lambda **kw: pytest.fail("evaluation must not run on ref mismatch"),
    )
    monkeypatch.setattr(reconciler, "write_result", lambda **kw: None)

    reconciler.reconcile_sessions(con, repo)

    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] == "failed"
    assert "gddp/attempt-job_drift" in (row["error"] or "")
    assert row["result_commit_sha"] is None
    job = con.execute(
        "SELECT status FROM jobs WHERE job_id = ?", ("job_drift",)
    ).fetchone()
    assert job["status"] == "failed"


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

    def retry_dispatch(job, repo_name, repo_path=None):
        assert repo_path == str(repo)
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


def test_auth_blocked_failure_parks_without_consuming_retry_budget(
    con, tmp_path, monkeypatch
):
    """A revoked-credential failure parks the session needs_operator, keeps
    the job running (scope still blocks duplicates), and allocates no retry
    — unattended, the node waits instead of exhausting against a dead wall."""
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_auth", executor="jules_cli", status="running")
    session_db_id = insert_executor_session(
        con,
        "job_auth",
        "jules_cli",
        "sess-auth",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(
        status_state="failed",
        status_error=(
            "local subprocess exited with code 1: xAI token refresh failed: "
            '400 {"error":"invalid_grant","error_description":"Refresh token '
            'has been revoked"}'
        ),
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    def forbidden_dispatch(job, repo_name, repo_path=None):
        raise AssertionError("auth-blocked failure must not redispatch")

    monkeypatch.setattr(reconciler, "dispatch", forbidden_dispatch)

    reconciler.reconcile_sessions(con, repo)

    parked = get_executor_session_by_id(con, session_db_id)
    assert parked["state"] == "needs_operator"
    assert "invalid_grant" in parked["error"]

    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", ("job_auth",)
    ).fetchone()
    assert job["status"] == "running"
    assert job["attempt"] == 0
    rows = con.execute(
        "SELECT * FROM executor_sessions WHERE job_id = ?", ("job_auth",)
    ).fetchall()
    assert len(rows) == 1  # no replacement session allocated

    # Second tick: the adapter still reports the dead session failed, but the
    # parked session stays put — quiet, idempotent, no retry burn.
    reconciler.reconcile_sessions(con, repo)
    parked = get_executor_session_by_id(con, session_db_id)
    assert parked["state"] == "needs_operator"
    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", ("job_auth",)
    ).fetchone()
    assert job["status"] == "running"
    assert job["attempt"] == 0


def test_classify_executor_failure_patterns():
    assert (
        reconciler.classify_executor_failure("xAI token refresh failed: 400 "
                                             "invalid_grant")
        == "auth_blocked"
    )
    assert (
        reconciler.classify_executor_failure("Please run /login and select Grok CLI")
        == "auth_blocked"
    )
    assert reconciler.classify_executor_failure("boom") == "retryable"
    assert reconciler.classify_executor_failure(None) == "retryable"
    assert (
        reconciler.classify_executor_failure("git apply failed: corrupt patch")
        == "retryable"
    )


def test_reconcile_reviewed_jobs_drains_only_terminal_graph_states(con):
    """Accepted/deferred nodes leave the review queue; everything else stays.
    Graph 'ready' is not reconciled — it cannot distinguish a rejected
    provisional from a node the human simply has not reviewed yet."""
    from scripts.runtime.heartbeat.state_recorder import reconcile_reviewed_jobs

    _insert_job(con, job_id="job_acc", node_id="node-a", status="awaiting_review")
    _insert_job(con, job_id="job_def", node_id="node-b", status="awaiting_review")
    _insert_job(con, job_id="job_wait", node_id="node-c", status="awaiting_review")
    _insert_job(con, job_id="job_run", node_id="node-d", status="running")

    reconciled = reconcile_reviewed_jobs(
        con,
        "proj-1",
        {
            "node-a": "complete",
            "node-b": "deferred",
            "node-c": "ready",
            "node-d": "complete",
        },
    )

    assert sorted(reconciled) == [
        ("job_acc", "node-a", "accepted"),
        ("job_def", "node-b", "deferred"),
    ]
    states = {
        row["job_id"]: (row["status"], row["queue_state"])
        for row in con.execute("SELECT job_id, status, queue_state FROM jobs")
    }
    assert states["job_acc"] == ("accepted", "accepted")
    assert states["job_def"] == ("deferred", "deferred")
    assert states["job_wait"] == ("awaiting_review", "awaiting_review")
    assert states["job_run"] == ("running", "running")
    queues = {
        row["job_id"]: row["queue"]
        for row in con.execute("SELECT job_id, queue FROM queue_records")
    }
    assert queues["job_acc"] == "accepted"
    assert queues["job_wait"] == "awaiting_review"

    # Idempotent: a second pass finds nothing left to drain.
    assert reconcile_reviewed_jobs(con, "proj-1", {"node-a": "complete"}) == []


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

    def failed_dispatch(job, repo_name, repo_path=None):
        assert repo_path == str(repo)
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


def test_plumbing_deaths_use_own_budget_and_never_consume_work_attempts(
    con, tmp_path, monkeypatch
):
    """Policy 2026-08-05: 3 work attempts + 3 plumbing retries, independent.
    A session that dies before durable exit state is infra noise — the job's
    work-attempt counter must not move, and the plumbing counter caps at 3."""
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(
        con,
        job_id="job_plumbing",
        status="running",
        attempt=0,
        max_attempts=3,
    )
    insert_executor_session(
        con,
        "job_plumbing",
        "jules_cli",
        "sess-p0",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(
        status_state="failed",
        status_error="local subprocess exited without durable exit state",
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})
    dispatched = []

    def ok_dispatch(job, repo_name, repo_path=None):
        dispatched.append(dict(job))
        return ProtocolDispatchResult(
            success=True,
            session_ref=SessionRef("jules_cli", f"sess-r{len(dispatched)}"),
        )

    monkeypatch.setattr(reconciler, "dispatch", ok_dispatch)

    # Deaths 1-3: each redispatches on the plumbing budget; attempt stays 0.
    for _ in range(3):
        reconciler.reconcile_sessions(con, repo)
        job = con.execute(
            "SELECT attempt, plumbing_attempt, status FROM jobs"
            " WHERE job_id = 'job_plumbing'"
        ).fetchone()
        assert tuple(job) == (0, job["plumbing_attempt"], "running")

    assert len(dispatched) == 3
    rows = con.execute(
        "SELECT session_id, execution_attempt_id, attempt_index, state"
        " FROM executor_sessions"
        " WHERE job_id = 'job_plumbing' ORDER BY created_at"
    ).fetchall()
    assert len(rows) == 4  # original + 3 plumbing replacements
    for row in rows[1:]:
        # Plumbing replacements re-attempt the same work attempt: the
        # execution_attempt_id is identical, the plumbing counter is the
        # durable discrimination.
        assert row["execution_attempt_id"] == "job_plumbing:attempt:0"
        assert row["attempt_index"] == 0

    # Death 4: plumbing budget exhausted -> terminal, no dispatch.
    reconciler.reconcile_sessions(con, repo)
    assert len(dispatched) == 3
    job = con.execute(
        "SELECT attempt, plumbing_attempt, status, queue_state FROM jobs"
        " WHERE job_id = 'job_plumbing'"
    ).fetchone()
    assert tuple(job) == (0, 3, "failed", "failed")


def test_work_failure_consumes_attempt_not_plumbing_budget(
    con, tmp_path, monkeypatch
):
    """A durable nonzero exit is an executor-completed failure: it consumes
    the work-attempt budget and leaves the plumbing counter untouched."""
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(
        con,
        job_id="job_workfail",
        status="running",
        attempt=0,
        max_attempts=3,
    )
    insert_executor_session(
        con,
        "job_workfail",
        "jules_cli",
        "sess-w0",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(
        status_state="failed",
        status_error="local subprocess exited with code 1: boom",
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    def ok_dispatch(job, repo_name, repo_path=None):
        return ProtocolDispatchResult(
            success=True, session_ref=SessionRef("jules_cli", "sess-w1")
        )

    monkeypatch.setattr(reconciler, "dispatch", ok_dispatch)

    reconciler.reconcile_sessions(con, repo)

    job = con.execute(
        "SELECT attempt, plumbing_attempt, status FROM jobs"
        " WHERE job_id = 'job_workfail'"
    ).fetchone()
    assert tuple(job) == (1, 0, "running")
    rows = con.execute(
        "SELECT attempt_index FROM executor_sessions"
        " WHERE job_id = 'job_workfail' ORDER BY created_at"
    ).fetchall()
    assert [r["attempt_index"] for r in rows] == [0, 1]


def test_classify_plumbing_failure_patterns():
    from runtime.local_attempt import LocalAttemptStatus

    assert reconciler.classify_plumbing_failure(
        LocalAttemptStatus(
            state="failed",
            error="provider initialization failed",
            plumbing=True,
        )
    )
    assert not reconciler.classify_plumbing_failure(
        LocalAttemptStatus(
            state="failed",
            error="exited without durable exit state",
            plumbing=False,
        )
    )
    # Compatibility for transports awaiting local_attempt adoption.
    assert reconciler.classify_plumbing_failure(
        "local subprocess exited without durable exit state"
    )
    assert reconciler.classify_plumbing_failure(
        "invalid local subprocess exit state: Expecting value"
    )
    assert not reconciler.classify_plumbing_failure(
        "local subprocess exited with code 1: boom"
    )
    assert not reconciler.classify_plumbing_failure(None)


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


def test_reconcile_jules_poll_timeout_does_not_allocate_replacement(
    con, tmp_path, monkeypatch
):
    repo, _ = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_poll_timeout", status="running")
    session_id = insert_executor_session(
        con, "job_poll_timeout", "jules_cli", "sess-poll-timeout"
    )

    class FakeAdapter:
        def __init__(self, repo=""):
            pass

        def status(self, session_ref):
            return SessionStatus(state="poll_error", error="jules list timed out after 30s")

    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})
    retry_dispatch = MagicMock()
    monkeypatch.setattr(reconciler, "dispatch", retry_dispatch)

    reconciler.reconcile_sessions(con, repo)

    assert get_executor_session_by_id(con, session_id)["state"] == "dispatched"
    assert con.execute(
        "SELECT COUNT(*) FROM executor_sessions WHERE job_id = ?",
        ("job_poll_timeout",),
    ).fetchone()[0] == 1
    assert con.execute(
        "SELECT attempt FROM jobs WHERE job_id = ?", ("job_poll_timeout",)
    ).fetchone()[0] == 0
    retry_dispatch.assert_not_called()



def test_reconcile_fresh_missing_session_stays_active(
    con, tmp_path, monkeypatch
):
    repo, _ = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_missing_fresh", status="running")
    session_id = insert_executor_session(
        con, "job_missing_fresh", "jules_cli", "missing-fresh"
    )
    con.execute(
        "UPDATE executor_sessions SET created_at = ?, updated_at = ? "
        "WHERE session_db_id = ?",
        (
            "2026-07-18T11:50:00+00:00",
            "2026-07-18T11:50:00+00:00",
            session_id,
        ),
    )
    con.commit()
    FakeAdapter = _make_fake_adapter(
        status_state="missing",
        status_error="session not found in successful jules list",
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})
    retry_dispatch = MagicMock()
    monkeypatch.setattr(reconciler, "dispatch", retry_dispatch)

    reconciler.reconcile_sessions(
        con,
        repo,
        current_time=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        missing_stale_after=timedelta(minutes=30),
    )

    assert get_executor_session_by_id(con, session_id)["state"] == "dispatched"
    job = con.execute(
        "SELECT attempt, status FROM jobs WHERE job_id = ?",
        ("job_missing_fresh",),
    ).fetchone()
    assert tuple(job) == (0, "running")
    retry_dispatch.assert_not_called()


def test_reconcile_aged_missing_session_retries_below_cap(
    con, tmp_path, monkeypatch
):
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_missing_retry", status="running")
    session_id = insert_executor_session(
        con,
        "job_missing_retry",
        "jules_cli",
        "missing-stale",
        expected_base_commit_sha=base_sha,
    )
    con.execute(
        "UPDATE executor_sessions SET created_at = ?, updated_at = ? "
        "WHERE session_db_id = ?",
        (
            "2026-07-18T11:29:00+00:00",
            "2026-07-18T11:29:00+00:00",
            session_id,
        ),
    )
    con.commit()
    FakeAdapter = _make_fake_adapter(
        status_state="missing",
        status_error="session not found in successful jules list",
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})
    retry_dispatch = MagicMock(
        return_value=ProtocolDispatchResult(
            success=True,
            session_ref=SessionRef("jules_cli", "replacement-session"),
        )
    )
    monkeypatch.setattr(reconciler, "dispatch", retry_dispatch)

    reconciler.reconcile_sessions(
        con,
        repo,
        current_time=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        missing_stale_after=timedelta(minutes=30),
    )

    stale = get_executor_session_by_id(con, session_id)
    assert stale["state"] == "failed"
    assert "not found" in stale["error"]
    replacement = con.execute(
        "SELECT state, session_id, attempt_index FROM executor_sessions "
        "WHERE job_id = ? AND attempt_index = 1",
        ("job_missing_retry",),
    ).fetchone()
    assert tuple(replacement) == ("dispatched", "replacement-session", 1)
    job = con.execute(
        "SELECT attempt, status FROM jobs WHERE job_id = ?",
        ("job_missing_retry",),
    ).fetchone()
    assert tuple(job) == (1, "running")


def test_reconcile_aged_missing_session_stops_at_attempt_cap(
    con, tmp_path, monkeypatch
):
    repo, _ = _make_git_repo(tmp_path)
    _insert_job(
        con,
        job_id="job_missing_exhausted",
        status="running",
        attempt=3,
        max_attempts=3,
    )
    session_id = insert_executor_session(
        con,
        "job_missing_exhausted",
        "jules_cli",
        "missing-exhausted",
        attempt_index=3,
    )
    con.execute(
        "UPDATE executor_sessions SET created_at = ?, updated_at = ? "
        "WHERE session_db_id = ?",
        (
            "2026-07-18T11:29:00+00:00",
            "2026-07-18T11:29:00+00:00",
            session_id,
        ),
    )
    con.commit()
    FakeAdapter = _make_fake_adapter(
        status_state="missing",
        status_error="session not found in successful jules list",
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})
    retry_dispatch = MagicMock()
    monkeypatch.setattr(reconciler, "dispatch", retry_dispatch)

    reconciler.reconcile_sessions(
        con,
        repo,
        current_time=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        missing_stale_after=timedelta(minutes=30),
    )

    assert get_executor_session_by_id(con, session_id)["state"] == "failed"
    job = con.execute(
        "SELECT attempt, status FROM jobs WHERE job_id = ?",
        ("job_missing_exhausted",),
    ).fetchone()
    assert tuple(job) == (3, "failed")
    assert con.execute(
        "SELECT COUNT(*) FROM executor_sessions WHERE job_id = ?",
        ("job_missing_exhausted",),
    ).fetchone()[0] == 1
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

def test_restart_recovery_terminalizes_stale_dispatch_without_redispatch(
    con, tmp_path, monkeypatch
):
    repo_path, _ = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_stale_dispatch", status="ready")
    session_id = insert_executor_session(
        con,
        "job_stale_dispatch",
        "jules_cli",
        "job_stale_dispatch:attempt:0",
        state="dispatching",
    )
    con.execute(
        "UPDATE executor_sessions SET updated_at = ? WHERE session_db_id = ?",
        ("2026-07-18T10:00:00+00:00", session_id),
    )
    con.commit()
    retry_dispatch = MagicMock()
    monkeypatch.setattr(reconciler, "dispatch", retry_dispatch)

    reconciler.reconcile_sessions(
        con,
        repo_path,
        repo="owner/repo",
        current_time=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        dispatching_stale_after=timedelta(minutes=30),
    )

    session = get_executor_session_by_id(con, session_id)
    assert session["state"] == "dispatch_failed"
    assert "outcome unknown" in session["error"]
    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = ?",
        ("job_stale_dispatch",),
    ).fetchone()
    assert tuple(job) == ("failed", "failed")
    assert con.execute(
        "SELECT queue FROM queue_records WHERE job_id = ?",
        ("job_stale_dispatch",),
    ).fetchone()[0] == "failed"
    retry_dispatch.assert_not_called()


def test_restart_recovery_leaves_fresh_dispatch_untouched(con, tmp_path):
    repo_path, _ = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_fresh_dispatch", status="ready")
    session_id = insert_executor_session(
        con,
        "job_fresh_dispatch",
        "jules_cli",
        "job_fresh_dispatch:attempt:0",
        state="dispatching",
    )
    con.execute(
        "UPDATE executor_sessions SET updated_at = ? WHERE session_db_id = ?",
        ("2026-07-18T11:45:00+00:00", session_id),
    )
    con.commit()

    reconciler.reconcile_sessions(
        con,
        repo_path,
        repo="owner/repo",
        current_time=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        dispatching_stale_after=timedelta(minutes=30),
    )

    assert get_executor_session_by_id(con, session_id)["state"] == "dispatching"
    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = ?",
        ("job_fresh_dispatch",),
    ).fetchone()
    assert tuple(job) == ("ready", "ready")



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


def test_refused_remote_cancellation_persists_without_claiming_remote_success(
    con, monkeypatch
):
    """A remote executor that refuses cancellation must not be recorded as
    cancelled. The session closes as cancel_failed and the job still reads
    cancelled locally — the remote may keep running, and we say so."""
    _insert_job(con, job_id="job_cancel_jules", status="running")
    session_id = insert_executor_session(
        con,
        "job_cancel_jules",
        "jules_api",
        "jules-session",
    )
    FakeJules = _make_fake_adapter(status_state="running", cancel_result=False)
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_api": FakeJules})

    result = reconciler.cancel_executor_session(con, session_id)

    assert result == "cancel_failed"
    row = get_executor_session_by_id(con, session_id)
    assert row["state"] == "cancel_failed"
    assert "not accepted" in row["error"].lower()
    assert "cancelled" not in row["error"].lower()
    assert get_active_executor_sessions(con) == []
    assert con.execute(
        "SELECT status FROM jobs WHERE job_id = ?", ("job_cancel_jules",)
    ).fetchone()[0] == "cancelled"


def test_dispatch_finalization_loses_to_cancellation_and_cancels_late_session(
    con, monkeypatch, capsys
):
    con.execute(
        "INSERT INTO events "
        "(event_id, received_at, source, event_type, repo, project_id, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "evt_cancel_race",
            "2026-07-18T12:00:00+00:00",
            "github",
            "issues",
            "owner/repo",
            "proj-1",
            "classified",
        ),
    )
    _insert_job(con, job_id="job_cancel_race", status="ready")
    session_db_id = insert_executor_session(
        con,
        "job_cancel_race",
        "jules_cli",
        "job_cancel_race:attempt:0",
        state="dispatching",
    )
    update_executor_session_state(
        con,
        session_db_id,
        state="cancel_unsupported",
        error="Jules CLI cancellation is unsupported",
    )
    con.execute(
        "UPDATE jobs SET status = 'cancelled', queue_state = 'cancelled' "
        "WHERE job_id = ?",
        ("job_cancel_race",),
    )
    con.execute(
        "UPDATE queue_records SET queue = 'cancelled' WHERE job_id = ?",
        ("job_cancel_race",),
    )
    con.commit()

    from scripts.runtime.heartbeat import dispatcher as heartbeat_dispatcher

    FakeJules = _make_fake_adapter(cancel_result=False)
    monkeypatch.setattr(
        heartbeat_dispatcher, "ADAPTERS", {"jules_cli": FakeJules}
    )
    planned = runner.PlannedDispatch(
        event_id="evt_cancel_race",
        classification={"executor_recommendation": "jules_cli"},
        job={
            "job_id": "job_cancel_race",
            "node_id": "node-1",
            "repo": "owner/repo",
        },
        session_db_id=session_db_id,
    )
    outcome = runner.DispatchOutcome(
        planned=planned,
        success=True,
        session_ref=SessionRef("jules_cli", "late-remote-session"),
    )

    runner._record_outcomes(
        con,
        [planned],
        {"job_cancel_race": outcome},
    )

    session = get_executor_session_by_id(con, session_db_id)
    assert session["state"] == "cancel_unsupported"
    assert session["session_id"] == "job_cancel_race:attempt:0"
    job = con.execute(
        "SELECT status, queue_state FROM jobs WHERE job_id = ?",
        ("job_cancel_race",),
    ).fetchone()
    assert tuple(job) == ("cancelled", "cancelled")
    assert con.execute(
        "SELECT queue FROM queue_records WHERE job_id = ?",
        ("job_cancel_race",),
    ).fetchone()[0] == "cancelled"
    assert FakeJules.cancelled_session_ids == ["late-remote-session"]
    assert con.execute(
        "SELECT status FROM events WHERE event_id = ?",
        ("evt_cancel_race",),
    ).fetchone()[0] == "mapped"
    assert runner._plan_dispatches(
        con,
        "proj-1",
        "owner/repo",
        [],
        MagicMock(),
    ) == []
    output = capsys.readouterr().out.lower()
    # The durable invariant: a refused cancellation must be reported as such
    # and must warn the remote may still be running. It must never read as
    # success.
    assert "not accepted" in output
    assert "remote may continue" in output
    assert "cancellation accepted" not in output


def test_dispatch_failure_closes_event_and_preserves_failed_job(con, capsys):
    con.execute(
        "INSERT INTO events "
        "(event_id, received_at, source, event_type, repo, project_id, status) "
        "VALUES ('evt_dispatch_failure', '2026-07-29T09:00:00Z', 'manual', "
        "'issue.opened', 'owner/repo', 'proj-1', 'classified')"
    )
    _insert_job(con, job_id="job_dispatch_failure", status="ready")
    session_db_id = insert_executor_session(
        con,
        "job_dispatch_failure",
        "local_subprocess",
        "job_dispatch_failure:attempt:0",
        state="dispatching",
    )
    planned = runner.PlannedDispatch(
        event_id="evt_dispatch_failure",
        classification={"executor_recommendation": "local_subprocess"},
        job={
            "job_id": "job_dispatch_failure",
            "node_id": "node-1",
            "repo": "owner/repo",
        },
        session_db_id=session_db_id,
    )
    outcome = runner.DispatchOutcome(
        planned=planned,
        success=False,
        error="worker launch failed",
    )

    runner._record_outcomes(
        con,
        [planned],
        {"job_dispatch_failure": outcome},
    )

    assert con.execute(
        "SELECT status FROM events WHERE event_id = 'evt_dispatch_failure'"
    ).fetchone()[0] == "mapped"
    assert con.execute(
        "SELECT status FROM jobs WHERE job_id = 'job_dispatch_failure'"
    ).fetchone()[0] == "failed"
    assert "dispatch this node again through gddp" in capsys.readouterr().out


def test_finalize_executor_session_dispatch_is_compare_and_swap(con):
    _insert_job(con, job_id="job_finalize_cas", status="cancelled")
    session_db_id = insert_executor_session(
        con,
        "job_finalize_cas",
        "jules_cli",
        "job_finalize_cas:attempt:0",
        state="dispatching",
    )
    update_executor_session_state(
        con,
        session_db_id,
        state="cancel_unsupported",
        error="cancelled while dispatch was in flight",
    )

    finalized = finalize_executor_session_dispatch(
        con,
        session_db_id,
        state="dispatched",
        session_id="late-remote-session",
    )

    assert finalized is False
    session = get_executor_session_by_id(con, session_db_id)
    assert session["state"] == "cancel_unsupported"
    assert session["session_id"] == "job_finalize_cas:attempt:0"


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
    mock_reader.load_project.return_value.execution_policy = {}
    mock_reader.get_ready_nodes.return_value = []
    monkeypatch.setattr(runner, "GraphReader", lambda **kw: mock_reader)

    order = []

    class FakeEvaluationBatch:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def finalize(self, c, **kwargs):
            order.append("finalize")

    def fake_reconcile(c, repo_path, repo=None, evaluation_batch=None):
        assert isinstance(evaluation_batch, FakeEvaluationBatch)
        assert evaluation_batch.max_workers == 2
        order.append("reconcile")

    monkeypatch.setattr(runner, "EvaluationBatch", FakeEvaluationBatch)
    monkeypatch.setattr(runner, "reconcile_sessions", fake_reconcile)
    monkeypatch.setattr(
        runner,
        "_plan_dispatches",
        lambda *args, **kwargs: order.append("plan") or [],
    )

    # Empty events table — previously this would skip reconcile entirely.
    runner.run_heartbeat(
        project_id="proj-1",
        repo="owner/repo",
        config_path=str(tmp_path / "no-config"),
    )

    assert order == ["reconcile", "plan", "finalize"]


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
            "executor_recommendation": "jules_api",
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
            "executor": "jules_api",
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
        expected_base_commit_sha="abc123",
    )

    assert len(planned) == 1
    assert planned[0].session_db_id
    row = con.execute(
        "SELECT * FROM executor_sessions WHERE job_id = 'job_initial'"
    ).fetchone()
    assert row["state"] == "dispatching"
    assert row["attempt_index"] == 0
    assert row["execution_attempt_id"] == "job_initial:attempt:0"
    assert row["expected_base_commit_sha"] == "abc123"
    assert planned[0].job["expected_base_commit_sha"] == "abc123"
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


def test_dispatcher_selects_jules_action_adapter(monkeypatch):
    job = _sample_job(executor="jules")

    action_dispatch = MagicMock(
        return_value=ProtocolDispatchResult(
            success=True,
            issue_url="https://github.com/owner/repo/issues/1",
        )
    )
    monkeypatch.setattr(JulesActionAdapter, "dispatch", action_dispatch)
    # Guard: the API adapter must not be selected.
    api_dispatch = MagicMock()
    monkeypatch.setattr(JulesApiAdapter, "dispatch", api_dispatch)

    result = dispatch(job, "owner/repo")

    action_dispatch.assert_called_once()
    api_dispatch.assert_not_called()
    assert result.success is True
    assert result.issue_url == "https://github.com/owner/repo/issues/1"
    # Action adapter path produces no durable session_ref.
    assert result.session_ref is None


def test_dispatcher_runs_local_executor_in_target_checkout(monkeypatch, tmp_path):
    target_repo = tmp_path / "MyAPI"
    target_repo.mkdir()
    observed = {}

    class RecordingLocalAdapter:
        def __init__(self, repo, *, cwd=None):
            observed["repo"] = repo
            observed["cwd"] = cwd

        def attempt_root(self):
            return tmp_path

        def dispatch(self, packet, *, attempt, continuity):
            return ProtocolDispatchResult(
                success=True,
                session_ref=SessionRef(
                    executor="local_subprocess", session_id="local-session"
                ),
            )

    monkeypatch.setitem(
        dispatcher.ADAPTERS, "local_subprocess", RecordingLocalAdapter
    )

    result = dispatcher.dispatch(
        _sample_job(executor="local_subprocess"),
        "owner/MyAPI",
        repo_path=str(target_repo),
    )

    assert result.success is True
    assert observed == {
        "repo": "owner/MyAPI",
        "cwd": str(target_repo),
    }


# =========================================================================== #
# 6. Issue #4 — "Awaiting User Feedback" parses as needs_operator
# =========================================================================== #

def test_dispatcher_executor_override_env_var(monkeypatch):
    """A job carrying executor: jules is rerouted to jules_api when
    GDDP_EXECUTOR_OVERRIDE is set, so the canary can test the API path
    without mutating the human-owned graph."""
    job = _sample_job(executor="jules")
    monkeypatch.setenv("GDDP_EXECUTOR_OVERRIDE", "jules_api")

    api_dispatch = MagicMock(
        return_value=ProtocolDispatchResult(
            success=True,
            session_ref=SessionRef(
                executor="jules_api", session_id="1234567890123456"
            ),
        )
    )
    monkeypatch.setattr(JulesApiAdapter, "dispatch", api_dispatch)
    # Guard: the action adapter must not be selected despite executor: jules.
    action_dispatch = MagicMock()
    monkeypatch.setattr(JulesActionAdapter, "dispatch", action_dispatch)

    result = dispatch(job, "owner/repo")

    api_dispatch.assert_called_once()
    action_dispatch.assert_not_called()
    assert result.success is True
    assert result.session_ref is not None
    assert result.session_ref.executor == "jules_api"


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
    api_dispatch = MagicMock()
    monkeypatch.setattr(JulesApiAdapter, "dispatch", api_dispatch)

    result = dispatch(job, "owner/repo")

    action_dispatch.assert_called_once()
    api_dispatch.assert_not_called()
    assert result.success is True


class _ScriptedReplyAdapter:
    """Fake adapter with a scripted status sequence and a recording reply().

    The reconciler instantiates ``adapter_cls(repo=...)`` per tick, so the
    script and counters live at class level.
    """

    script = []
    reply_calls = 0
    reply_messages = []

    def __init__(self, repo=""):
        self.repo = repo

    def status(self, session_ref):
        state = type(self).script.pop(0) if type(self).script else "running"
        return SessionStatus(state=state)

    def reply(self, session_ref, message):
        type(self).reply_calls += 1
        type(self).reply_messages.append(message)
        return True


def _reset_scripted_adapter(script):
    _ScriptedReplyAdapter.script = list(script)
    _ScriptedReplyAdapter.reply_calls = 0
    _ScriptedReplyAdapter.reply_messages = []
    return _ScriptedReplyAdapter


def test_awaiting_reply_answered_once_then_escalates(con, tmp_path, monkeypatch):
    """Parked session gets one standing reply; still parked next tick -> human."""
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_park", executor="jules_cli",
                repo="owner/repo", status="running")
    ses_id = insert_executor_session(
        con, "job_park", "jules_cli", "sess-park",
        expected_base_commit_sha=base_sha,
    )
    update_executor_session_state(con, ses_id, state="running")
    con.commit()
    FakeAdapter = _reset_scripted_adapter(["awaiting_reply", "awaiting_reply"])
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    reconciler.reconcile_sessions(con, repo)  # tick 1: answer
    row = get_executor_session_by_id(con, ses_id)
    assert FakeAdapter.reply_calls == 1
    assert "full authority" in FakeAdapter.reply_messages[0]
    assert row["state"] == "awaiting_reply"

    reconciler.reconcile_sessions(con, repo)  # tick 2: still parked -> escalate
    row = get_executor_session_by_id(con, ses_id)
    assert FakeAdapter.reply_calls == 1  # no second reply
    assert row["state"] == "needs_operator"
    assert "still asking" in (row["error"] or "")


def test_awaiting_reply_latch_resets_when_session_unparks(con, tmp_path, monkeypatch):
    """A session that unparks and re-parks is answered again, not escalated."""
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_repark", executor="jules_cli",
                repo="owner/repo", status="running")
    ses_id = insert_executor_session(
        con, "job_repark", "jules_cli", "sess-repark",
        expected_base_commit_sha=base_sha,
    )
    update_executor_session_state(con, ses_id, state="running")
    con.commit()
    FakeAdapter = _reset_scripted_adapter(
        ["awaiting_reply", "running", "awaiting_reply"]
    )
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": FakeAdapter})

    reconciler.reconcile_sessions(con, repo)  # parked -> reply #1
    reconciler.reconcile_sessions(con, repo)  # unparked -> latch resets
    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] == "running"

    reconciler.reconcile_sessions(con, repo)  # re-parked -> reply #2
    row = get_executor_session_by_id(con, ses_id)
    assert FakeAdapter.reply_calls == 2
    assert row["state"] == "awaiting_reply"


class _MuteAdapter:
    """Adapter that reports awaiting_reply but cannot converse."""

    def __init__(self, repo=""):
        self.repo = repo

    def status(self, session_ref):
        return SessionStatus(state="awaiting_reply")


def test_awaiting_reply_without_reply_capability_goes_to_operator(
    con, tmp_path, monkeypatch
):
    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_mute", executor="jules_cli",
                repo="owner/repo", status="running")
    ses_id = insert_executor_session(
        con, "job_mute", "jules_cli", "sess-mute",
        expected_base_commit_sha=base_sha,
    )
    update_executor_session_state(con, ses_id, state="running")
    con.commit()
    monkeypatch.setattr(reconciler, "ADAPTERS", {"jules_cli": _MuteAdapter})

    reconciler.reconcile_sessions(con, repo)

    row = get_executor_session_by_id(con, ses_id)
    assert row["state"] == "needs_operator"
    assert "cannot reply" in (row["error"] or "")


def test_evaluation_batch_carries_expected_base(con, tmp_path):
    """PendingEvaluation must carry the dispatch-recorded base alongside the tip."""
    from scripts.runtime.heartbeat.reconciler import EvaluationBatch

    repo, base_sha = _make_git_repo(tmp_path)
    _insert_job(con, job_id="job_base", executor="jules_cli",
                repo="owner/repo", status="running")
    ses_id = insert_executor_session(
        con, "job_base", "jules_cli", "sess-base",
        expected_base_commit_sha=base_sha,
    )
    session = get_executor_session_by_id(con, ses_id)
    job = con.execute("SELECT * FROM jobs WHERE job_id = ?", ("job_base",)).fetchone()

    batch = EvaluationBatch(max_workers=1)
    batch.add(session, job, result_commit_sha="c" * 40)

    pending = batch._pending[0]
    assert pending.expected_base_commit_sha == base_sha
    assert pending.result_commit_sha == "c" * 40


# --------------------------------------------------------------------------- #
# Evaluator-driven retry (live heartbeat path)
# --------------------------------------------------------------------------- #


def _retry_pending_and_job(con, index=1):
    """Insert a collected evaluation and return (pending, job_id, session_db_id)."""
    job_id, session_db_id = _insert_collected_evaluation(
        con, index, session_id=f"retry-session-{index}"
    )
    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    pending = reconciler.PendingEvaluation(
        session_db_id=session_db_id,
        session_id=f"retry-session-{index}",
        executor="local_subprocess",
        project_id=str(job["project_id"]),
        node_id=str(job["node_id"]),
        job_id=job_id,
        attempt=int(job["attempt"]),
        result_commit_sha="b" * 40,
    )
    return pending, job_id, session_db_id


def _nonpass_cited_verification():
    return {
        "verification_status": "ok",
        "verdict": "needs-human-review",
        "evaluated_commit_sha": "c" * 40,
        "integrity": {
            "verdict": "drift",
            "intent_preserved": False,
            "graph_integrity_preserved": False,
            "required_human_review": True,
            "confidence": 0.8,
            "findings": [
                {
                    "severity": "high",
                    "summary": "broke scripts/runtime/bridge.py:42",
                    "affected_node_ids": [],
                }
            ],
            "reasoning": "violates the runtime contract",
        },
    }


def _successful_dispatch(job, repo, repo_path=None):
    return ProtocolDispatchResult(
        success=True,
        session_ref=SessionRef(executor=job["executor"], session_id="retry-new"),
    )


def test_evaluator_retry_dispatches_on_nonpass_with_cited_findings(
    con, tmp_path, monkeypatch
):
    pending, job_id, _ = _retry_pending_and_job(con)
    monkeypatch.setattr(reconciler, "write_result", lambda **kwargs: None)
    monkeypatch.setattr(reconciler, "maybe_mark_provisional", lambda **kwargs: False)
    monkeypatch.setattr(
        reconciler,
        "_load_project_yaml",
        lambda project_id: {"execution_policy": {"retry_budget": 1}},
    )
    monkeypatch.setattr(reconciler, "dispatch", _successful_dispatch)

    reconciler._finalize_evaluation(
        con, pending, _nonpass_cited_verification(), repo_path=tmp_path
    )

    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert job["attempt"] == 1
    assert job["status"] == "running"
    assert job["queue_state"] == "running"
    # The cited findings rode along as the retry's fix-list.
    findings = json.loads(job["previous_findings"])
    assert findings["verdict"] == "needs-human-review"
    assert findings["integrity_verdict"] == "drift"
    assert findings["findings"][0]["summary"] == "broke scripts/runtime/bridge.py:42"


def test_evaluator_retry_skips_when_findings_uncited(con, tmp_path, monkeypatch):
    pending, job_id, _ = _retry_pending_and_job(con)
    monkeypatch.setattr(reconciler, "write_result", lambda **kwargs: None)
    monkeypatch.setattr(reconciler, "maybe_mark_provisional", lambda **kwargs: False)
    monkeypatch.setattr(
        reconciler,
        "_load_project_yaml",
        lambda project_id: {"execution_policy": {"retry_budget": 1}},
    )
    dispatched = []
    monkeypatch.setattr(
        reconciler,
        "dispatch",
        lambda *a, **k: dispatched.append(1) or _successful_dispatch(*a, **k),
    )

    verification = _nonpass_cited_verification()
    # Strip the file-path citation: findings without evidence never retry.
    verification["integrity"]["findings"] = [
        {"severity": "medium", "summary": "the code feels wrong", "affected_node_ids": []}
    ]
    verification["integrity"]["reasoning"] = "vague"

    reconciler._finalize_evaluation(
        con, pending, verification, repo_path=tmp_path
    )

    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert job["attempt"] == 0
    assert job["status"] == "awaiting_review"
    assert dispatched == []


def test_evaluator_retry_skips_when_budget_exhausted(con, tmp_path, monkeypatch):
    pending, job_id, _ = _retry_pending_and_job(con)
    monkeypatch.setattr(reconciler, "write_result", lambda **kwargs: None)
    monkeypatch.setattr(reconciler, "maybe_mark_provisional", lambda **kwargs: False)
    monkeypatch.setattr(
        reconciler,
        "_load_project_yaml",
        lambda project_id: {"execution_policy": {"retry_budget": 0}},
    )
    monkeypatch.setattr(reconciler, "dispatch", _successful_dispatch)

    reconciler._finalize_evaluation(
        con, pending, _nonpass_cited_verification(), repo_path=tmp_path
    )

    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert job["attempt"] == 0
    assert job["status"] == "awaiting_review"


def test_evaluator_retry_skips_on_pass(con, tmp_path, monkeypatch):
    pending, job_id, _ = _retry_pending_and_job(con)
    monkeypatch.setattr(reconciler, "write_result", lambda **kwargs: None)
    monkeypatch.setattr(reconciler, "maybe_mark_provisional", lambda **kwargs: False)
    monkeypatch.setattr(
        reconciler,
        "_load_project_yaml",
        lambda project_id: {"execution_policy": {"retry_budget": 1}},
    )
    dispatched = []
    monkeypatch.setattr(
        reconciler,
        "dispatch",
        lambda *a, **k: dispatched.append(1) or _successful_dispatch(*a, **k),
    )

    reconciler._finalize_evaluation(
        con,
        pending,
        {"verification_status": "ok", "verdict": "pass"},
        repo_path=tmp_path,
    )

    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert job["attempt"] == 0
    assert job["status"] == "awaiting_review"
    assert dispatched == []


def test_evaluator_retry_skips_on_verification_error(con, tmp_path, monkeypatch):
    pending, job_id, _ = _retry_pending_and_job(con)
    monkeypatch.setattr(reconciler, "write_result", lambda **kwargs: None)
    monkeypatch.setattr(reconciler, "maybe_mark_provisional", lambda **kwargs: False)
    monkeypatch.setattr(
        reconciler,
        "_load_project_yaml",
        lambda project_id: {"execution_policy": {"retry_budget": 1}},
    )
    dispatched = []
    monkeypatch.setattr(
        reconciler,
        "dispatch",
        lambda *a, **k: dispatched.append(1) or _successful_dispatch(*a, **k),
    )

    reconciler._finalize_evaluation(
        con,
        pending,
        {"verification_status": "error", "error": "evaluator crashed"},
        repo_path=tmp_path,
    )

    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    assert job["attempt"] == 0
    assert job["status"] == "awaiting_review"
    assert dispatched == []


def test_evaluator_retry_dispatch_failure_routes_to_review(con, tmp_path, monkeypatch):
    pending, job_id, _ = _retry_pending_and_job(con)
    monkeypatch.setattr(reconciler, "write_result", lambda **kwargs: None)
    monkeypatch.setattr(reconciler, "maybe_mark_provisional", lambda **kwargs: False)
    monkeypatch.setattr(
        reconciler,
        "_load_project_yaml",
        lambda project_id: {"execution_policy": {"retry_budget": 1}},
    )
    monkeypatch.setattr(
        reconciler,
        "dispatch",
        lambda *a, **k: ProtocolDispatchResult(
            success=False, error="executor config broken"
        ),
    )

    reconciler._finalize_evaluation(
        con, pending, _nonpass_cited_verification(), repo_path=tmp_path
    )

    job = con.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    # A failed retry-dispatch does not mark the job failed; the non-pass verdict
    # still routes to the human, and the reserved session is cleaned up.
    assert job["status"] == "awaiting_review"
    sessions = con.execute(
        "SELECT state FROM executor_sessions WHERE job_id = ? ORDER BY state",
        (job_id,),
    ).fetchall()
    states = {row["state"] for row in sessions}
    assert "dispatch_failed" in states
