"""Guards, dry-run, write path, and collected→evaluation e2e."""

from __future__ import annotations

import json, sqlite3, subprocess, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.runtime.heartbeat import reconciler, runner
from scripts.runtime.heartbeat.adoption import BASE_OMITTED_WARNING, AdoptionError, adopt
from scripts.runtime.heartbeat.dispatcher import ADAPTERS
from scripts.runtime.heartbeat.graph_reader import GraphReader

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE events (
    event_id TEXT PRIMARY KEY, schema_version TEXT, received_at TEXT,
    source TEXT, event_type TEXT, actor TEXT, url TEXT, repo TEXT,
    project_id TEXT, project_node_candidates TEXT, scope_status TEXT,
    priority TEXT, risk_level TEXT, routing TEXT, status TEXT);
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY, schema_version TEXT DEFAULT '1.0',
    created_at TEXT NOT NULL, event_id TEXT, project_id TEXT, repo TEXT,
    node_id TEXT NOT NULL, job_type TEXT NOT NULL, executor TEXT NOT NULL,
    queue_state TEXT, title TEXT NOT NULL, goal TEXT NOT NULL, why TEXT,
    constraints TEXT, acceptance_criteria TEXT, dependencies TEXT,
    priority TEXT, status TEXT, attempt INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3, artifacts_dir TEXT,
    required_artifacts TEXT DEFAULT '[]', previous_findings TEXT,
    FOREIGN KEY(event_id) REFERENCES events(event_id));
CREATE TABLE queue_records (
    queue_item_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
    queue TEXT NOT NULL, available_at TEXT NOT NULL);
CREATE TABLE executor_sessions (
    session_db_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
    executor TEXT NOT NULL, session_id TEXT NOT NULL,
    execution_attempt_id TEXT NOT NULL, attempt_index INTEGER NOT NULL,
    state TEXT, expected_base_commit_sha TEXT, result_commit_sha TEXT,
    patch_path TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id));
"""
NODE = """\
schema_version: '1.0'
schema_type: node
node_id: {id}
title: {id}
status: {status}
why: fixture
priority: medium
depends_on: []
acceptance_criteria: []
constraints: []
allowed_execution_modes: [local_subprocess]
required_artifacts: []
unlocks: []
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f").write_text("base\n")
    _git(repo, "add", "."); _git(repo, "commit", "-m", "base")
    (repo / "f").write_text("result\n")
    _git(repo, "add", "."); _git(repo, "commit", "-m", "result")
    return repo


@pytest.fixture()
def shas(git_repo: Path) -> tuple[str, str]:
    return _git(git_repo, "rev-parse", "HEAD"), _git(git_repo, "rev-parse", "HEAD~1")


@pytest.fixture()
def config_root(tmp_path: Path, git_repo: Path) -> Path:
    root = tmp_path / "gddp-config"
    nodes = root / "graphs" / "adopt-proj" / "nodes"
    nodes.mkdir(parents=True)
    (root / "graphs" / "adopt-proj" / "project.yaml").write_text(
        "schema_version: '1.0'\nschema_type: project_graph\n"
        f"project_id: adopt-proj\nproject_name: Adopt Fixture\nrepo: {git_repo}\n"
        "nodes:\n  - id: node-ready\n    status: ready\n"
        "  - id: node-done\n    status: complete\n"
    )
    for nid, st in (("node-ready", "ready"), ("node-done", "complete")):
        (nodes / f"{nid}.yaml").write_text(NODE.format(id=nid, status=st))
    return root


@pytest.fixture()
def con() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    (root / "jobs").mkdir(parents=True)
    return root


def _go(con, config_root, runtime_root, shas, **over):
    commit, base = shas
    kw = dict(con=con, project_id="adopt-proj", node_id="node-ready",
              commit=commit, base=base, executor="local_subprocess",
              dry_run=False, config_path=config_root, runtime_root=runtime_root)
    kw.update(over)
    return adopt(**kw)


def test_commit_must_resolve(con, config_root, runtime_root, shas):
    with pytest.raises(AdoptionError, match="does not resolve"):
        _go(con, config_root, runtime_root, shas, commit="deadbeef" * 5)


def test_base_must_be_ancestor(con, config_root, runtime_root, git_repo, shas):
    commit, _ = shas
    _git(git_repo, "checkout", "--orphan", "other")
    (git_repo / "g").write_text("other\n")
    _git(git_repo, "add", "."); _git(git_repo, "commit", "-m", "other")
    other = _git(git_repo, "rev-parse", "HEAD")
    _git(git_repo, "checkout", "main")
    with pytest.raises(AdoptionError, match="not an ancestor"):
        _go(con, config_root, runtime_root, shas, commit=commit, base=other)


def test_node_must_exist(con, config_root, runtime_root, shas):
    with pytest.raises(AdoptionError, match="No node file found"):
        _go(con, config_root, runtime_root, shas, node_id="node-missing")


def test_terminal_node_refused(con, config_root, runtime_root, shas):
    with pytest.raises(AdoptionError, match="terminal"):
        _go(con, config_root, runtime_root, shas, node_id="node-done")


def test_existing_non_terminal_job_refused(con, config_root, runtime_root, shas):
    con.execute("INSERT INTO events (event_id, received_at, source, event_type, status) "
                "VALUES ('evt_old', 't', 'x', 'issue.opened', 'mapped')")
    con.execute("INSERT INTO jobs (job_id, created_at, event_id, project_id, node_id, "
                "job_type, executor, title, goal, status) VALUES "
                "('job_old', 't', 'evt_old', 'adopt-proj', 'node-ready', "
                "'implementation', 'local_subprocess', 't', 'g', 'awaiting_result')")
    con.commit()
    with pytest.raises(AdoptionError, match="non-terminal job"):
        _go(con, config_root, runtime_root, shas)


