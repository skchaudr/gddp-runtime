"""Focused tests for one cumulative review branch per graph."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.runtime.cumulative_branch import (
    ActiveResult,
    cleanup_preserved_refs,
    delete_remote_temporary_ref,
    load_target_branch,
    publication_in_progress,
    query_active_results,
    rebuild_project,
    rebuild_review_branch,
    remote_ref_sha,
    review_ref_name,
    schedule_rebuild,
    topological_merge_order,
    wait_for_publication,
)
from scripts.runtime import cumulative_branch as cb


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def _init_identity(repo: Path) -> None:
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")


def _commit(repo: Path, relpath: str, text: str, message: str) -> str:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    _git(repo, "add", relpath)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            project_id TEXT,
            node_id TEXT NOT NULL,
            dependencies TEXT
        );
        CREATE TABLE executor_sessions (
            session_db_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            attempt_index INTEGER NOT NULL DEFAULT 0,
            result_commit_sha TEXT,
            updated_at TEXT
        );
        """
    )


def test_review_ref_is_one_named_branch_per_graph():
    assert review_ref_name("myapi") == "gddp/review/myapi"


def test_load_target_branch_reads_project_yaml(tmp_path: Path):
    project = tmp_path / "graphs" / "demo"
    project.mkdir(parents=True)
    (project / "project.yaml").write_text("target_branch: develop\n")
    assert load_target_branch("demo", root=tmp_path) == "develop"
    assert load_target_branch("missing", root=tmp_path) == "main"


def test_topological_merge_order_parents_before_children():
    items = [
        ActiveResult("c", "job-c", "s-c", "ccc", ("b",)),
        ActiveResult("a", "job-a", "s-a", "aaa"),
        ActiveResult("b", "job-b", "s-b", "bbb", ("a",)),
    ]
    assert [item.node_id for item in topological_merge_order(items)] == [
        "a",
        "b",
        "c",
    ]


def test_query_active_results_skips_complete_and_deferred():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    _schema(con)
    con.executemany(
        "INSERT INTO jobs VALUES (?, ?, ?, ?)",
        [
            ("job-a", "demo", "node-a", "[]"),
            ("job-b", "demo", "node-b", "[]"),
            ("job-c", "demo", "node-c", "[]"),
            ("job-old", "demo", "node-a", "[]"),
        ],
    )
    con.executemany(
        "INSERT INTO executor_sessions VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("s1", "job-old", "old", 0, "aaa111", "2026-01-01"),
            ("s2", "job-a", "new", 1, "aaa222", "2026-01-02"),
            ("s3", "job-b", "sb", 0, "bbb000", "2026-01-02"),
            ("s4", "job-c", "sc", 0, "ccc000", "2026-01-02"),
        ],
    )
    results = query_active_results(
        con,
        "demo",
        statuses={"node-a": "ready", "node-b": "complete", "node-c": "deferred"},
        dependencies={"node-a": ()},
    )
    assert [(item.node_id, item.commit_sha) for item in results] == [
        ("node-a", "aaa222")
    ]


def _bare_pair(tmp_path: Path) -> tuple[Path, Path, str]:
    remote = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(tmp_path, "clone", str(remote), str(work))
    _init_identity(work)
    _git(work, "checkout", "-b", "main")
    base = _commit(work, "README", "base\n", "base")
    _git(work, "push", "-u", "origin", "main")
    return remote, work, base


def test_rebuild_merges_results_and_deletes_preserved_temp_refs(tmp_path: Path):
    _remote, work, base = _bare_pair(tmp_path)
    _git(work, "checkout", "-b", "feat-a")
    sha_a = _commit(work, "a.txt", "A\n", "node a")
    _git(work, "push", "origin", "HEAD:refs/heads/gddp/result-job-a-sess-a")
    _git(work, "push", "origin", "HEAD:refs/heads/gddp/attempt-job-a-attempt-1")
    _git(work, "update-ref", "refs/heads/gddp/result-job-a-sess-a", sha_a)
    _git(work, "update-ref", "refs/heads/gddp/attempt-job-a-attempt-1", sha_a)
    _git(work, "checkout", "--detach", base)
    _git(work, "checkout", "-b", "feat-b")
    sha_b = _commit(work, "b.txt", "B\n", "node b")
    _git(work, "push", "origin", "HEAD:refs/heads/gddp/result-job-b-sess-b")
    _git(work, "update-ref", "refs/heads/gddp/result-job-b-sess-b", sha_b)
    _git(work, "checkout", "main")

    report = rebuild_review_branch(
        work,
        "demo",
        [
            ActiveResult("node-b", "job-b", "sess-b", sha_b, ("node-a",)),
            ActiveResult("node-a", "job-a", "sess-a", sha_a),
        ],
        target_branch="main",
    )
    assert report.ok
    assert report.review_ref == "gddp/review/demo"
    assert report.merged_shas == [sha_a, sha_b]
    assert set(report.cleaned_refs) >= {
        "gddp/result-job-a-sess-a",
        "gddp/result-job-b-sess-b",
        "gddp/attempt-job-a-attempt-1",
    }

    _git(work, "fetch", "origin")
    tree = _git(
        work, "ls-tree", "-r", "--name-only", "origin/gddp/review/demo"
    ).stdout.split()
    assert "a.txt" in tree and "b.txt" in tree and "README" in tree
    remote_heads = _git(work, "ls-remote", "--heads", "origin").stdout
    assert "gddp/review/demo" in remote_heads
    assert "gddp/result-job-a-sess-a" not in remote_heads
    assert "gddp/attempt-job-a-attempt-1" not in remote_heads


