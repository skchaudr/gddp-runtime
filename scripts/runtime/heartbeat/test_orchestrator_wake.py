"""Tests for one orchestrator wake (pack -> prompt -> turn -> decision -> apply).

The properties pinned here are the ones whose absence would let a stateless
orchestrator mis-record outcomes, touch the node job ledger, or run a real
cursor-agent process during a heartbeat tick.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from .graph_reader import GraphReader
from . import orchestrator_wake
from .orchestrator_wake import run_wake

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)

_DISPATCH_JSON = json.dumps(
    {
        "action": "dispatch",
        "node_id": "alpha",
        "to_n": 2,
        "reason": "only dispatchable node and capacity is free",
        "next_wake_s": 120,
    }
)


def _stream(text, subtype="success"):
    return [
        {"type": "system", "subtype": "init", "session_id": "s1"},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
            },
        },
        {
            "type": "result",
            "subtype": subtype,
            "is_error": subtype != "success",
            "result": text,
            "session_id": "s1",
        },
    ]


def _ago(seconds: int) -> str:
    return (NOW - timedelta(seconds=seconds)).isoformat()


@pytest.fixture
def config(tmp_path: Path) -> Path:
    """A four-node graph: three ready, one blocked on alpha."""
    graphs = tmp_path / "graphs" / "demo"
    (graphs / "nodes").mkdir(parents=True)
    (graphs / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "project_id": "demo",
                "project_name": "Demo",
                "repo": "owner/demo",
                "execution_policy": {"max_concurrent_jobs": 3},
                "nodes": [
                    {"id": "alpha", "title": "Alpha", "status": "ready"},
                    {"id": "beta", "title": "Beta", "status": "ready"},
                    {"id": "gamma", "title": "Gamma", "status": "ready"},
                    {"id": "delta", "title": "Delta", "status": "pending"},
                ],
            }
        )
    )
    for node_id, depends in (
        ("alpha", []),
        ("beta", []),
        ("gamma", []),
        ("delta", ["alpha"]),
    ):
        (graphs / "nodes" / f"{node_id}.yaml").write_text(
            yaml.safe_dump(
                {
                    "node_id": node_id,
                    "title": node_id.title(),
                    "status": "pending" if node_id == "delta" else "ready",
                    "depends_on": depends,
                    "allowed_execution_modes": ["agent"],
                }
            )
        )
    return tmp_path


@pytest.fixture
def config_with_model(config: Path) -> Path:
    """Project policy names an orchestrator model for argv resolution."""
    project_yaml = config / "graphs" / "demo" / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text())
    data["execution_policy"] = {
        "max_concurrent_jobs": 3,
        "models": {"orchestrator": "cursor-grok-4.6-high"},
    }
    project_yaml.write_text(yaml.safe_dump(data))
    return config


@pytest.fixture
def config_with_run_block(config: Path) -> Path:
    """Project policy carries a per-run operator block for the prompt."""
    project_yaml = config / "graphs" / "demo" / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text())
    data["execution_policy"] = {
        "max_concurrent_jobs": 3,
        "orchestrator_run_block": "Worker budget for this run: 3.",
    }
    project_yaml.write_text(yaml.safe_dump(data))
    return config


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(tmp_path / "queue.db")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY, project_id TEXT, repo TEXT, node_id TEXT,
            status TEXT, queue_state TEXT, attempt INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3, created_at TEXT
        );
        CREATE TABLE executor_sessions (
            session_db_id TEXT PRIMARY KEY, job_id TEXT, executor TEXT,
            session_id TEXT, state TEXT, created_at TEXT, updated_at TEXT,
            attempt_index INTEGER
        );
        CREATE TABLE results (
            result_id TEXT PRIMARY KEY, job_id TEXT, outcome TEXT,
            received_at TEXT
        );
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY, schema_version TEXT, received_at TEXT,
            source TEXT, event_type TEXT, actor TEXT, url TEXT,
            project_id TEXT, project_node_candidates TEXT, scope_status TEXT,
            priority TEXT, risk_level TEXT, routing TEXT, status TEXT, repo TEXT
        );
        """
    )
    return con


def _wake_dir(spool_root: Path) -> Path:
    return next((spool_root / "demo").iterdir())


def _run(db, config, tmp_path, monkeypatch, *, answer=_DISPATCH_JSON, spawn_result=None):
    spool_root = tmp_path / "wakes"
    receipts_root = tmp_path / "receipts"
    reader = GraphReader(str(config))
    project = reader.load_project("demo")

    if spawn_result is None:
        spawn_result = (0, None, _stream(answer))

    def fake_spawn(argv, attempt_dir, timeout_s):
        fake_spawn.last_argv = argv
        return spawn_result

    fake_spawn.last_argv = None
    monkeypatch.setattr(orchestrator_wake, "_spawn_turn", fake_spawn)

    applied = run_wake(
        db,
        reader,
        project,
        now=NOW,
        spool_root=spool_root,
        receipts_root=receipts_root,
    )
    return applied, spool_root, receipts_root, fake_spawn.last_argv