def test_existing_result_sha_refused(con, config_root, runtime_root, shas):
    commit, _ = shas
    con.execute("INSERT INTO events (event_id, received_at, source, event_type, status) "
                "VALUES ('evt_old', 't', 'x', 'issue.opened', 'mapped')")
    con.execute("INSERT INTO jobs (job_id, created_at, event_id, project_id, node_id, "
                "job_type, executor, title, goal, status) VALUES "
                "('job_old', 't', 'evt_old', 'adopt-proj', 'other-node', "
                "'implementation', 'local_subprocess', 't', 'g', 'failed')")
    con.execute("INSERT INTO executor_sessions (session_db_id, job_id, executor, "
                "session_id, execution_attempt_id, attempt_index, state, "
                "result_commit_sha, created_at, updated_at) VALUES "
                "('ses_old', 'job_old', 'local_subprocess', 's', 'a', 0, "
                "'evaluated', ?, 't', 't')", (commit,))
    con.commit()
    with pytest.raises(AdoptionError, match="already carries"):
        _go(con, config_root, runtime_root, shas)


def test_unknown_executor_refused(con, config_root, runtime_root, shas):
    assert "manual" not in ADAPTERS
    with pytest.raises(AdoptionError, match="ADAPTERS"):
        _go(con, config_root, runtime_root, shas, executor="manual")


def test_dry_run_prints_three_rows_and_writes_nothing(
    con, config_root, runtime_root, shas, capsys
):
    plan = _go(con, config_root, runtime_root, shas, dry_run=True)
    payload = json.loads(capsys.readouterr().out)
    assert payload["event"]["source"] == "adopt_manual"
    assert payload["event"]["status"] == "mapped"
    assert payload["job"]["status"] == "awaiting_result"
    assert payload["session"]["state"] == "collected"
    assert plan.job["job_id"].startswith("job_")
    for table in ("events", "jobs", "executor_sessions", "queue_records"):
        assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_happy_path_writes_three_rows(con, config_root, runtime_root, shas, capsys):
    commit, base = shas
    plan = _go(con, config_root, runtime_root, shas)
    assert BASE_OMITTED_WARNING not in capsys.readouterr().err
    event = con.execute("SELECT * FROM events").fetchone()
    job = con.execute("SELECT * FROM jobs").fetchone()
    session = con.execute("SELECT * FROM executor_sessions").fetchone()
    project = GraphReader(config_path=str(config_root)).load_project("adopt-proj")
    assert event["source"] == "adopt_manual" and event["status"] == "mapped"
    assert event["url"] == "adopt://node: node-ready"
    assert job["job_id"] == plan.job["job_id"]
    assert job["status"] == job["queue_state"] == "awaiting_result"
    assert job["executor"] == "local_subprocess"
    assert job["repo"] == project.repo
    assert session["state"] == "collected"
    assert session["result_commit_sha"] == commit
    assert session["expected_base_commit_sha"] == base
    assert session["session_id"] == f"adopt_node-ready_{commit[:12]}"
    assert con.execute("SELECT COUNT(*) FROM queue_records").fetchone()[0] == 0


def test_collected_row_activates_project_and_reaches_evaluation(
    con, config_root, runtime_root, git_repo, shas, tmp_path, monkeypatch
):
    """A collected session is itself what makes the project active; reconcile
    then routes it to evaluation without contacting an adapter."""
    commit, _ = shas
    plan = _go(con, config_root, runtime_root, shas)
    db_path = tmp_path / "queue.db"
    disk = sqlite3.connect(db_path)
    disk.executescript(SCHEMA)
    for table in ("events", "jobs", "executor_sessions"):
        rows = con.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            continue
        cols = list(rows[0].keys())
        disk.executemany(
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
            [tuple(row[c] for c in cols) for row in rows],
        )
    disk.commit(); disk.close()
    monkeypatch.setattr(runner, "DB_PATH", db_path)
    reader = GraphReader(config_path=str(config_root))
    assert [p.project_id for p in runner._active_projects(reader)] == ["adopt-proj"]
    ticks = []
    monkeypatch.setattr(runner, "run_heartbeat", lambda **kw: ticks.append(kw))
    runner.run_active_projects(config_path=str(config_root))
    assert ticks == [{"project_id": "adopt-proj", "repo": str(git_repo),
                      "config_path": str(config_root)}]
    monkeypatch.setattr(reconciler, "ADAPTERS", {"local_subprocess": object})
    monkeypatch.setattr(reconciler, "verify_job_return",
                        lambda **kw: {"verification_status": "ok", "verdict": "pass"})
    monkeypatch.setattr(reconciler, "write_result", lambda **kw: None)
    monkeypatch.setattr(reconciler, "maybe_mark_provisional", lambda **kw: False)
    reconciler.reconcile_sessions(
        con, repo=reader.load_project("adopt-proj").repo, repo_path=str(git_repo)
    )
    session = con.execute("SELECT * FROM executor_sessions").fetchone()
    assert session["state"] == "evaluated"
    assert session["result_commit_sha"] == commit
    assert con.execute("SELECT status FROM jobs").fetchone()[0] == "awaiting_review"
    assert plan.session["session_id"].startswith("adopt_node-ready_")