def test_rebuild_conflict_fails_closed_and_preserves_previous_review(tmp_path: Path):
    _remote, work, base = _bare_pair(tmp_path)
    _git(work, "checkout", "-b", "feat-a")
    sha_a = _commit(work, "same.txt", "A\n", "node a")
    first = rebuild_review_branch(
        work,
        "demo",
        [ActiveResult("node-a", "job-a", "sess-a", sha_a)],
        target_branch="main",
    )
    assert first.ok
    previous = first.review_sha
    _git(work, "checkout", "--detach", base)
    _git(work, "checkout", "-b", "feat-b")
    sha_b = _commit(work, "same.txt", "B\n", "node b")
    _git(work, "update-ref", "refs/heads/gddp/result-job-b-sess-b", sha_b)
    _git(work, "push", "origin", "HEAD:refs/heads/gddp/result-job-b-sess-b")
    _git(work, "checkout", "main")

    report = rebuild_review_branch(
        work,
        "demo",
        [
            ActiveResult("node-a", "job-a", "sess-a", sha_a),
            ActiveResult("node-b", "job-b", "sess-b", sha_b),
        ],
        target_branch="main",
    )
    assert not report.ok
    assert not report.published
    assert sha_a in report.merged_shas
    assert sha_b in report.skipped_shas
    assert report.cleaned_refs == []
    assert "merge conflict" in (report.error or "")
    _git(work, "fetch", "origin")
    current = _git(work, "rev-parse", "origin/gddp/review/demo").stdout.strip()
    assert current == previous
    remote_heads = _git(work, "ls-remote", "--heads", "origin").stdout
    assert "gddp/result-job-b-sess-b" in remote_heads


def test_cleanup_leaves_unpreserved_temp_ref(tmp_path: Path):
    _remote, work, _base = _bare_pair(tmp_path)
    _git(work, "checkout", "-b", "feat")
    preserved = _commit(work, "keep.txt", "keep\n", "keep")
    orphan = _commit(work, "drop.txt", "drop\n", "drop")
    _git(work, "update-ref", "refs/heads/gddp/result-keep-s", preserved)
    _git(work, "update-ref", "refs/heads/gddp/result-orphan-s", orphan)
    _git(work, "push", "origin", "HEAD:refs/heads/gddp/review/demo")
    _git(work, "push", "origin", f"{preserved}:refs/heads/gddp/result-keep-s")
    _git(work, "push", "origin", f"{orphan}:refs/heads/gddp/result-orphan-s")
    cleaned = cleanup_preserved_refs(work, preserved)
    assert "gddp/result-keep-s" in cleaned.remote_deleted
    assert "gddp/result-orphan-s" not in cleaned.remote_deleted
    assert "gddp/result-orphan-s" in cleaned.skipped
    assert _git(work, "rev-parse", "--verify", "refs/heads/gddp/result-orphan-s").returncode == 0


