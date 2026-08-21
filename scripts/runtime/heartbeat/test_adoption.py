"""Guards, dry-run, happy path, and collected→evaluation e2e for job adoption."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts import init_db as init_db_module
from scripts.runtime.heartbeat import reconciler, runner
from scripts.runtime.heartbeat.adoption import AdoptionError, adopt, format_adopt_rows
from scripts.runtime.heartbeat.graph_reader import GraphReader

PROJECT, NODE = "proj", "node-a"
NODE_YAML = """\
schema_version: '1.0'
schema_type: node
node_id: {node_id}
title: {node_id}
status: {status}
why: because
depends_on: []
acceptance_criteria: [it works]
constraints: []
priority: medium
allowed_execution_modes: [local_subprocess]
required_artifacts: []
unlocks: []
"""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "f").write_text("a\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "f").write_text("b\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "result")
    commit = _git(repo, "rev-parse", "HEAD").stdout.strip()

    config = tmp_path / "config"
    nodes = config / "graphs" / PROJECT / "nodes"
    nodes.mkdir(parents=True)
    (config / "graphs" / PROJECT / "project.yaml").write_text(
        f"schema_version: '1.0'\nschema_type: project_graph\n"
        f"project_id: {PROJECT}\nproject_name: Test\nrepo: {repo}\n"
        f"execution_policy:\n  default_executor: local_subprocess\n"
        f"nodes:\n  - id: {NODE}\n    status: ready\n"
    )
    (nodes / f"{NODE}.yaml").write_text(NODE_YAML.format(node_id=NODE, status="ready"))

    runtime = tmp_path / "runtime"
    db_path = runtime / "db" / "queue.db"
    monkeypatch.setattr(init_db_module, "DB_PATH", db_path)
    init_db_module.init_db()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")

    def _adopt(**kw):
        return adopt(
            project_id=kw.pop("project_id", PROJECT),
            node_id=kw.pop("node_id", NODE),
            commit=kw.pop("commit", commit),
            base=kw.pop("base", base),
            config_path=str(config),
            runtime_root=runtime,
            con=con,
            **kw,
        )

    try:
        yield SimpleNamespace(
            repo=repo, base=base, commit=commit, config=config, nodes=nodes,
            runtime=runtime, db_path=db_path, con=con, adopt=_adopt,
        )
    finally:
        con.close()


def test_unknown_executor_rejected(tmp_path):
    with pytest.raises(AdoptionError, match="ADAPTERS"):
        adopt(
            project_id="p", node_id="n", commit="abc", executor="manual",
            config_path=str(tmp_path), runtime_root=tmp_path,
        )


def test_missing_node_rejected(world):
    with pytest.raises(AdoptionError, match="No node file"):
        world.adopt(node_id="missing-node")


def test_terminal_node_rejected(world):
    (world.nodes / f"{NODE}.yaml").write_text(
        NODE_YAML.format(node_id=NODE, status="complete")
    )
    with pytest.raises(AdoptionError, match="terminal"):
        world.adopt()


def test_unresolvable_commit_rejected(world):
    with pytest.raises(AdoptionError, match="does not resolve"):
        world.adopt(commit="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")


def test_base_not_ancestor_rejected(world):
    with pytest.raises(AdoptionError, match="not an ancestor"):
        world.adopt(commit=world.base, base=world.commit)


def test_existing_nonterminal_job_rejected(world):
    world.con.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, status) "
        "VALUES ('e1', 't', 'x', 'issue.opened', 'mapped')"
    )
    world.con.execute(
        "INSERT INTO jobs (job_id, created_at, event_id, project_id, node_id, "
        "job_type, executor, title, goal, status) VALUES "
        "('job_old', 't', 'e1', ?, ?, 'implementation', 'local_subprocess', "
        "'t', 'g', 'ready')",
        (PROJECT, NODE),
    )
    world.con.commit()
    with pytest.raises(AdoptionError, match="non-terminal job"):
        world.adopt()


def test_existing_session_sha_rejected(world):
    world.con.execute(
        "INSERT INTO events (event_id, received_at, source, event_type, status) "
        "VALUES ('e1', 't', 'x', 'issue.opened', 'mapped')"
    )
    world.con.execute(
        "INSERT INTO jobs (job_id, created_at, event_id, project_id, node_id, "
        "job_type, executor, title, goal, status) VALUES "
        "('job_old', 't', 'e1', 'other', 'other-node', 'implementation', "
        "'local_subprocess', 't', 'g', 'complete')"
    )
    world.con.execute(
        "INSERT INTO executor_sessions (session_db_id, job_id, executor, "
        "session_id, execution_attempt_id, attempt_index, state, "
        "result_commit_sha, created_at, updated_at) VALUES "
        "('ses_old', 'job_old', 'local_subprocess', 's', 'job_old:attempt:0', "
        "0, 'evaluated', ?, 't', 't')",
        (world.commit,),
    )
    world.con.commit()
    with pytest.raises(AdoptionError, match="already records"):
        world.adopt()


def test_missing_base_warns(world, capsys):
    world.adopt(base=None, dry_run=True)
    assert "WARNING: --base omitted" in capsys.readouterr().err


def test_dry_run_prints_rows_and_writes_nothing(world):
    plan = world.adopt(dry_run=True)
    text = format_adopt_rows(plan)
    assert "source:   adopt_manual" in text
    assert "status:   mapped" in text
    assert "state:                    collected" in text
    assert world.con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert world.con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    assert world.con.execute("SELECT COUNT(*) FROM executor_sessions").fetchone()[0] == 0
    assert world.con.execute("SELECT COUNT(*) FROM queue_records").fetchone()[0] == 0


def test_happy_path_writes_three_rows(world):
    plan = world.adopt()
    event = world.con.execute("SELECT * FROM events").fetchone()
    job = world.con.execute("SELECT * FROM jobs").fetchone()
    session = world.con.execute("SELECT * FROM executor_sessions").fetchone()
    assert event["source"] == "adopt_manual"
    assert event["status"] == "mapped"
    assert event["url"] == f"adopt://node: {NODE}"
    assert job["job_id"] == plan["job"]["job_id"]
    assert job["status"] == job["queue_state"] == "awaiting_result"
    assert job["executor"] == "local_subprocess"
    assert job["repo"] == str(world.repo)
    assert job["event_id"] == event["event_id"]
    assert session["state"] == "collected"
    assert session["result_commit_sha"] == world.commit
    assert session["expected_base_commit_sha"] == world.base
    assert session["session_id"] == f"adopt_{NODE}_{world.commit[:7]}"
    assert world.con.execute(
        "SELECT COUNT(*) FROM queue_records WHERE job_id = ?", (job["job_id"],)
    ).fetchone()[0] == 0


def test_e2e_collected_activates_project_and_reaches_evaluation(world, monkeypatch):
    """Adopted collected row is itself what makes the project active, then
    reconcile routes it to evaluation without contacting an executor."""
    plan = world.adopt()
    world.con.execute(
        "UPDATE jobs SET status = 'awaiting_review', queue_state = 'awaiting_review' "
        "WHERE job_id = ?",
        (plan["job"]["job_id"],),
    )
    world.con.commit()
    monkeypatch.setattr(runner, "DB_PATH", world.db_path)
    active = runner._active_projects(GraphReader(config_path=str(world.config)))
    assert [p.project_id for p in active] == [PROJECT]

    reached = {}
    orig_add = reconciler.EvaluationBatch.add

    def spy_add(self, session, job, result_sha, **kwargs):
        reached["state"] = session["state"]
        reached["sha"] = result_sha
        reached["job_id"] = job["job_id"]
        return orig_add(self, session, job, result_sha, **kwargs)

    monkeypatch.setattr(reconciler.EvaluationBatch, "add", spy_add)
    monkeypatch.setattr(
        reconciler, "verify_job_return",
        lambda **kw: {"verification_status": "ok", "verdict": "pass"},
    )
    monkeypatch.setattr(reconciler, "write_result", lambda **kw: None)
    monkeypatch.setattr(reconciler, "maybe_mark_provisional", lambda **kw: False)
    reconciler.reconcile_sessions(world.con, world.repo, repo=str(world.repo))
    assert reached == {
        "state": "collected",
        "sha": world.commit,
        "job_id": plan["job"]["job_id"],
    }