# ---------------------------------------------------------------------------


def test_happy_path_applies_dispatch_and_leaves_a_wake_record(db, config, tmp_path, monkeypatch):
    """A completed turn with valid JSON lands one dispatch event and a full
    wake spool record — the orchestrator's only durable memory of the pulse."""
    applied, spool_root, receipts_root, _ = _run(db, config, tmp_path, monkeypatch)

    assert applied is not None
    assert applied.effected is True

    rows = db.execute("SELECT * FROM events").fetchall()
    assert len(rows) == 1
    assert rows[0]["source"] == "orchestrator"
    assert json.loads(rows[0]["routing"]) == {"worker_budget": 2}

    wake_dir = _wake_dir(spool_root)
    assert (wake_dir / "prompt.txt").is_file()
    assert (wake_dir / "raw.jsonl").is_file()
    wake_json = json.loads((wake_dir / "wake.json").read_text())
    assert wake_json["kind"] == "orchestrator_wake"
    assert wake_json["decision"]["action"] == "dispatch"
    assert wake_json["applied"]["effected"] is True

    assert list((receipts_root / "demo").glob("*.json"))


def test_wakes_stay_out_of_the_node_job_ledger(db, config, tmp_path, monkeypatch):
    """G6: a wake spools beside node attempts and never opens a jobs row —
    treating a pulse as node work would consume capacity and corrupt the ledger."""
    _, spool_root, _, _ = _run(db, config, tmp_path, monkeypatch)

    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM executor_sessions").fetchone()[0] == 0
    assert _wake_dir(spool_root).parent == spool_root / "demo"


def test_prose_answer_without_json_returns_none_and_records_error(
    db, config, tmp_path, monkeypatch
):
    """Prose with no JSON object must fail closed — guessing a decision from
    natural language would let a stateless orchestrator act on hallucination."""
    applied, spool_root, _, _ = _run(
        db,
        config,
        tmp_path,
        monkeypatch,
        answer="I think we should hold for now.",
    )

    assert applied is None
    wake_json = json.loads((_wake_dir(spool_root) / "wake.json").read_text())
    assert "error" in wake_json
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_incomplete_turn_returns_none_and_records_error(db, config, tmp_path, monkeypatch):
    """A turn that never reaches result/success is incomplete work — applying
    a decision from a partial stream would race the agent still running."""
    applied, spool_root, _, _ = _run(
        db,
        config,
        tmp_path,
        monkeypatch,
        spawn_result=(0, None, _stream("partial answer", subtype="error")),
    )

    assert applied is None
    wake_json = json.loads((_wake_dir(spool_root) / "wake.json").read_text())
    assert "error" in wake_json
    assert "completed work" in wake_json["error"]
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_spawn_failure_returns_none_and_records_error(db, config, tmp_path, monkeypatch):
    """A killed turn must surface the spawn error in wake.json — silent failure
    would leave the next wake blind to a timeout or binary crash."""
    applied, spool_root, _, _ = _run(
        db,
        config,
        tmp_path,
        monkeypatch,
        spawn_result=(-15, "wake exceeded 600s and was killed", []),
    )

    assert applied is None
    wake_json = json.loads((_wake_dir(spool_root) / "wake.json").read_text())
    assert wake_json["error"] == "wake exceeded 600s and was killed"
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_execution_policy_model_reaches_argv(db, config_with_model, tmp_path, monkeypatch):
    """The orchestrator model from execution_policy must reach build_argv —
    otherwise every wake would run the transport default and ignore project intent."""
    _, _, _, argv = _run(db, config_with_model, tmp_path, monkeypatch)

    assert argv is not None
    model_index = argv.index("--model")
    assert argv[model_index + 1] == "cursor-grok-4.6-high"


def test_env_model_orchestrator_beats_execution_policy(
    db, config_with_model, tmp_path, monkeypatch
):
    """Role-scoped env wins over policy — operators must be able to override
    the model for one host without rewriting the graph checkout."""
    monkeypatch.setenv("GDDP_CURSOR_CLI_MODEL_ORCHESTRATOR", "env-orchestrator-model")

    _, _, _, argv = _run(db, config_with_model, tmp_path, monkeypatch)

    model_index = argv.index("--model")
    assert argv[model_index + 1] == "env-orchestrator-model"


def test_orchestrator_run_block_lands_in_the_prompt(
    db, config_with_run_block, tmp_path, monkeypatch
):
    """The per-run operator block must appear in prompt.txt — without it the
    model sees pack memory but misses constraints set for this pulse only."""
    _, spool_root, _, _ = _run(db, config_with_run_block, tmp_path, monkeypatch)

    prompt = (_wake_dir(spool_root) / "prompt.txt").read_text()
    assert "### THIS RUN" in prompt
    assert "Worker budget for this run: 3." in prompt
