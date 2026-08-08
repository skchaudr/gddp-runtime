from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

from scripts import init_db
from scripts.adapters import mission_adapter
from scripts.adapters.executor_protocol import NodePacket
from scripts.adapters.mission_adapter import MissionAdapter
from scripts.runtime import results_store
from scripts.runtime.heartbeat import dispatcher, job_factory, reconciler, runner
from scripts.runtime.heartbeat.graph_reader import GraphReader
from scripts.runtime.verification.receipt_sink import write_receipt
from scripts.runtime.verification.schemas import VerdictReceipt


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    remote = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        text=True,
        capture_output=True,
        check=True,
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Mission E2E")
    _git(repo, "config", "user.email", "mission-e2e@example.invalid")
    _git(repo, "remote", "add", "origin", str(remote))
    (repo / "README.md").write_text("operator checkout\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "operator base")
    _git(repo, "push", "-u", "origin", "main")
    (repo / "operator-untracked.txt").write_text("preserve me\n")
    return repo, _git(repo, "rev-parse", "HEAD")


def _checkout_snapshot(repo: Path) -> dict[str, object]:
    return {
        "head": _git(repo, "rev-parse", "HEAD"),
        "branch": _git(repo, "branch", "--show-current"),
        "index": _git(repo, "write-tree"),
        "unstaged": _git(repo, "diff", "--binary"),
        "staged": _git(repo, "diff", "--cached", "--binary"),
        "untracked": tuple(
            _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        ),
    }


def _graph_snapshot(config_root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(config_root)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(config_root.rglob("*.yaml"))
    }


def _write_graph(
    config_root: Path,
    repo: Path,
    node_ids: tuple[str, ...],
    dependencies: dict[str, tuple[str, ...]] | None = None,
) -> None:
    dependencies = dependencies or {}
    graph = config_root / "graphs" / "mission-e2e"
    nodes = graph / "nodes"
    nodes.mkdir(parents=True)
    summaries = "\n".join(
        f"  - id: {node_id}\n    status: ready" for node_id in node_ids
    )
    (graph / "project.yaml").write_text(
        "project_id: mission-e2e\n"
        "project_name: Operator Authored Mission E2E\n"
        f"repo: {repo}\n"
        "nodes:\n"
        f"{summaries}\n"
        "execution_policy:\n"
        "  default_executor: factory_mission\n"
        "  max_concurrent_jobs: 2\n"
        "  mission_engagement_size: 1\n"
        "  mission_max_pairs: 5\n"
    )
    for node_id in node_ids:
        node_dependencies = dependencies.get(node_id, ())
        depends_on = (
            "depends_on:\n"
            + "".join(f"  - {dependency}\n" for dependency in node_dependencies)
            if node_dependencies
            else "depends_on: []\n"
        )
        (nodes / f"{node_id}.yaml").write_text(
            "schema_version: '1.0'\n"
            "schema_type: node\n"
            f"node_id: {node_id}\n"
            f"title: Operator topic {node_id}\n"
            "status: ready\n"
            "type: capability\n"
            f"why: Execute the operator-authored topic {node_id}.\n"
            f"{depends_on}"
            "acceptance_criteria:\n"
            f"  - Preserve the exact topic {node_id}.\n"
            "constraints:\n"
            "  - Change only the feature-owned result file.\n"
            "allowed_execution_modes:\n"
            "  - factory_mission\n"
            "required_artifacts: []\n"
            "priority: high\n"
            "unlocks: []\n"
            "human_gate: true\n"
        )


def _fake_droid(path: Path) -> Path:
    script = path / "droid"
    script.write_text(
        """#!/usr/bin/env python3
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

args = sys.argv[1:]
mission_file = pathlib.Path(args[args.index("-f") + 1])
branch = args[args.index("-w") + 1]
mission_root = pathlib.Path(os.environ["GDDP_FACTORY_MISSION_DIR"])
mission_dir = mission_root / "mis-e2e"
mission_dir.mkdir(parents=True)
(mission_dir / "handoffs").mkdir()
(mission_dir / "io.json").write_text(json.dumps({
    "stdin_tty": os.isatty(0),
    "stdout_tty": os.isatty(1),
    "stderr_tty": os.isatty(2),
    "argv": sys.argv,
}))
feature_ids = re.findall(
    r"^### Feature `([^`]+)`$", mission_file.read_text(), re.MULTILINE
)
(mission_dir / "features.json").write_text(json.dumps({
    "features": [{"id": feature_id} for feature_id in feature_ids]
}))
(mission_dir / "state.json").write_text(json.dumps({
    "missionId": "mis-e2e",
    "state": "running",
}))
worktree = mission_root.parent / "engagement-worktree"
subprocess.run(
    ["git", "worktree", "add", "-b", branch, str(worktree), "HEAD"],
    check=True,
)

def git(*git_args):
    return subprocess.run(
        ["git", *git_args],
        cwd=worktree,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()

progress_path = mission_dir / "progress_log.jsonl"
receipts_path = pathlib.Path(os.environ["GDDP_RECEIPTS_PATH"])
for index, feature_id in enumerate(feature_ids):
    worker_id = f"worker-{index:02d}"
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with progress_path.open("a") as progress:
        progress.write(json.dumps({
            "timestamp": started,
            "type": "worker_started",
            "featureId": feature_id,
            "workerSessionId": worker_id,
        }) + "\\n")
    base = git("rev-parse", "HEAD")
    (worktree / f"{index:02d}-{feature_id}.txt").write_text(feature_id + "\\n")
    git("add", f"{index:02d}-{feature_id}.txt")
    git(
        "commit",
        "-m",
        f"complete {feature_id}",
        "-m",
        f"GDDP-Node-Id: {feature_id}",
    )
    result = git("rev-parse", "HEAD")
    git("push", "origin", f"HEAD:refs/heads/{branch}")
    with receipts_path.open("a") as receipts:
        receipts.write(json.dumps({
            "node_id": feature_id,
            "base": base,
            "result": result,
            "timestamp_utc": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "git_head": result,
            "git_branch": branch,
            "git_toplevel": str(worktree),
        }) + "\\n")
    completed = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (mission_dir / "handoffs" / f"{index:02d}.json").write_text(json.dumps({
        "featureId": feature_id,
        "workerSessionId": worker_id,
        "commitId": result,
        "repoPath": str(worktree),
        "successState": "success",
    }))
    with progress_path.open("a") as progress:
        progress.write(json.dumps({
            "timestamp": completed,
            "type": "worker_completed",
            "featureId": feature_id,
            "workerSessionId": worker_id,
            "commitId": result,
            "successState": "success",
        }) + "\\n")
with progress_path.open("a") as progress:
    progress.write(json.dumps({
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "type": "mission_completed",
    }) + "\\n")
(mission_dir / "state.json").write_text(json.dumps({
    "missionId": "mis-e2e",
    "state": "completed",
}))
"""
    )
    script.chmod(0o755)
    return script


def _packet(node_id: str, base: str) -> NodePacket:
    return NodePacket(
        job_id=f"job-{node_id}",
        execution_attempt_id=f"job-{node_id}:attempt:0",
        node_id=node_id,
        title=f"Operator topic {node_id}",
        goal=f"Execute {node_id}",
        why=f"Operator authored {node_id}.",
        constraints=("Change only the feature-owned result file.",),
        acceptance_criteria=(f"Preserve the exact topic {node_id}.",),
        required_artifacts=(),
        attempt_index=0,
        expected_base_commit_sha=base,
    )


def _wait_for_completion(adapter: MissionAdapter, session_ref) -> None:
    deadline = time.monotonic() + 15
    while True:
        status = adapter.status(session_ref)
        if status.state != "running":
            assert status.state == "completed", status.error
            return
        assert time.monotonic() < deadline
        time.sleep(0.02)


def _receipt(pending: reconciler.PendingEvaluation) -> VerdictReceipt:
    return VerdictReceipt(
        project_id=pending.project_id,
        node_id=pending.node_id,
        verdict="pass",
        criteria_verdict="pass",
        integrity={
            "verdict": "pass",
            "intent_preserved": True,
            "graph_integrity_preserved": True,
            "required_human_review": False,
            "confidence": 1.0,
            "findings": [],
            "reasoning": "The integration evaluator observed valid evidence.",
        },
        confidence=1.0,
        criteria_confidence=1.0,
        completeness=1.0,
        graph_readiness=1.0,
        completeness_status="complete",
        deterministic={
            "criteria": [],
            "constraints": [],
            "artifacts_present": {},
            "deps_status": {},
            "criteria_mismatches": [],
            "missing_evidence": [],
            "human_review_questions": [],
        },
        semantic=None,
        decision_reasoning="All integration evidence agrees.",
        required_next_action="Human review.",
        generated_at="2026-08-07T00:00:00Z",
        evaluated_commit_sha=pending.result_commit_sha,
        merge_commit_sha=pending.result_commit_sha,
        expected_base_commit_sha=pending.expected_base_commit_sha,
        job_id=pending.job_id,
        execution_attempt_id=pending.execution_attempt_id,
        evidence_manifest_sha256=pending.evidence_manifest_sha256,
        mission_receipt_id=pending.mission_receipt_id,
    )


def test_ready_nodes_reach_review_through_headless_mission_pipeline(
    tmp_path, monkeypatch
):
    repo, base = _repository(tmp_path)
    config_root = tmp_path / "gddp-config"
    node_ids = ("operator-audit", "operator-execution")
    _write_graph(config_root, repo, node_ids)
    graph_before = _graph_snapshot(config_root)
    checkout_before = _checkout_snapshot(repo)
    mission_root = tmp_path / "factory-missions"
    mission_root.mkdir()
    session_root = tmp_path / "mission-sessions"
    runtime_root = tmp_path / "runtime"
    db_path = runtime_root / "db" / "queue.db"
    receipts_root = tmp_path / "verdict-receipts"
    fake_droid = _fake_droid(tmp_path)
    trace: list[str] = []
    spawn: dict[str, object] = {}

    monkeypatch.setenv("GDDP_CONFIG_PATH", str(config_root))
    monkeypatch.setenv("GDDP_FACTORY_MISSION_DIR", str(mission_root))
    monkeypatch.setenv("GDDP_MISSION_SESSION_DIR", str(session_root))
    monkeypatch.setattr(init_db, "DB_PATH", db_path)
    monkeypatch.setattr(runner, "DB_PATH", db_path)
    monkeypatch.setattr(runner, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(results_store, "DB_PATH", db_path)
    init_db.init_db()

    real_popen = mission_adapter.subprocess.Popen

    def observed_popen(argv, **kwargs):
        if list(argv[1:3]) == ["exec", "--mission"]:
            trace.append("mission_launch")
            spawn.update(argv=argv, kwargs=kwargs)
        return real_popen(argv, **kwargs)

    monkeypatch.setattr(mission_adapter.subprocess, "Popen", observed_popen)
    adapter = MissionAdapter(
        repo="owner/repo",
        cwd=repo,
        session_root=session_root,
        mission_root=mission_root,
        droid_path=str(fake_droid),
        mission_dir_timeout=5,
    )
    real_collect = adapter.collect_engagement

    def observed_collect(session_ref):
        trace.append("evidence_collection")
        return real_collect(session_ref)

    monkeypatch.setattr(adapter, "collect_engagement", observed_collect)
    monkeypatch.setitem(
        dispatcher.ADAPTERS,
        "factory_mission",
        lambda **_kwargs: adapter,
    )

    reader = GraphReader(config_path=str(config_root))
    ready_nodes = reader.get_ready_nodes("mission-e2e")
    assert [node.node_id for node in ready_nodes] == list(node_ids)
    trace.append("graph_ready")

    con = runner.connect()
    for index, node_id in enumerate(node_ids):
        con.execute(
            """
            INSERT INTO events (
                event_id, received_at, source, event_type, repo, project_id,
                status, url
            ) VALUES (?, ?, 'manual', 'issue.opened', 'owner/repo',
                      'mission-e2e', 'received', ?)
            """,
            (
                f"event-{index}",
                f"2026-08-07T00:00:0{index}Z",
                f"https://example.invalid/node: {node_id}",
            ),
        )
    con.commit()
    planned = runner._plan_dispatches(
        con,
        "mission-e2e",
        "owner/repo",
        ready_nodes,
        reader,
        expected_base_commit_sha=base,
        max_concurrent_jobs=2,
        repo_path=str(repo),
    )
    outcomes = runner._execute_dispatches(
        planned,
        "owner/repo",
        str(repo),
        execution_policy={
            "mission_engagement_size": 1,
            "mission_max_pairs": 5,
        },
    )
    runner._record_outcomes(con, planned, outcomes, str(repo))
    trace.append("heartbeat_dispatch")

    session_ref = next(iter(outcomes.values())).session_ref
    assert session_ref is not None
    _wait_for_completion(adapter, session_ref)
    trace.append("mission_completion")

    def evaluate(pending):
        trace.append(f"evaluator:{pending.node_id}")
        receipt_path = write_receipt(
            _receipt(pending),
            pending.project_id,
            base=receipts_root,
            job_id=pending.job_id,
            attempt=pending.attempt,
        )
        trace.append(f"verdict_receipt:{pending.node_id}")
        return {
            "verification_status": "ok",
            "verdict": "pass",
            "receipt_path": str(receipt_path),
            "changed_files": [],
        }

    monkeypatch.setattr(reconciler, "_run_evaluation", evaluate)
    batch = reconciler.EvaluationBatch(max_workers=1)
    reconciler.reconcile_sessions(
        con,
        repo,
        repo="owner/repo",
        evaluation_batch=batch,
    )
    batch.finalize(con)
    trace.append("awaiting_review")

    rows = con.execute(
        """
        SELECT j.node_id, j.status, j.queue_state, s.state,
               s.result_commit_sha, s.evidence_manifest_path,
               s.completion_quarantine_reason
          FROM jobs j
          JOIN executor_sessions s ON s.job_id = j.job_id
         ORDER BY j.node_id
        """
    ).fetchall()
    assert len(rows) == len(node_ids)
    for row in rows:
        assert (row["status"], row["queue_state"], row["state"]) == (
            "awaiting_review",
            "awaiting_review",
            "evaluated",
        )
        assert row["completion_quarantine_reason"] is None
        manifest = json.loads(
            Path(row["evidence_manifest_path"]).read_text()
        )
        result_sha = row["result_commit_sha"]
        assert {
            manifest["receipt"]["result"],
            manifest["handoff"]["commitId"],
            result_sha,
        } == {result_sha}
        assert manifest["git_verified"]["trailer_node_ids"] == [
            row["node_id"]
        ]
        assert manifest["git_verified"]["verified"] is True
        assert manifest["engagement_history"]["verified"] is True
        trace.append(f"git_verification:{row['node_id']}")

    receipt_files = sorted(receipts_root.rglob("*.json"))
    assert len(receipt_files) == len(node_ids)
    for receipt_file in receipt_files:
        receipt = VerdictReceipt.model_validate_json(receipt_file.read_text())
        assert receipt.merge_commit_sha == receipt.evaluated_commit_sha
        assert receipt.execution_attempt_id
        assert receipt.evidence_manifest_sha256
        assert receipt.mission_receipt_id

    record = json.loads(
        (session_root / session_ref.session_id / "session.json").read_text()
    )
    assert record["process_returncode"] == 0
    io = json.loads((Path(record["mission_dir"]) / "io.json").read_text())
    assert io["argv"][1:4] == ["exec", "--mission", "-f"]
    assert io["stdin_tty"] is False
    assert io["stdout_tty"] is False
    assert io["stderr_tty"] is False
    assert spawn["kwargs"]["stdin"] is subprocess.DEVNULL
    assert Path(spawn["kwargs"]["stdout"].name).name == "stdout"
    assert Path(spawn["kwargs"]["stderr"].name).name == "stderr"

    history = json.loads(
        Path(rows[0]["evidence_manifest_path"]).read_text()
    )["engagement_history"]
    assert history["node_ids"] == list(node_ids)
    assert len(history["commit_shas"]) == len(node_ids)
    assert _checkout_snapshot(repo) == checkout_before
    assert _graph_snapshot(config_root) == graph_before
    assert all("Operator topic" in node.title for node in ready_nodes)
    assert "complete" not in {
        node.status
        for node in GraphReader(config_path=str(config_root)).get_ready_nodes(
            "mission-e2e"
        )
    }
    con.close()

    assert trace.index("graph_ready") < trace.index("mission_launch")
    assert trace.index("mission_launch") < trace.index("heartbeat_dispatch")
    assert trace.index("heartbeat_dispatch") < trace.index(
        "mission_completion"
    )
    assert trace.index("mission_completion") < trace.index(
        "evidence_collection"
    )
    assert trace.index("evidence_collection") < trace.index(
        "evaluator:operator-audit"
    )
    assert trace.index("evaluator:operator-audit") < trace.index(
        "verdict_receipt:operator-audit"
    )
    assert trace.index("verdict_receipt:operator-execution") < trace.index(
        "awaiting_review"
    )


def test_eight_feature_engagement_preserves_topological_execution_order(
    tmp_path, monkeypatch
):
    repo, base = _repository(tmp_path)
    config_root = tmp_path / "gddp-config"
    mission_root = tmp_path / "factory-missions"
    mission_root.mkdir()
    monkeypatch.setenv("GDDP_FACTORY_MISSION_DIR", str(mission_root))
    adapter = MissionAdapter(
        repo="owner/repo",
        cwd=repo,
        session_root=tmp_path / "mission-sessions",
        mission_root=mission_root,
        droid_path=str(_fake_droid(tmp_path)),
        mission_dir_timeout=5,
    )
    node_ids = tuple(f"probe-2a-{index}" for index in range(8))
    dependencies = {
        node_ids[2]: (node_ids[0], node_ids[1]),
        node_ids[3]: (node_ids[2],),
        node_ids[4]: (node_ids[2],),
        node_ids[5]: (node_ids[3], node_ids[4]),
        node_ids[6]: (node_ids[5],),
        node_ids[7]: (node_ids[6],),
    }
    _write_graph(config_root, repo, node_ids, dependencies)
    graph_nodes = GraphReader(config_path=str(config_root)).get_ready_nodes(
        "mission-e2e"
    )
    jobs = []
    for index, node in enumerate(graph_nodes):
        job = job_factory.build_job(
            node,
            {"event_id": f"event-{index}"},
            "mission-e2e",
            "owner/repo",
            tmp_path / "runtime",
            "factory_mission",
        )
        job["expected_base_commit_sha"] = base
        jobs.append(job)
    assert {
        job["node_id"]: tuple(json.loads(job["dependencies"]))
        for job in jobs
    } == {
        node_id: dependencies.get(node_id, ())
        for node_id in node_ids
    }

    monkeypatch.setitem(
        dispatcher.ADAPTERS,
        "factory_mission",
        lambda **_kwargs: adapter,
    )
    planned = [
        runner.PlannedDispatch(
            event_id=f"event-{index}",
            classification={"executor_recommendation": "factory_mission"},
            job=job,
            session_db_id=f"session-{index}",
        )
        for index, job in enumerate(jobs)
    ]
    outcomes = runner._execute_dispatches(
        planned,
        "owner/repo",
        str(repo),
        execution_policy={
            "mission_engagement_size": 4,
            "mission_max_pairs": 5,
        },
    )
    assert all(outcome.success for outcome in outcomes.values())
    session_refs = {
        outcome.session_ref for outcome in outcomes.values()
    }
    assert len(session_refs) == 1
    session_ref = session_refs.pop()
    assert session_ref is not None
    _wait_for_completion(adapter, session_ref)

    collected = adapter.collect_engagement(session_ref)

    assert [item.feature_id for item in collected] == list(node_ids)
    assert all(item.success for item in collected)
    record = json.loads(
        (
            adapter.session_root
            / session_ref.session_id
            / "session.json"
        ).read_text()
    )
    mission_dir = Path(record["mission_dir"])
    features = json.loads((mission_dir / "features.json").read_text())
    assert [item["id"] for item in features["features"]] == list(node_ids)
    progress = [
        json.loads(line)
        for line in (mission_dir / "progress_log.jsonl").read_text().splitlines()
    ]
    starts = {
        item["featureId"]: index
        for index, item in enumerate(progress)
        if item["type"] == "worker_started"
    }
    completions = {
        item["featureId"]: index
        for index, item in enumerate(progress)
        if item["type"] == "worker_completed"
    }
    for dependent, node_dependencies in dependencies.items():
        for dependency in node_dependencies:
            assert completions[dependency] < starts[dependent]
    receipts = [
        json.loads(line)
        for line in Path(record["receipts_path"]).read_text().splitlines()
    ]
    assert [item["node_id"] for item in receipts] == list(node_ids)
    assert all(
        previous["result"] == following["base"]
        for previous, following in zip(receipts, receipts[1:])
    )
    manifest = json.loads(Path(collected[0].evidence_manifest_path).read_text())
    assert manifest["engagement_history"]["node_ids"] == list(node_ids)
    assert len(manifest["engagement_history"]["commit_shas"]) == 8


def test_production_dispatch_rejects_out_of_order_graph_jobs(
    tmp_path, monkeypatch
):
    node_ids = ("root", "dependent")
    config_root = tmp_path / "gddp-config"
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_graph(
        config_root,
        repo,
        node_ids,
        {"dependent": ("root",)},
    )
    graph_nodes = GraphReader(config_path=str(config_root)).get_ready_nodes(
        "mission-e2e"
    )
    jobs = [
        {
            **job_factory.build_job(
                node,
                {"event_id": f"event-{index}"},
                "mission-e2e",
                "owner/repo",
                tmp_path / "runtime",
                "factory_mission",
            ),
            "expected_base_commit_sha": "a" * 40,
        }
        for index, node in enumerate(graph_nodes)
    ]
    adapter = MagicMock()
    adapter.supports_engagement.return_value = True
    monkeypatch.setitem(
        dispatcher.ADAPTERS,
        "factory_mission",
        lambda **_kwargs: adapter,
    )

    result = dispatcher.dispatch_engagement(
        list(reversed(jobs)),
        "owner/repo",
        str(repo),
    )

    assert result.success is False
    assert "topological order" in (result.error or "")
    adapter.dispatch_engagement.assert_not_called()


def test_three_way_sha_disagreement_is_quarantined_before_evaluation(
    tmp_path, monkeypatch
):
    repo, base = _repository(tmp_path)
    mission_root = tmp_path / "factory-missions"
    mission_root.mkdir()
    monkeypatch.setenv("GDDP_FACTORY_MISSION_DIR", str(mission_root))
    adapter = MissionAdapter(
        repo="owner/repo",
        cwd=repo,
        session_root=tmp_path / "mission-sessions",
        mission_root=mission_root,
        droid_path=str(_fake_droid(tmp_path)),
        mission_dir_timeout=5,
    )
    dispatch_result = adapter.dispatch_engagement(
        [_packet("operator-conflict", base)]
    )
    assert dispatch_result.success is True
    assert dispatch_result.session_ref is not None
    _wait_for_completion(adapter, dispatch_result.session_ref)
    record = json.loads(
        (
            adapter.session_root
            / dispatch_result.session_ref.session_id
            / "session.json"
        ).read_text()
    )
    handoff_path = next(Path(record["mission_dir"], "handoffs").glob("*.json"))
    handoff = json.loads(handoff_path.read_text())
    result_sha = handoff["commitId"]
    handoff["commitId"] = base
    handoff_path.write_text(json.dumps(handoff))

    db_path = tmp_path / "runtime" / "db" / "queue.db"
    monkeypatch.setattr(init_db, "DB_PATH", db_path)
    init_db.init_db()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute(
        """
        INSERT INTO jobs (
            job_id, created_at, project_id, repo, node_id, job_type, executor,
            title, goal, status, queue_state
        ) VALUES (
            'job-conflict', '2026-08-07T00:00:00Z', 'mission-e2e',
            'owner/repo', 'operator-conflict', 'implementation',
            'factory_mission', 'Conflict', 'Detect conflict', 'running',
            'running'
        )
        """
    )
    con.execute(
        """
        INSERT INTO queue_records (
            queue_item_id, job_id, queue, available_at
        ) VALUES (
            'queue-conflict', 'job-conflict', 'running',
            '2026-08-07T00:00:00Z'
        )
        """
    )
    con.execute(
        """
        INSERT INTO executor_sessions (
            session_db_id, job_id, executor, session_id, state,
            execution_attempt_id, attempt_index, expected_base_commit_sha,
            created_at, updated_at
        ) VALUES (
            'session-conflict', 'job-conflict', 'factory_mission', ?,
            'running', 'job-conflict:attempt:0', 0, ?,
            '2026-08-07T00:00:00Z', '2026-08-07T00:00:00Z'
        )
        """,
        (dispatch_result.session_ref.session_id, base),
    )
    con.commit()
    session = con.execute(
        "SELECT * FROM executor_sessions WHERE session_db_id = "
        "'session-conflict'"
    ).fetchone()
    evaluator_batch = MagicMock()

    reconciler._reconcile_engagement_group(
        con,
        adapter,
        [session],
        repo,
        evaluator_batch,
    )

    row = con.execute(
        """
        SELECT s.state, s.completion_quarantine_reason, s.result_commit_sha,
               j.status, j.queue_state
          FROM executor_sessions s
          JOIN jobs j ON j.job_id = s.job_id
         WHERE s.session_db_id = 'session-conflict'
        """
    ).fetchone()
    assert row["state"] == "evaluated"
    assert (row["status"], row["queue_state"]) == (
        "awaiting_review",
        "awaiting_review",
    )
    assert row["result_commit_sha"] == result_sha
    assert row["completion_quarantine_reason"]
    evidence_path = con.execute(
        "SELECT evidence_manifest_path FROM executor_sessions WHERE "
        "session_db_id = 'session-conflict'"
    ).fetchone()[0]
    manifest = json.loads(Path(evidence_path).read_text())
    assert manifest["receipt"]["result"] == result_sha
    assert manifest["handoff"]["commitId"] == base
    assert manifest["git_verified"]["result_sha"] == result_sha
    evaluator_batch.add.assert_not_called()
    con.close()