def test_rebuild_project_reads_db_and_graph(tmp_path: Path):
    _remote, work, _base = _bare_pair(tmp_path)
    _git(work, "checkout", "-b", "feat-a")
    sha_a = _commit(work, "a.txt", "A\n", "node a")
    config = tmp_path / "config"
    nodes = config / "graphs" / "demo" / "nodes"
    nodes.mkdir(parents=True)
    (config / "graphs" / "demo" / "project.yaml").write_text(
        "project_id: demo\nrepo: work\ntarget_branch: main\nnodes:\n"
        "  - id: node-a\n    status: ready\n  - id: node-done\n    status: complete\n"
    )
    (nodes / "node-a.yaml").write_text(
        "node_id: node-a\nstatus: ready\ndepends_on: []\n"
    )
    (nodes / "node-done.yaml").write_text(
        "node_id: node-done\nstatus: complete\ndepends_on: []\n"
    )
    db = tmp_path / "queue.db"
    con = sqlite3.connect(db)
    _schema(con)
    con.execute("INSERT INTO jobs VALUES (?, ?, ?, ?)", ("job-a", "demo", "node-a", "[]"))
    con.execute("INSERT INTO jobs VALUES (?, ?, ?, ?)", ("job-d", "demo", "node-done", "[]"))
    con.execute(
        "INSERT INTO executor_sessions VALUES (?, ?, ?, ?, ?, ?)",
        ("s-a", "job-a", "sess-a", 0, sha_a, "now"),
    )
    con.execute(
        "INSERT INTO executor_sessions VALUES (?, ?, ?, ?, ?, ?)",
        ("s-d", "job-d", "sess-d", 0, "deadbeef", "now"),
    )
    con.commit()
    con.close()

    report = rebuild_project(
        "demo", repo_path=work, db_path=db, config=config
    )
    assert report.ok
    assert report.merged_shas == [sha_a]
    _git(work, "fetch", "origin")
    names = _git(
        work, "ls-tree", "-r", "--name-only", "origin/gddp/review/demo"
    ).stdout
    assert "a.txt" in names


def test_schedule_rebuild_is_noop_under_pytest():
    cb._reset_scheduler_state_for_tests()
    with patch(
        "scripts.runtime.cumulative_branch.rebuild_project"
    ) as rebuild:
        schedule_rebuild("demo")
        rebuild.assert_not_called()


def test_schedule_rebuild_offloads_when_enabled():
    cb._reset_scheduler_state_for_tests()
    with (
        patch.dict("os.environ", {"GDDP_REVIEW_BRANCH_IN_TESTS": "1"}, clear=False),
        patch(
            "scripts.runtime.cumulative_branch.rebuild_project"
        ) as rebuild,
    ):
        rebuild.return_value.ok = True
        rebuild.return_value.review_ref = "gddp/review/demo"
        rebuild.return_value.review_sha = "a" * 40
        rebuild.return_value.merged_shas = []
        rebuild.return_value.skipped_shas = []
        rebuild.return_value.cleaned_refs = []
        schedule_rebuild("demo")
        wait_for_publication(timeout=2)
        rebuild.assert_called_with("demo")
        assert not publication_in_progress()


def test_wait_for_publication_blocks_until_non_daemon_worker_finishes():
    cb._reset_scheduler_state_for_tests()
    started = threading.Event()
    release = threading.Event()

    def fake_rebuild(project_id):
        started.set()
        assert release.wait(timeout=2)
        report = cb.RebuildReport(
            project_id=project_id,
            review_ref=review_ref_name(project_id),
            target_branch="main",
            review_sha="a" * 40,
            published=True,
        )
        return report

    with (
        patch.dict("os.environ", {"GDDP_REVIEW_BRANCH_IN_TESTS": "1"}, clear=False),
        patch("scripts.runtime.cumulative_branch.rebuild_project", side_effect=fake_rebuild),
    ):
        schedule_rebuild("demo")
        assert started.wait(timeout=2)
        worker = cb._workers["demo"]
        assert worker.is_alive()
        assert worker.daemon is False
        assert publication_in_progress()
        finished = []

        def waiter():
            wait_for_publication(timeout=2)
            finished.append(True)

        waiter_thread = threading.Thread(target=waiter)
        waiter_thread.start()
        time.sleep(0.05)
        assert not finished
        release.set()
        waiter_thread.join(timeout=2)
        assert finished == [True]
        assert not publication_in_progress()


def test_heartbeat_waits_for_publication_before_returning(tmp_path, monkeypatch):
    from scripts.runtime.heartbeat import runner
    from scripts.runtime.heartbeat.test_executor_sessions import _apply_schema

    db_path = tmp_path / "queue.db"
    init_con = sqlite3.connect(str(db_path))
    _apply_schema(init_con)
    init_con.close()
    monkeypatch.setattr(runner, "DB_PATH", db_path)
    mock_reader = MagicMock()
    mock_reader.load_project.return_value = SimpleNamespace(
        execution_policy={}, nodes=[]
    )
    mock_reader.get_ready_nodes.return_value = []
    monkeypatch.setattr(runner, "GraphReader", lambda **kw: mock_reader)

    class FakeEvaluationBatch:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def finalize(self, c):
            return None

    monkeypatch.setattr(runner, "EvaluationBatch", FakeEvaluationBatch)
    monkeypatch.setattr(runner, "reconcile_sessions", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_plan_dispatches", lambda *a, **k: [])
    monkeypatch.setattr(runner, "advance_frontier", lambda *a, **k: False)
    monkeypatch.setattr(runner, "reconcile_reviewed_jobs", lambda *a, **k: [])
    waited = []
    monkeypatch.setattr(
        runner, "wait_for_publication", lambda: waited.append("waited")
    )
    runner.run_heartbeat(
        project_id="proj-1",
        repo="owner/repo",
        config_path=str(tmp_path / "no-config"),
    )
    assert waited == ["waited"]


def test_one_rebuild_per_project_serializes_publish_and_cleanup():
    cb._reset_scheduler_state_for_tests()
    current = {"n": 0}
    max_seen = {"n": 0}
    gate = threading.Event()

    def fake_rebuild(project_id):
        current["n"] += 1
        max_seen["n"] = max(max_seen["n"], current["n"])
        assert gate.wait(timeout=2)
        time.sleep(0.05)
        current["n"] -= 1
        return cb.RebuildReport(
            project_id=project_id,
            review_ref=review_ref_name(project_id),
            target_branch="main",
            review_sha="b" * 40,
            published=True,
        )

    with (
        patch.dict("os.environ", {"GDDP_REVIEW_BRANCH_IN_TESTS": "1"}, clear=False),
        patch("scripts.runtime.cumulative_branch.rebuild_project", side_effect=fake_rebuild),
    ):
        schedule_rebuild("demo")
        schedule_rebuild("demo")
        schedule_rebuild("demo")
        assert len(cb._workers) == 1
        gate.set()
        wait_for_publication(timeout=2)
        assert max_seen["n"] == 1


def test_moved_retry_ref_survives_lease_delete(tmp_path: Path):
    _remote, work, _base = _bare_pair(tmp_path)
    _git(work, "checkout", "-b", "feat")
    first = _commit(work, "keep.txt", "keep\n", "keep")
    moved = _commit(work, "retry.txt", "retry\n", "retry")
    _git(work, "push", "origin", f"{first}:refs/heads/gddp/attempt-job-a-attempt-1")
    observed = remote_ref_sha(work, "gddp/attempt-job-a-attempt-1")
    assert observed == first
    _git(work, "push", "--force", "origin", f"{moved}:refs/heads/gddp/attempt-job-a-attempt-1")
    assert delete_remote_temporary_ref(
        work, "gddp/attempt-job-a-attempt-1", first
    ) is False
    assert remote_ref_sha(work, "gddp/attempt-job-a-attempt-1") == moved
    cleanup = cleanup_preserved_refs(work, first, extra_refs=("gddp/attempt-job-a-attempt-1",))
    assert cleanup.remote_deleted == []
    assert "gddp/attempt-job-a-attempt-1" in cleanup.skipped


def test_return_router_schedules_rebuild_after_write():
    from scripts.runtime.test_return_router import TestReturnRouter

    case = TestReturnRouter()
    with patch(
        "scripts.runtime.return_router.schedule_rebuild"
    ) as scheduled:
        case.test_handle_merged_pr_success()
        scheduled.assert_called_once_with("vault-doctor")


def test_reconciler_schedules_rebuild_after_commit_ref(tmp_path, monkeypatch):
    from scripts.runtime.heartbeat import reconciler
    from scripts.runtime.heartbeat.state_recorder import insert_executor_session
    from scripts.runtime.heartbeat.test_executor_sessions import (
        _apply_schema,
        _insert_job,
        _make_fake_adapter,
        _make_git_repo,
    )

    repo, base_sha = _make_git_repo(tmp_path)
    (repo / "result.txt").write_text("from local agent\n")
    _git(repo, "add", "result.txt")
    _git(repo, "commit", "-m", "agent result")
    result_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "branch", "gddp/attempt-job_local", result_sha)

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    _apply_schema(con)
    _insert_job(
        con,
        job_id="job_local",
        executor="local_subprocess",
        project_id="demo",
        status="running",
    )
    insert_executor_session(
        con,
        "job_local",
        "local_subprocess",
        "sess-local",
        expected_base_commit_sha=base_sha,
    )
    FakeAdapter = _make_fake_adapter(
        status_state="completed",
        result_commit_sha=result_sha,
        result_ref="gddp/attempt-job_local",
    )
    monkeypatch.setattr(
        reconciler, "ADAPTERS", {"local_subprocess": FakeAdapter}
    )
    monkeypatch.setattr(
        reconciler,
        "verify_job_return",
        lambda **kw: {"verification_status": "ok", "verdict": "pass"},
    )
    monkeypatch.setattr(reconciler, "write_result", lambda **kw: None)
    scheduled: list[str | None] = []
    monkeypatch.setattr(
        reconciler, "schedule_rebuild", scheduled.append
    )
    reconciler.reconcile_sessions(con, repo)
    assert scheduled == ["demo"]
    con.close()
